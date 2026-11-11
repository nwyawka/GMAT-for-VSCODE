# GMAT Headless for macOS

A local Python/Qt application for running GMAT scripts without the GMAT GUI, viewing console output, and inspecting report files. It does not start a web server and is not a packaged executable.

## Set up

GMAT must already be installed. From this directory:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python gmat_app.py examples/earth_orbit.script
```

The first time GMAT cannot be found automatically, choose `GmatConsole` in the native file picker. The validated path is remembered in `~/Library/Application Support/GMAT Headless/config.json`.

Every execution snapshots the script and redirects GMAT's output into a unique folder under `runs/`. The app never edits the source script during a run.

## VS Code

Open this folder in VS Code, select a `.script` file, and use **GMAT: Run Headless (-H)** or **GMAT: Run with Native Plots (+H)** from the Command Palette.

The `vscode-gmat` folder contains the complete, inspectable, self-contained extension. It adds syntax highlighting, snippets, Run/Stop editor buttons, live GMAT output, run history, tables, and VS Code result tabs. It starts no server and does not require Python on the destination Mac.

Install it locally by copying or symlinking the folder, then reload VS Code:

```bash
mkdir -p ~/.vscode/extensions
ln -s "$PWD/vscode-gmat" ~/.vscode/extensions/gmat-headless-0.3.0
```

Open this project as the VS Code workspace. If mission scripts live in another workspace, set **GMAT Headless: Project Path** to this project directory. Use **GMAT: Select Installation** only if automatic GMAT discovery does not find `GmatConsole`.

## Tests

```bash
python3 -m unittest discover -s tests -v
```
