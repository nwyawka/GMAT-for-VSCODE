# Repository Guidelines

## Project Structure & Module Organization

The project has two user interfaces over one GMAT execution layer:

- `gmat_headless/`: Python package. `runner.py` prepares isolated runs, `cli.py` supports VS Code, `app.py` provides the PySide6 desktop UI, and `results.py` parses reports.
- `gmat_app.py` and `gmat_cli.py`: thin executable entry points.
- `vscode-gmat/`: local VS Code extension, language grammar, snippets, and icon assets.
- `examples/`: working GMAT `.script` missions.
- `tests/`: standard-library unit tests.
- `runs/`: generated mission snapshots and outputs; never commit this directory.

Keep GMAT process and filesystem behavior in the Python package. VS Code-specific presentation belongs in `vscode-gmat/`.

## Build, Test, and Development Commands

Create the local environment and install dependencies:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
```

Useful commands:

```bash
.venv/bin/python gmat_app.py examples/earth_orbit.script
.venv/bin/python gmat_cli.py examples/earth_orbit.script
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q gmat_headless gmat_app.py gmat_cli.py
node --check vscode-gmat/extension.js
```

Reload VS Code after extension changes with **Developer: Reload Window**.

## Coding Style & Naming Conventions

Use four-space indentation and PEP 8 conventions for Python: `snake_case` functions, `PascalCase` classes, and type annotations for public interfaces. Keep entry points small and platform-specific behavior explicit. JavaScript uses two-space indentation, `camelCase` identifiers, semicolons, and no external runtime packages unless justified. Use descriptive GMAT example names such as `earth_orbit.script`.

## Testing Guidelines

Tests use `unittest` and follow `tests/test_*.py`. Add focused tests for path discovery, startup-file rewriting, report parsing, and failure handling. Tests must not depend on a local GMAT installation; real-GMAT checks are supplemental. Run the full unit suite before submitting changes.

## Commit & Pull Request Guidelines

No repository Git history is available to infer an existing convention. Use short, imperative commit subjects, for example `Add detachable result plots`. Pull requests should explain user-visible behavior, list validation commands, and include screenshots for Qt or VS Code UI changes. Link relevant issues and call out configuration or GMAT compatibility changes.

## Configuration & Safety

Never hard-code a user-specific GMAT path. Store local settings under macOS application support or VS Code configuration. Preserve per-run isolation, avoid modifying source scripts during execution, and do not commit logs, virtual environments, or generated results.
