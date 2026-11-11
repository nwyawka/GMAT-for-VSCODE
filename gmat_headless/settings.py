from __future__ import annotations

import json
from pathlib import Path


APP_SUPPORT = Path.home() / "Library" / "Application Support" / "GMAT Headless"
CONFIG_PATH = APP_SUPPORT / "config.json"


def load_settings() -> dict[str, str]:
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def save_settings(settings: dict[str, str]) -> None:
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    temporary = CONFIG_PATH.with_suffix(".tmp")
    temporary.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
    temporary.replace(CONFIG_PATH)

