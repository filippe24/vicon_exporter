"""Choices remembered between runs, stored per user outside the repository.

The last dataset folder, where the folder dialogs open.
"""

import json
import os
from pathlib import Path

_BASE = Path(os.environ.get("APPDATA") or Path.home() / ".config")
PREFERENCES_FILE = _BASE / "vicon_exporter" / "preferences.json"


def _load() -> dict:
    try:
        data = json.loads(PREFERENCES_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(key: str, value: str):
    data = _load()
    data[key] = value
    try:
        PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
        PREFERENCES_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except OSError:
        pass  # Remembering is a convenience; never block an export over it.


def _existing(key: str, check) -> Path | None:
    value = _load().get(key)
    if isinstance(value, str) and value and check(Path(value)):
        return Path(value)
    return None


def last_dataset_folder() -> Path | None:
    return _existing("dataset_folder", Path.is_dir)


def remember_dataset_folder(folder: Path | str):
    _save("dataset_folder", str(folder))


def dataset_dialog_start() -> str | None:
    folder = last_dataset_folder()
    return str(folder) if folder else None
