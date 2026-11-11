from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

from .results import output_files, read_table
from .runner import GmatError, command_for, discover_gmat, installation_bin, prepare_run, validate_gmat
from .settings import load_settings, save_settings


def main() -> int:
    parser = argparse.ArgumentParser(description="Run GMAT scripts headlessly on macOS")
    parser.add_argument("script", nargs="?", type=Path, help="GMAT .script file")
    args = parser.parse_args()
    try:
        from PySide6 import QtCore, QtGui, QtWidgets
        import pyqtgraph as pg
    except ImportError:
        print("Install dependencies with: python -m pip install -r requirements.txt", file=sys.stderr)
        return 2

    class Window(QtWidgets.QMainWindow):
        def __init__(self) -> None:
            super().__init__()
            self.setWindowTitle("GMAT Headless")
            self.resize(1100, 760)
            self.settings = load_settings()
            self.executable: Path | None = discover_gmat(self.settings.get("gmat_executable"))
            self.script: Path | None = args.script.resolve() if args.script else None
            self.run = None
            self.process: QtCore.QProcess | None = None
            self.console_handle = None
            self._build_ui()
            self._show_paths()
            if self.executable:
                self.statusBar().showMessage(f"GMAT: {self.executable}")
            else:
                QtCore.QTimer.singleShot(0, self.choose_gmat)

        def _build_ui(self) -> None:
            root = QtWidgets.QWidget()
            layout = QtWidgets.QVBoxLayout(root)
            paths = QtWidgets.QFormLayout()
            self.gmat_label = QtWidgets.QLineEdit(readOnly=True)
            self.script_label = QtWidgets.QLineEdit(readOnly=True)
            gmat_row, script_row = QtWidgets.QHBoxLayout(), QtWidgets.QHBoxLayout()
            gmat_row.addWidget(self.gmat_label); script_row.addWidget(self.script_label)
            choose_gmat = QtWidgets.QPushButton("Choose…"); choose_gmat.clicked.connect(self.choose_gmat)
            choose_script = QtWidgets.QPushButton("Open…"); choose_script.clicked.connect(self.choose_script)
            edit_script = QtWidgets.QPushButton("Edit in VS Code"); edit_script.clicked.connect(self.edit_script)
            gmat_row.addWidget(choose_gmat); script_row.addWidget(choose_script); script_row.addWidget(edit_script)
            paths.addRow("GMAT", gmat_row); paths.addRow("Script", script_row)
            layout.addLayout(paths)
            buttons = QtWidgets.QHBoxLayout()
            self.run_button = QtWidgets.QPushButton("Run"); self.run_button.clicked.connect(self.start_run)
            self.stop_button = QtWidgets.QPushButton("Stop"); self.stop_button.clicked.connect(self.stop_run); self.stop_button.setEnabled(False)
            reveal = QtWidgets.QPushButton("Reveal Run in Finder"); reveal.clicked.connect(self.reveal_run)
            buttons.addWidget(self.run_button); buttons.addWidget(self.stop_button); buttons.addWidget(reveal); buttons.addStretch()
            layout.addLayout(buttons)
            splitter = QtWidgets.QSplitter(QtCore.Qt.Orientation.Vertical)
            self.console = QtWidgets.QPlainTextEdit(readOnly=True); self.console.setMaximumBlockCount(20_000)
            splitter.addWidget(self.console)
            results = QtWidgets.QSplitter()
            self.files = QtWidgets.QListWidget(); self.files.itemSelectionChanged.connect(self.show_result)
            self.tabs = QtWidgets.QTabWidget()
            self.table = QtWidgets.QTableWidget(); self.plot = pg.PlotWidget(background="w"); self.plot.showGrid(x=True, y=True, alpha=0.25)
            self.tabs.addTab(self.table, "Table"); self.tabs.addTab(self.plot, "Plot")
            results.addWidget(self.files); results.addWidget(self.tabs); results.setStretchFactor(1, 1)
            splitter.addWidget(results); splitter.setStretchFactor(0, 1); splitter.setStretchFactor(1, 1)
            layout.addWidget(splitter)
            self.setCentralWidget(root)

        def _show_paths(self) -> None:
            self.gmat_label.setText(str(self.executable or "Not selected"))
            self.script_label.setText(str(self.script or "Not selected"))

        def choose_gmat(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Select GmatConsole", str(Path.home() / "Applications"))
            if not path:
                return
            candidate = Path(path)
            try:
                label = validate_gmat(candidate)
            except GmatError as exc:
                QtWidgets.QMessageBox.critical(self, "Invalid GMAT executable", str(exc)); return
            self.executable = candidate.absolute()
            self.settings["gmat_executable"] = str(self.executable)
            save_settings(self.settings); self._show_paths(); self.statusBar().showMessage(f"Selected {label}")

        def choose_script(self) -> None:
            path, _ = QtWidgets.QFileDialog.getOpenFileName(self, "Open GMAT script", str(Path.cwd()), "GMAT scripts (*.script);;All files (*)")
            if path:
                self.script = Path(path).resolve(); self._show_paths()

        def edit_script(self) -> None:
            if not self.script:
                self.choose_script()
            if self.script:
                subprocess.Popen(["open", "-a", "Visual Studio Code", str(self.script)])

        def start_run(self) -> None:
            if not self.executable:
                self.choose_gmat()
            if not self.script:
                self.choose_script()
            if not self.executable or not self.script:
                return
            try:
                self.run = prepare_run(self.script, self.executable, Path.cwd() / "runs")
            except GmatError as exc:
                QtWidgets.QMessageBox.critical(self, "Cannot start run", str(exc)); return
            self.console.clear(); self.files.clear(); self.table.clear(); self.plot.clear()
            self.console_handle = self.run.console_log.open("wb")
            self.process = QtCore.QProcess(self)
            self.process.setProcessChannelMode(QtCore.QProcess.ProcessChannelMode.MergedChannels)
            self.process.setWorkingDirectory(str(installation_bin(self.executable)))
            self.process.readyReadStandardOutput.connect(self.read_output)
            self.process.finished.connect(self.run_finished)
            self.process.setProgram(str(self.executable))
            self.process.setArguments(command_for(self.executable, self.run)[1:])
            self.process.start()
            self.run_button.setEnabled(False); self.stop_button.setEnabled(True)
            self.statusBar().showMessage(f"Running {self.run.run_dir.name}…")

        def read_output(self) -> None:
            if not self.process:
                return
            data = bytes(self.process.readAllStandardOutput())
            if self.console_handle:
                self.console_handle.write(data); self.console_handle.flush()
            self.console.moveCursor(QtGui.QTextCursor.MoveOperation.End)
            self.console.insertPlainText(data.decode("utf-8", errors="replace"))
            self.console.moveCursor(QtGui.QTextCursor.MoveOperation.End)

        def run_finished(self, exit_code: int, _status) -> None:
            self.read_output()
            if self.console_handle:
                self.console_handle.close(); self.console_handle = None
            self.run_button.setEnabled(True); self.stop_button.setEnabled(False)
            self.statusBar().showMessage("Run completed" if exit_code == 0 else f"GMAT exited with code {exit_code}")
            self.refresh_results()

        def stop_run(self) -> None:
            if self.process and self.process.state() != QtCore.QProcess.ProcessState.NotRunning:
                pid = int(self.process.processId())
                try: os.kill(pid, signal.SIGTERM)
                except ProcessLookupError: pass
                QtCore.QTimer.singleShot(3000, lambda: self.process and self.process.kill())

        def refresh_results(self) -> None:
            self.files.clear()
            if not self.run: return
            for path in output_files(self.run.run_dir):
                item = QtWidgets.QListWidgetItem(str(path.relative_to(self.run.run_dir))); item.setData(QtCore.Qt.ItemDataRole.UserRole, path)
                self.files.addItem(item)

        def show_result(self) -> None:
            items = self.files.selectedItems()
            if not items: return
            path = items[0].data(QtCore.Qt.ItemDataRole.UserRole)
            try: headers, rows = read_table(path)
            except OSError as exc:
                self.statusBar().showMessage(str(exc)); return
            self.table.clear(); self.table.setColumnCount(len(headers)); self.table.setRowCount(min(len(rows), 2000)); self.table.setHorizontalHeaderLabels(headers)
            for row_index, row in enumerate(rows[:2000]):
                for column, value in enumerate(row): self.table.setItem(row_index, column, QtWidgets.QTableWidgetItem(value))
            self.table.resizeColumnsToContents(); self.plot.clear()
            if len(headers) >= 2:
                try:
                    x = [float(row[0]) for row in rows]
                    for column in range(1, min(len(headers), 7)):
                        y = [float(row[column]) for row in rows]
                        self.plot.plot(x, y, pen=pg.mkPen(pg.intColor(column), width=2), name=headers[column])
                except (ValueError, IndexError): pass

        def reveal_run(self) -> None:
            if self.run: subprocess.Popen(["open", str(self.run.run_dir)])

        def closeEvent(self, event) -> None:
            if self.process and self.process.state() != QtCore.QProcess.ProcessState.NotRunning:
                self.stop_run(); self.process.waitForFinished(3000)
            event.accept()

    application = QtWidgets.QApplication(sys.argv)
    application.setApplicationName("GMAT Headless")
    window = Window(); window.show()
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())

