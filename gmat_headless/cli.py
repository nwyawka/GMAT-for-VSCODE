from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from pathlib import Path

from .runner import GmatError, command_for, discover_gmat, installation_bin, prepare_run


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a GMAT script for the VS Code extension")
    parser.add_argument("script", type=Path)
    parser.add_argument("--gmat", type=Path)
    parser.add_argument("--runs-root", type=Path, default=Path.cwd() / "runs")
    args = parser.parse_args()
    executable = args.gmat or discover_gmat()
    if not executable:
        print("GMAT_ERROR=GmatConsole was not found", flush=True)
        return 2
    try:
        run = prepare_run(args.script, executable, args.runs_root)
    except GmatError as exc:
        print(f"GMAT_ERROR={exc}", flush=True)
        return 2
    print(f"GMAT_RUN_DIR={run.run_dir}", flush=True)
    process = subprocess.Popen(
        command_for(executable, run), cwd=installation_bin(executable),
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        bufsize=1, start_new_session=True,
    )

    def stop(_signum, _frame):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    saw_error = False
    with run.console_log.open("w", encoding="utf-8") as log:
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="", flush=True)
            log.write(line); log.flush()
            saw_error |= "**** ERROR" in line or "Error occurred" in line
    code = process.wait()
    print(f"GMAT_EXIT_CODE={code}", flush=True)
    return code or (1 if saw_error else 0)


if __name__ == "__main__":
    raise SystemExit(main())

