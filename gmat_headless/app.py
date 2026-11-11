from __future__ import annotations

import argparse, os, signal, subprocess, sys
from datetime import datetime
from pathlib import Path

from .results import output_files, read_table
from .runner import GmatError, command_for, discover_gmat, installation_bin, prepare_run, validate_gmat
from .settings import load_settings, save_settings


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("script", nargs="?", type=Path)
    args = parser.parse_args()
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        import pyqtgraph as pg
    except ImportError:
        print("Install dependencies with: python -m pip install -r requirements.txt", file=sys.stderr); return 2

    class Window(QtWidgets.QMainWindow):
        def __init__(self):
            super().__init__(); self.resize(1220, 800); self.setMinimumSize(900, 620); self.setWindowTitle("GMAT Headless")
            self.settings = load_settings(); self.executable = discover_gmat(self.settings.get("gmat_executable"))
            self.script = args.script.resolve() if args.script else None
            self.run = self.active_run_dir = self.process = self.console_handle = self.started_at = None
            self.plot_windows = []
            self.build_ui(); self.apply_theme(); self.show_paths(); self.refresh_history(); self.set_status("Ready", "#4b78e6")
            if not self.executable: QtCore.QTimer.singleShot(0, self.choose_gmat)

        def icon(self, kind): return self.style().standardIcon(kind)
        def button(self, text, kind, callback, primary=False):
            b = QtWidgets.QPushButton(text); b.setIcon(self.icon(kind)); b.clicked.connect(callback); b.setObjectName("primary" if primary else "button"); return b
        def make_metric(self, row, value, caption):
            card = QtWidgets.QFrame(objectName="card"); lay = QtWidgets.QVBoxLayout(card)
            v = QtWidgets.QLabel(value, objectName="metric"); lay.addWidget(v); lay.addWidget(QtWidgets.QLabel(caption, objectName="caption")); row.addWidget(card); return v

        def build_ui(self):
            root = QtWidgets.QWidget(objectName="root"); outer = QtWidgets.QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
            header = QtWidgets.QFrame(objectName="header"); h = QtWidgets.QHBoxLayout(header); h.setContentsMargins(24,15,22,15)
            titles = QtWidgets.QVBoxLayout(); titles.setSpacing(1); titles.addWidget(QtWidgets.QLabel("GMAT Headless", objectName="title")); self.mission_title=QtWidgets.QLabel(objectName="muted"); titles.addWidget(self.mission_title); h.addLayout(titles); h.addStretch()
            self.badge=QtWidgets.QLabel(); h.addWidget(self.badge); self.stop_button=self.button("Stop",QtWidgets.QStyle.SP_MediaStop,self.stop_run); self.stop_button.setEnabled(False); h.addWidget(self.stop_button)
            self.run_button=self.button("Run Mission",QtWidgets.QStyle.SP_MediaPlay,self.start_run,True); h.addWidget(self.run_button); outer.addWidget(header)
            split=QtWidgets.QSplitter(); split.setHandleWidth(1)
            side=QtWidgets.QFrame(objectName="sidebar"); sl=QtWidgets.QVBoxLayout(side); sl.setContentsMargins(16,18,16,16)
            sl.addWidget(QtWidgets.QLabel("MISSION",objectName="caption")); card=QtWidgets.QFrame(objectName="card"); cl=QtWidgets.QVBoxLayout(card)
            self.script_name=QtWidgets.QLabel("No script selected",objectName="strong"); self.script_path=QtWidgets.QLabel(objectName="muted"); self.script_path.setWordWrap(True); cl.addWidget(self.script_name); cl.addWidget(self.script_path)
            actions=QtWidgets.QHBoxLayout(); actions.addWidget(self.button("Open",QtWidgets.QStyle.SP_DialogOpenButton,self.choose_script)); actions.addWidget(self.button("VS Code",QtWidgets.QStyle.SP_FileIcon,self.edit_script)); cl.addLayout(actions); sl.addWidget(card)
            hr=QtWidgets.QHBoxLayout(); hr.addWidget(QtWidgets.QLabel("RECENT RUNS",objectName="caption")); hr.addStretch(); self.history_count=QtWidgets.QLabel("0",objectName="muted"); hr.addWidget(self.history_count); sl.addLayout(hr)
            self.history=QtWidgets.QListWidget(); self.history.setFrameShape(QtWidgets.QFrame.NoFrame); self.history.itemSelectionChanged.connect(self.select_history); sl.addWidget(self.history,1)
            sl.addWidget(self.button("GMAT Settings",QtWidgets.QStyle.SP_ComputerIcon,self.choose_gmat)); split.addWidget(side)
            content=QtWidgets.QFrame(objectName="content"); ml=QtWidgets.QVBoxLayout(content); ml.setContentsMargins(22,15,22,15); self.tabs=QtWidgets.QTabWidget(); self.tabs.setDocumentMode(True); ml.addWidget(self.tabs)
            overview=QtWidgets.QWidget(); ol=QtWidgets.QVBoxLayout(overview); ol.setContentsMargins(3,14,3,3); ol.setSpacing(15)
            hero=QtWidgets.QFrame(objectName="hero"); hl=QtWidgets.QVBoxLayout(hero); self.hero_title=QtWidgets.QLabel("Ready to run",objectName="heroTitle"); self.hero_detail=QtWidgets.QLabel("Open a mission script, then run it with GMAT Console.",objectName="muted"); hl.addWidget(self.hero_title); hl.addWidget(self.hero_detail); ol.addWidget(hero)
            metrics=QtWidgets.QHBoxLayout(); self.duration=self.make_metric(metrics,"—","DURATION"); self.outputs=self.make_metric(metrics,"—","OUTPUT FILES"); self.gmat=self.make_metric(metrics,"—","GMAT"); ol.addLayout(metrics)
            details=QtWidgets.QFrame(objectName="card"); form=QtWidgets.QFormLayout(details); self.detail_script=QtWidgets.QLabel("—"); self.detail_run=QtWidgets.QLabel("—"); self.detail_output=QtWidgets.QLabel("—")
            for w in (self.detail_script,self.detail_run,self.detail_output): w.setWordWrap(True); w.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse)
            form.addRow("Source script",self.detail_script); form.addRow("Run snapshot",self.detail_run); form.addRow("Output folder",self.detail_output); ol.addWidget(details); ol.addStretch(); self.tabs.addTab(overview,"Overview")
            cp=QtWidgets.QWidget(); cpl=QtWidgets.QVBoxLayout(cp); self.console=QtWidgets.QPlainTextEdit(readOnly=True,objectName="console"); self.console.setPlaceholderText("Console output will appear here."); cpl.addWidget(self.console); self.tabs.addTab(cp,"Console")
            dp=QtWidgets.QWidget(); dl=QtWidgets.QHBoxLayout(dp); self.files=QtWidgets.QListWidget(); self.files.setMaximumWidth(280); self.files.itemSelectionChanged.connect(self.show_result); self.files.itemDoubleClicked.connect(lambda _item:self.open_plot_window()); self.table=QtWidgets.QTableWidget(); self.table.setAlternatingRowColors(True); self.table.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers); self.table.verticalHeader().hide(); dl.addWidget(self.files); dl.addWidget(self.table,1); self.tabs.addTab(dp,"Data")
            pp=QtWidgets.QWidget(); pl=QtWidgets.QVBoxLayout(pp); chart_bar=QtWidgets.QHBoxLayout(); self.chart_title=QtWidgets.QLabel("Select a report in Data",objectName="strong"); chart_bar.addWidget(self.chart_title); chart_bar.addStretch(); chart_bar.addWidget(self.button("Open Plot Window",QtWidgets.QStyle.SP_TitleBarMaxButton,self.open_plot_window)); pl.addLayout(chart_bar); self.plot=pg.PlotWidget(); self.plot.showGrid(x=True,y=True,alpha=.18); pl.addWidget(self.plot); self.tabs.addTab(pp,"Charts")
            split.addWidget(content); split.setSizes([245,975]); split.setCollapsible(0,False); outer.addWidget(split,1)
            footer=QtWidgets.QFrame(objectName="footer"); fl=QtWidgets.QHBoxLayout(footer); fl.setContentsMargins(18,7,18,7); self.footer=QtWidgets.QLabel(objectName="muted"); fl.addWidget(self.footer); fl.addStretch(); fl.addWidget(self.button("Reveal in Finder",QtWidgets.QStyle.SP_DirOpenIcon,self.reveal_run)); outer.addWidget(footer); self.setCentralWidget(root)

        def apply_theme(self):
            dark=self.palette().color(QtGui.QPalette.Window).lightness()<128
            bg,panel,raised,side,text,muted,border,console=("#12161d","#1a2029","#202834","#161b23","#f2f5f8","#9aa7b7","#2d3745","#0c1016") if dark else ("#f3f5f8","#fff","#f8fafc","#e9edf3","#18212f","#667386","#d8dee8","#111820")
            self.setStyleSheet(f"""*{{font-family:-apple-system,'SF Pro Text';font-size:13px;color:{text}}}#root,#content{{background:{bg}}}#header,#footer{{background:{panel};border-bottom:1px solid {border}}}#footer{{border-top:1px solid {border}}}#sidebar{{background:{side};border-right:1px solid {border}}}#title{{font-size:20px;font-weight:700}}#heroTitle{{font-size:21px;font-weight:700}}#strong{{font-weight:600}}#muted,#caption{{color:{muted}}}#caption{{font-size:10px;font-weight:700}}#card,#hero{{background:{panel};border:1px solid {border};border-radius:10px}}#hero{{border-left:4px solid #4b78e6}}#metric{{font-size:20px;font-weight:700}}QPushButton{{min-height:30px;padding:0 11px;background:{raised};border:1px solid {border};border-radius:7px}}QPushButton:hover{{border-color:#4b78e6}}#primary{{background:#4b78e6;color:white;border:0;font-weight:600;padding:0 16px}}QTabWidget::pane{{border:0}}QTabBar::tab{{padding:9px 16px;color:{muted};border-bottom:2px solid transparent}}QTabBar::tab:selected{{color:{text};border-bottom:2px solid #4b78e6;font-weight:600}}QListWidget{{background:transparent;border:0;outline:0}}QListWidget::item{{padding:9px 8px;border-radius:7px}}QListWidget::item:selected{{background:rgba(75,120,230,.18)}}#console{{background:{console};color:#d9e2ec;border:1px solid {border};border-radius:9px;padding:12px;font-family:'SF Mono',Menlo;font-size:12px}}QTableWidget{{background:{panel};alternate-background-color:{raised};border:1px solid {border};border-radius:8px;gridline-color:{border}}}QHeaderView::section{{background:{raised};padding:8px;border:0;border-bottom:1px solid {border}}}QSplitter::handle{{background:{border}}}""")
            self.plot.setBackground(panel)

        def set_status(self,text,color): self.badge.setText(text); self.badge.setStyleSheet(f"background:{color}22;color:{color};padding:6px 11px;border-radius:11px;font-weight:600"); self.footer.setText(text)
        def show_paths(self):
            if self.script: self.mission_title.setText(self.script.name); self.script_name.setText(self.script.name); self.script_path.setText(str(self.script.parent)); self.detail_script.setText(str(self.script))
            else: self.mission_title.setText("Choose a GMAT script to begin")
            self.gmat.setText("R2025a" if self.executable else "Not configured")
        def choose_gmat(self):
            path,_=QtWidgets.QFileDialog.getOpenFileName(self,"Select GmatConsole",str(Path.home()/"Applications"))
            if not path:return
            try: label=validate_gmat(Path(path))
            except GmatError as e: QtWidgets.QMessageBox.critical(self,"Invalid GMAT executable",str(e)); return
            self.executable=Path(path).absolute(); self.settings["gmat_executable"]=str(self.executable); save_settings(self.settings); self.show_paths(); self.footer.setText(f"Selected {label}")
        def choose_script(self):
            path,_=QtWidgets.QFileDialog.getOpenFileName(self,"Open GMAT script",str(Path.cwd()),"GMAT scripts (*.script)")
            if path:self.script=Path(path).resolve();self.show_paths()
        def edit_script(self):
            if not self.script:self.choose_script()
            if self.script:subprocess.Popen(["open","-a","Visual Studio Code",str(self.script)])
        def start_run(self):
            if not self.executable:self.choose_gmat()
            if not self.script:self.choose_script()
            if not self.executable or not self.script:return
            try:self.run=prepare_run(self.script,self.executable,Path.cwd()/"runs")
            except GmatError as e:QtWidgets.QMessageBox.critical(self,"Cannot start run",str(e));return
            self.active_run_dir=self.run.run_dir;self.started_at=datetime.now();self.console.clear();self.files.clear();self.table.clear();self.plot.clear();self.console_handle=self.run.console_log.open("wb")
            self.process=QtCore.QProcess(self);self.process.setProcessChannelMode(QtCore.QProcess.MergedChannels);self.process.setWorkingDirectory(str(installation_bin(self.executable)));self.process.readyReadStandardOutput.connect(self.read_output);self.process.finished.connect(self.run_finished);self.process.setProgram(str(self.executable));self.process.setArguments(command_for(self.executable,self.run)[1:]);self.process.start()
            self.run_button.setEnabled(False);self.stop_button.setEnabled(True);self.hero_title.setText("Mission running");self.hero_detail.setText("Live output is available in Console.");self.duration.setText("Running…");self.detail_run.setText(str(self.run.script));self.detail_output.setText(str(self.run.output_dir));self.set_status("Running","#d08b32");self.tabs.setCurrentIndex(1)
        def read_output(self):
            if not self.process:return
            data=bytes(self.process.readAllStandardOutput());self.console_handle and self.console_handle.write(data);self.console.appendPlainText(data.decode(errors="replace").rstrip())
        def run_finished(self,code,_):
            self.read_output();self.console_handle and self.console_handle.close();self.console_handle=None;self.run_button.setEnabled(True);self.stop_button.setEnabled(False);elapsed=(datetime.now()-self.started_at).total_seconds();self.duration.setText(f"{elapsed:.2f} s")
            failed=code!=0 or "**** ERROR" in self.console.toPlainText();self.hero_title.setText("Mission needs attention" if failed else "Mission completed");self.hero_detail.setText("Review Console for details." if failed else "Explore generated reports in Data and Charts.");self.set_status("Failed" if failed else "Completed","#d95757" if failed else "#2fa66f");self.refresh_results();self.refresh_history();self.tabs.setCurrentIndex(1 if failed else 0)
        def stop_run(self):
            if self.process and self.process.state()!=QtCore.QProcess.NotRunning:
                try:os.kill(int(self.process.processId()),signal.SIGTERM)
                except ProcessLookupError:pass
        def refresh_results(self):
            self.files.clear();paths=output_files(self.active_run_dir) if self.active_run_dir else [];self.outputs.setText(str(len(paths)))
            for p in paths:i=QtWidgets.QListWidgetItem(self.icon(QtWidgets.QStyle.SP_FileIcon),str(p.relative_to(self.active_run_dir)));i.setData(QtCore.Qt.UserRole,p);self.files.addItem(i)
            if paths:self.files.setCurrentRow(0)
        def refresh_history(self):
            self.history.blockSignals(True);self.history.clear();root=Path.cwd()/"runs";dirs=sorted([p for p in root.iterdir() if p.is_dir()],reverse=True) if root.is_dir() else []
            for d in dirs[:30]:i=QtWidgets.QListWidgetItem(self.icon(QtWidgets.QStyle.SP_DialogApplyButton),d.name.replace("_","  ",1));i.setData(QtCore.Qt.UserRole,d);self.history.addItem(i)
            self.history_count.setText(str(len(dirs)));self.history.blockSignals(False)
        def select_history(self):
            if not self.history.selectedItems():return
            self.active_run_dir=self.history.selectedItems()[0].data(QtCore.Qt.UserRole);self.detail_run.setText(str(self.active_run_dir));self.detail_output.setText(str(self.active_run_dir/"outputs"));self.hero_title.setText("Previous run");self.refresh_results()
        def show_result(self):
            if not self.files.selectedItems():return
            p=self.files.selectedItems()[0].data(QtCore.Qt.UserRole);headers,rows=read_table(p);self.table.clear();self.table.setColumnCount(len(headers));self.table.setRowCount(min(len(rows),2000));self.table.setHorizontalHeaderLabels(headers)
            for r,row in enumerate(rows[:2000]):
                for c,v in enumerate(row):self.table.setItem(r,c,QtWidgets.QTableWidgetItem(v))
            self.table.resizeColumnsToContents();self.plot.clear();self.plot.addLegend();self.chart_title.setText(p.name)
            try:
                x=[float(r[0]) for r in rows]
                for c in range(1,min(len(headers),7)):self.plot.plot(x,[float(r[c]) for r in rows],pen=pg.mkPen(pg.intColor(c,hues=7),width=2),name=headers[c])
                self.plot.setLabel("bottom",headers[0])
            except (ValueError,IndexError):pass
        def open_plot_window(self):
            if not self.files.selectedItems():
                QtWidgets.QMessageBox.information(self,"Choose report","Select a numeric report in the Data tab first.");return
            path=self.files.selectedItems()[0].data(QtCore.Qt.UserRole);headers,rows=read_table(path)
            try:
                x=[float(row[0]) for row in rows]
                series=[(headers[c],[float(row[c]) for row in rows]) for c in range(1,min(len(headers),7))]
            except (ValueError,IndexError):
                QtWidgets.QMessageBox.warning(self,"Cannot plot report","The selected report does not contain numeric columns.");return
            window=QtWidgets.QMainWindow(self);window.setAttribute(QtCore.Qt.WA_DeleteOnClose);window.resize(920,620);window.setWindowTitle(f"{path.name} — GMAT Plot")
            central=QtWidgets.QWidget();layout=QtWidgets.QVBoxLayout(central);heading=QtWidgets.QLabel(path.name,objectName="heroTitle");subheading=QtWidgets.QLabel(str(path),objectName="muted");subheading.setTextInteractionFlags(QtCore.Qt.TextSelectableByMouse);layout.addWidget(heading);layout.addWidget(subheading)
            plot=pg.PlotWidget();plot.setBackground(self.plot.backgroundBrush());plot.showGrid(x=True,y=True,alpha=.2);plot.addLegend(offset=(12,12));plot.setLabel("bottom",headers[0])
            for index,(name,values) in enumerate(series,1):plot.plot(x,values,pen=pg.mkPen(pg.intColor(index,hues=7),width=2),name=name)
            layout.addWidget(plot);window.setCentralWidget(central);window.setStyleSheet(self.styleSheet());window.destroyed.connect(lambda:self.plot_windows.remove(window) if window in self.plot_windows else None);self.plot_windows.append(window);window.show();window.raise_();window.activateWindow()
        def reveal_run(self):
            if self.active_run_dir:subprocess.Popen(["open",str(self.active_run_dir)])
        def closeEvent(self,event):
            if self.process and self.process.state()!=QtCore.QProcess.NotRunning:self.stop_run();self.process.waitForFinished(3000)
            event.accept()

    app=QtWidgets.QApplication(sys.argv);app.setApplicationName("GMAT Headless");app.setStyle("Fusion");window=Window();window.show();return app.exec()


if __name__ == "__main__": raise SystemExit(main())
