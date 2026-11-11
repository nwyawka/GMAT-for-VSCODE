# GMAT Headless

Run GMAT `.script` missions directly from VS Code on macOS. The extension provides syntax highlighting, snippets, Run/Stop controls, console output, isolated run history, result tables, and plots. It starts no server and requires no Python installation.

## Requirements

- macOS
- VS Code 1.80 or newer
- A working GMAT installation

After installation, open a folder containing GMAT scripts. If GMAT is not detected, run **GMAT: Select Installation** and choose `GmatConsole`. Open a `.script` file and choose a run mode from the editor title bar or Command Palette:

- **GMAT: Run Headless (-H)** runs with no concurrent plot tabs.
- **GMAT: Run with Native Plots (+H)** launches the GMAT GUI minimized so the script's `OrbitView`, `XYPlot`, and other graphical subscribers display while the mission runs.

These are extension modes; `-H` and `+H` are not literal GMAT flags. `-H` uses `GmatConsole`. `+H` launches GMAT's GUI executable in the foreground and leaves it open so native plot windows remain visible. Quit GMAT normally or use **GMAT: Stop Mission** when finished.

Reports containing Cartesian X, Y, and Z columns include an interactive 3D trajectory. Drag to rotate and scroll to zoom.

Generated files are stored under `runs/` in the open workspace.
