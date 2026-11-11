from __future__ import annotations

import csv
from pathlib import Path


def output_files(run_dir: Path) -> list[Path]:
    ignored = {"console.log", "gmat.log", "gmat_startup_file.txt"}
    return sorted(
        path for path in run_dir.rglob("*")
        if path.is_file() and path.name not in ignored and path.parent != run_dir
    )


def read_table(path: Path, limit: int = 10_000) -> tuple[list[str], list[list[str]]]:
    lines = [line for line in path.read_text(encoding="utf-8", errors="replace").splitlines() if line.strip()]
    if not lines:
        return [], []
    sample = "\n".join(lines[:10])
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",\t;")
        rows = list(csv.reader(lines[: limit + 1], dialect))
    except csv.Error:
        rows = [line.split() for line in lines[: limit + 1]]
    width = max(map(len, rows), default=0)
    rows = [row + [""] * (width - len(row)) for row in rows]
    return rows[0], rows[1:]

