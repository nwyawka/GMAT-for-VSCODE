from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from uuid import uuid4


COMMON_LOCATIONS = (
    Path.home() / "Applications" / "GmatConsole",
    Path.home() / "Applications" / "bin" / "GmatConsole",
    Path.home() / "Applications" / "GMATR2025a" / "bin" / "GmatConsole",
    Path("/Applications/GMAT/bin/GmatConsole"),
)


class GmatError(RuntimeError):
    pass


@dataclass(frozen=True)
class PreparedRun:
    run_dir: Path
    script: Path
    output_dir: Path
    console_log: Path
    gmat_log: Path
    startup_file: Path


def is_executable(path: Path) -> bool:
    return path.is_file() and os.access(path, os.X_OK)


def discover_gmat(saved_path: str | None = None) -> Path | None:
    candidates = ([Path(saved_path).expanduser()] if saved_path else []) + list(COMMON_LOCATIONS)
    for candidate in candidates:
        if is_executable(candidate):
            # Preserve the public bin-folder symlink. Resolving it enters the
            # macOS app bundle, where GMAT can no longer find its startup file.
            return candidate.absolute()
    applications = Path.home() / "Applications"
    if applications.is_dir():
        for candidate in applications.glob("GMAT*/bin/GmatConsole"):
            if is_executable(candidate):
                return candidate.absolute()
    return None


def installation_bin(executable: Path) -> Path:
    """Return the bin folder even when executable is a symlink into an app bundle."""
    executable = executable.expanduser().absolute()
    parts = executable.parts
    if "Contents" in parts and "MacOS" in parts:
        macos_index = parts.index("MacOS")
        return Path(*parts[: macos_index - 2])
    return executable.parent


def find_startup_file(executable: Path) -> Path:
    bin_dir = installation_bin(executable)
    candidates = (bin_dir / "gmat_startup_file.txt", bin_dir.parent / "gmat_startup_file.txt")
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise GmatError(f"Could not find gmat_startup_file.txt beside {executable}")


def validate_gmat(executable: Path, timeout: float = 15) -> str:
    if not is_executable(executable):
        raise GmatError(f"Not an executable file: {executable}")
    try:
        result = subprocess.run(
            [str(executable), "--version"],
            cwd=installation_bin(executable),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise GmatError(f"GMAT validation failed: {exc}") from exc
    combined = result.stdout + result.stderr
    if "GMAT" not in combined:
        raise GmatError(f"The selected program did not identify itself as GMAT.\n{combined[-1000:]}")
    match = re.search(r"GMAT[^\n]*(?:R\d{4}[a-z]?|Version[^\n]*)", combined, re.IGNORECASE)
    return match.group(0).strip() if match else "GMAT Console"


def prepare_run(script: Path, executable: Path, runs_root: Path) -> PreparedRun:
    script = script.expanduser().resolve()
    if not script.is_file():
        raise GmatError(f"Script does not exist: {script}")
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    run_dir = runs_root.resolve() / f"{stamp}_{uuid4().hex[:6]}"
    output_dir = run_dir / "outputs"
    output_dir.mkdir(parents=True)
    snapshot = run_dir / script.name
    shutil.copy2(script, snapshot)

    source_startup = find_startup_file(executable)
    startup_text = source_startup.read_text(encoding="utf-8", errors="replace")
    replacement = f"OUTPUT_PATH              = {output_dir}/"
    startup_text, count = re.subn(r"^\s*OUTPUT_PATH\s*=.*$", replacement, startup_text, flags=re.MULTILINE)
    if count != 1:
        raise GmatError(f"Expected one OUTPUT_PATH entry in {source_startup}; found {count}")
    startup = run_dir / "gmat_startup_file.txt"
    startup.write_text(startup_text, encoding="utf-8")
    return PreparedRun(
        run_dir=run_dir,
        script=snapshot,
        output_dir=output_dir,
        console_log=run_dir / "console.log",
        gmat_log=run_dir / "gmat.log",
        startup_file=startup,
    )


def command_for(executable: Path, run: PreparedRun) -> list[str]:
    return [
        str(executable),
        "--startup_file", str(run.startup_file),
        "--logfile", str(run.gmat_log),
        "--run", str(run.script),
    ]

