const vscode = require('vscode');
const fs = require('fs');
const path = require('path');
const cp = require('child_process');

let child, currentRun;
const output = vscode.window.createOutputChannel('GMAT');
const status = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 90);

function workspace() { return vscode.workspace.workspaceFolders?.[0]?.uri.fsPath; }
function config() { return vscode.workspace.getConfiguration('gmatHeadless'); }
function runsRoot() { return path.join(workspace() || process.cwd(), 'runs'); }

function findGmat() {
  const selected=config().get('executable');
  const home=require('os').homedir();
  return [selected,path.join(home,'Applications','GmatConsole'),path.join(home,'Applications','bin','GmatConsole'),path.join(home,'Applications','GMATR2025a','bin','GmatConsole'),'/Applications/GMAT/bin/GmatConsole'].find(p=>p&&fs.existsSync(p));
}
function findGmatGui(consolePath) {
  const bin=path.dirname(consolePath);
  if(bin.endsWith(path.join('Contents','MacOS'))){const direct=path.join(bin,'GMAT');if(fs.existsSync(direct))return direct;}
  if(!fs.existsSync(bin))return undefined;
  for(const name of fs.readdirSync(bin).filter(x=>x.endsWith('.app'))){const candidate=path.join(bin,name,'Contents','MacOS','GMAT');if(fs.existsSync(candidate))return candidate;}
  return undefined;
}
function installationBin(executable) {
  const marker=`${path.sep}Contents${path.sep}MacOS${path.sep}`;
  return executable.includes(marker)?path.resolve(path.dirname(executable),'../../..'):path.dirname(executable);
}
function prepareRun(script,gmat) {
  const now=new Date(), stamp=`${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}_${String(now.getHours()).padStart(2,'0')}${String(now.getMinutes()).padStart(2,'0')}${String(now.getSeconds()).padStart(2,'0')}`;
  const run=path.join(runsRoot(),`${stamp}_${Math.random().toString(16).slice(2,8)}`), outputs=path.join(run,'outputs');fs.mkdirSync(outputs,{recursive:true});
  const snapshot=path.join(run,path.basename(script));fs.copyFileSync(script,snapshot);
  const bin=installationBin(gmat), candidates=[path.join(bin,'gmat_startup_file.txt'),path.join(bin,'..','gmat_startup_file.txt')], source=candidates.find(fs.existsSync);
  if(!source)throw new Error(`Could not find gmat_startup_file.txt beside ${gmat}`);
  let startup=fs.readFileSync(source,'utf8'),count=0;startup=startup.replace(/^\s*OUTPUT_PATH\s*=.*$/m,()=>{count++;return `OUTPUT_PATH              = ${outputs}/`;});if(count!==1)throw new Error('Could not redirect GMAT OUTPUT_PATH.');
  const startupPath=path.join(run,'gmat_startup_file.txt');fs.writeFileSync(startupPath,startup);
  return {run,outputs,snapshot,startupPath,bin};
}
function suppressMissingMatlabDialog(startupPath) {
  let text=fs.readFileSync(startupPath,'utf8');
  text=text.replace(/^(\s*PLUGIN\s*=.*libMatlabInterface.*)$/m,'# Disabled for unattended GUI run: $1');
  fs.writeFileSync(startupPath,text);
}

class RunTree {
  constructor() { this.changed = new vscode.EventEmitter(); this.onDidChangeTreeData = this.changed.event; }
  refresh() { this.changed.fire(); }
  getTreeItem(item) { return item; }
  getChildren(item) {
    if (!item) {
      if (!fs.existsSync(runsRoot())) return [];
      return fs.readdirSync(runsRoot(), {withFileTypes:true}).filter(x=>x.isDirectory()).map(x=>x.name).sort().reverse().slice(0,30).map(name=>{
        const i=new vscode.TreeItem(name,vscode.TreeItemCollapsibleState.Collapsed); i.contextValue='gmatRun'; i.runPath=path.join(runsRoot(),name); i.iconPath=new vscode.ThemeIcon('run-all'); return i;
      });
    }
    if (!item.runPath) return [];
    const dir=path.join(item.runPath,'outputs'); if(!fs.existsSync(dir)) return [];
    return fs.readdirSync(dir,{withFileTypes:true}).filter(x=>x.isFile()).map(x=>{
      const i=new vscode.TreeItem(x.name,vscode.TreeItemCollapsibleState.None); i.contextValue='gmatResult'; i.filePath=path.join(dir,x.name); i.command={command:'gmat.openResult',title:'Open Result',arguments:[i]}; i.iconPath=new vscode.ThemeIcon('graph'); return i;
    });
  }
}

function parseReport(file) {
  const lines=fs.readFileSync(file,'utf8').split(/\r?\n/).filter(x=>x.trim()); if(!lines.length)return {headers:[],rows:[]};
  const split = lines[0].includes(',') ? s=>s.split(',').map(x=>x.trim()) : s=>s.trim().split(/\s+/);
  return {headers:split(lines[0]),rows:lines.slice(1,10001).map(split)};
}
function esc(s){return String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function trajectory3d(headers,rows) {
  const column=axis=>headers.findIndex(h=>new RegExp(`(?:^|\\.)${axis}$`,'i').test(h.trim()));
  const xi=column('X'),yi=column('Y'),zi=column('Z');
  if([xi,yi,zi].some(i=>i<0))return '<p class="hint">A 3D trajectory appears when the report contains X, Y, and Z columns.</p>';
  const stride=Math.max(1,Math.ceil(rows.length/4000)),points=rows.filter((_,i)=>i%stride===0).map(r=>[+r[xi],+r[yi],+r[zi]]).filter(p=>p.every(Number.isFinite));
  if(points.length<2)return '<p class="hint">Not enough Cartesian samples for a 3D trajectory.</p>';
  return `<section><div class="plotHeading"><h2>Interactive 3D trajectory</h2><span>Drag to rotate · Scroll to zoom</span></div><canvas id="trajectory3d"></canvas></section><script>(()=>{const pts=${JSON.stringify(points)},canvas=document.getElementById('trajectory3d'),ctx=canvas.getContext('2d');let ax=.55,ay=-.7,zoom=1,drag=false,lx=0,ly=0;const max=Math.max(...pts.flat().map(Math.abs))||1;function draw(){const dpr=devicePixelRatio||1,w=canvas.clientWidth,h=canvas.clientHeight;canvas.width=w*dpr;canvas.height=h*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,w,h);const project=p=>{let[x,y,z]=p.map(v=>v/max);const x1=x*Math.cos(ay)-z*Math.sin(ay),z1=x*Math.sin(ay)+z*Math.cos(ay),y1=y*Math.cos(ax)-z1*Math.sin(ax);return[w/2+x1*Math.min(w,h)*.38*zoom,h/2-y1*Math.min(w,h)*.38*zoom]};ctx.strokeStyle=getComputedStyle(document.body).getPropertyValue('--vscode-charts-blue')||'#4b78e6';ctx.lineWidth=2;ctx.beginPath();pts.forEach((p,i)=>{const q=project(p);i?ctx.lineTo(...q):ctx.moveTo(...q)});ctx.stroke();const origin=project([0,0,0]);ctx.fillStyle='#4b78e6';ctx.beginPath();ctx.arc(...origin,Math.max(5,18*zoom),0,Math.PI*2);ctx.globalAlpha=.32;ctx.fill();ctx.globalAlpha=1;const end=project(pts[pts.length-1]);ctx.fillStyle='#2fa66f';ctx.beginPath();ctx.arc(...end,4,0,Math.PI*2);ctx.fill()}canvas.onpointerdown=e=>{drag=true;lx=e.clientX;ly=e.clientY;canvas.setPointerCapture(e.pointerId)};canvas.onpointermove=e=>{if(!drag)return;ay+=(e.clientX-lx)*.01;ax+=(e.clientY-ly)*.01;lx=e.clientX;ly=e.clientY;draw()};canvas.onpointerup=()=>drag=false;canvas.onwheel=e=>{e.preventDefault();zoom=Math.max(.25,Math.min(5,zoom*Math.exp(-e.deltaY*.001)));draw()};new ResizeObserver(draw).observe(canvas);draw()})()</script>`;
}
function resultHtml(file) {
  const {headers,rows}=parseReport(file), numeric=headers.map((_,c)=>rows.every(r=>Number.isFinite(Number(r[c]))));
  const cols=numeric.map((v,i)=>v?i:-1).filter(i=>i>=0), xcol=cols[0], series=cols.slice(1,7), W=900,H=440,pad=48;
  let svg='<p>No numeric series available.</p>';
  if(xcol!==undefined&&series.length&&rows.length){const xs=rows.map(r=>+r[xcol]), ys=series.flatMap(c=>rows.map(r=>+r[c])), xmin=Math.min(...xs),xmax=Math.max(...xs),ymin=Math.min(...ys),ymax=Math.max(...ys),sx=x=>pad+(x-xmin)/(xmax-xmin||1)*(W-2*pad),sy=y=>H-pad-(y-ymin)/(ymax-ymin||1)*(H-2*pad),colors=['#4b78e6','#2fa66f','#d95757','#a66bda','#e09236','#35a9b8'];
    svg=`<svg viewBox="0 0 ${W} ${H}"><line x1="${pad}" y1="${H-pad}" x2="${W-pad}" y2="${H-pad}"/><line x1="${pad}" y1="${pad}" x2="${pad}" y2="${H-pad}"/>${series.map((c,i)=>`<polyline fill="none" stroke="${colors[i]}" stroke-width="2" points="${rows.map(r=>`${sx(+r[xcol])},${sy(+r[c])}`).join(' ')}"/>`).join('')}</svg><div class="legend">${series.map((c,i)=>`<span style="color:${colors[i]}">● ${esc(headers[c])}</span>`).join('')}</div>`;}
  const table=`<table><thead><tr>${headers.map(h=>`<th>${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.slice(0,500).map(r=>`<tr>${r.map(v=>`<td>${esc(v)}</td>`).join('')}</tr>`).join('')}</tbody></table>`;
  return `<!doctype html><style>body{font-family:var(--vscode-font-family);color:var(--vscode-foreground);padding:20px}h1{font-size:20px}h2{font-size:15px;margin:0}.plotHeading{display:flex;align-items:center;justify-content:space-between;margin-top:24px}.plotHeading span,.hint{color:var(--vscode-descriptionForeground)}canvas{display:block;width:100%;height:440px;margin-top:10px;background:var(--vscode-editor-background);border:1px solid var(--vscode-panel-border);border-radius:6px;cursor:grab}canvas:active{cursor:grabbing}svg{width:100%;background:var(--vscode-editor-background)}svg line{stroke:var(--vscode-editor-foreground);opacity:.5}.legend{display:flex;gap:18px;margin:8px 0 24px}table{border-collapse:collapse;width:100%;font-family:var(--vscode-editor-font-family);margin-top:24px}th,td{padding:6px 9px;border-bottom:1px solid var(--vscode-panel-border);text-align:right}th{position:sticky;top:0;background:var(--vscode-editor-background)}</style><h1>${esc(path.basename(file))}</h1>${svg}${trajectory3d(headers,rows)}${table}`;
}

async function runMission(nativePlots, tree) {
  const editor=vscode.window.activeTextEditor;
  if(!editor||!editor.document.fileName.endsWith('.script')){vscode.window.showWarningMessage('Open a GMAT .script file first.');return;}
  if(child){vscode.window.showWarningMessage('A GMAT mission is already running.');return;}
  await editor.document.save();const exe=findGmat();if(!exe){vscode.window.showErrorMessage('GmatConsole was not found. Run GMAT: Select Installation.');return;}
  let prepared;try{prepared=prepareRun(editor.document.fileName,exe);}catch(e){vscode.window.showErrorMessage(e.message);return;}currentRun=prepared.run;
  let launch=exe,argv=['--startup_file',prepared.startupPath,'--logfile',path.join(prepared.run,'gmat.log'),'--run',prepared.snapshot];
  if(nativePlots){launch=findGmatGui(exe);if(!launch){vscode.window.showErrorMessage('The GMAT GUI executable was not found beside GmatConsole.');return;}suppressMissingMatlabDialog(prepared.startupPath);}
  output.clear();output.show(true);output.appendLine(`Mode: ${nativePlots?'+H native GMAT plots':'-H headless console'}`);output.appendLine(`Executable: ${launch}`);output.appendLine(`GMAT_RUN_DIR=${prepared.run}`);status.text=`$(sync~spin) GMAT ${nativePlots?'+H':'-H'} Running`;
  child=cp.spawn(launch,argv,{cwd:prepared.bin});const log=fs.createWriteStream(path.join(prepared.run,'console.log'));let sawError=false;
  if(nativePlots){const pid=child.pid;setTimeout(()=>cp.spawn('/usr/bin/osascript',['-e',`tell application "System Events" to set frontmost of first process whose unix id is ${pid} to true`]),1200);}
  const consume=data=>{const text=data.toString();sawError ||= text.includes('**** ERROR') || text.includes('Error occurred');output.append(text);log.write(text);};child.stdout.on('data',consume);child.stderr.on('data',consume);
  child.on('error',e=>{vscode.window.showErrorMessage(`Could not start GMAT: ${e.message}`);child=undefined;status.text='$(error) GMAT Error';});
  child.on('close',code=>{log.end();const failed=code!==0||sawError;child=undefined;tree.refresh();status.text=!failed?'$(check) GMAT Complete':'$(error) GMAT Failed';if(!failed)vscode.window.showInformationMessage('GMAT mission completed.','Show Runs').then(x=>x&&vscode.commands.executeCommand('workbench.view.extension.gmat'));else vscode.window.showErrorMessage('GMAT failed. See GMAT Output for details.');});
}

function activate(context) {
  const tree=new RunTree(); vscode.window.registerTreeDataProvider('gmatRuns',tree);
  status.text='$(rocket) GMAT Ready'; status.command='gmat.run'; status.show();
  context.subscriptions.push(output,status,
    vscode.commands.registerCommand('gmat.refreshRuns',()=>tree.refresh()),
    vscode.commands.registerCommand('gmat.selectExecutable',async()=>{const pick=await vscode.window.showOpenDialog({canSelectMany:false,openLabel:'Select GmatConsole'});if(pick)await config().update('executable',pick[0].fsPath,vscode.ConfigurationTarget.Workspace);}),
    vscode.commands.registerCommand('gmat.stop',()=>{if(child){child.kill('SIGTERM');output.appendLine('\nStopping GMAT…');}}),
    vscode.commands.registerCommand('gmat.revealRun',item=>item?.runPath&&vscode.commands.executeCommand('revealFileInOS',vscode.Uri.file(item.runPath))),
    vscode.commands.registerCommand('gmat.openResult',item=>{const file=item?.filePath||item;if(!file)return;const panel=vscode.window.createWebviewPanel('gmatResult',path.basename(file),vscode.ViewColumn.Beside,{enableScripts:true});panel.webview.html=resultHtml(file);}),
    vscode.commands.registerCommand('gmat.run',()=>runMission(false,tree)),
    vscode.commands.registerCommand('gmat.runWithPlots',()=>runMission(true,tree))
  );
}
function deactivate(){if(child)child.kill('SIGTERM');}
module.exports={activate,deactivate,_test:{parseReport,resultHtml,trajectory3d,installationBin,prepareRun,findGmatGui}};
