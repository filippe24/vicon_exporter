"""Choices remembered between runs, stored per user outside the repository.

Folder and FBX pickers each keep their own last location, so choosing a target
FBX no longer moves where the take folder dialog opens (and the other way round).
"""

import json
import os
from pathlib import Path

from configuration.settings import METAHUMAN_VICON_TARGET_FBX

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


def target_fbx() -> Path:
    """The last chosen UE5 target FBX, or the configured default."""
    return _existing("target_fbx", Path.is_file) or METAHUMAN_VICON_TARGET_FBX


def remember_target_fbx(path: Path | str):
    _save("target_fbx", str(path))


def dataset_dialog_start() -> str | None:
    folder = last_dataset_folder()
    return str(folder) if folder else None


def fbx_dialog_start() -> str | None:
    path = target_fbx().resolve()
    return str(path.parent) if path.parent.is_dir() else None
