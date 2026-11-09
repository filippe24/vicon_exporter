"""Which aligned outputs each take has, and whether they still match the aLigner export.

Every aligned step records in ``aligned_exports/reports/export_status.yaml`` the
aLigner values it used: actor frame ranges for actor exports and retargets, C3D
crop ranges for props. When the aLigner export YAML later gives different
values, the step is outdated and needs a new export with Overwrite. Only files
in the take folder are read, so this works without aLigner installed.
"""

import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from configuration.settings import (
    ACTORS_FOLDER_NAME,
    ALIGNED_EXPORT_FOLDER_NAME,
    ALIGNED_REPORTS_FOLDER_NAME,
)
from exporter.aligned_export_pipeline import (
    _collapse_actor_mocap_entries,
    _find_aligner_export_yaml,
    _read_mocap_entries,
)

STATUS_FILE = "export_status.yaml"
EXTRA_PREFIX = "__vicon_exporter_"

CURRENT = "current"
OUTDATED = "outdated"
UNVERIFIED = "unverified"
MISSING_OUTPUTS = "missing outputs"
NOT_EXPORTED = "not exported"
NOT_APPLICABLE = "not applicable"
NO_ALIGNMENT = "no alignment"


@dataclass(frozen=True)
class Step:
    key: str
    label: str
    # Which aLigner values the step depends on: "actors" or "props".
    inputs: str
    # The UserSelection option that runs the step.
    option: str
    calibration_only: bool = False


STEPS = (
    Step("actors", "Actors", "actors", "run_aligned_export"),
    Step("props", "Props", "props", "run_aligned_props"),
    Step("all_props", "All props C3D", "props", "run_aligned_combined_props"),
    Step("calibration_markers", "Unlabeled markers", "props", "run_aligned_calibration_markers", calibration_only=True),
    Step("metahuman", "MetaHuman", "actors", "run_aligned_metahuman"),
    Step("geeno", "Geeno", "actors", "run_aligned_geeno"),
)
STEP_BY_KEY = {step.key: step for step in STEPS}


@dataclass
class StepStatus:
    state: str
    outputs: list[str] = field(default_factory=list)
    record: dict[str, Any] | None = None
    changes: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class TakeStatus:
    take_dir: Path
    aligner_yaml: Path | None = None
    aligner_format: str | None = None
    # When aLigner last wrote the export YAML, and the saved alignment beside it.
    aligner_exported_at: datetime | None = None
    aligner_saved_at: datetime | None = None
    error: str | None = None
    steps: dict[str, StepStatus] = field(default_factory=dict)

    @property
    def outdated(self) -> list[str]:
        return [key for key, step in self.steps.items() if step.state in (OUTDATED, MISSING_OUTPUTS)]

    @property
    def aligner_export_stale(self) -> bool:
        """The alignment was saved after aLigner last exported, so the YAML may hold older values."""
        return bool(self.aligner_exported_at and self.aligner_saved_at
                    and (self.aligner_saved_at - self.aligner_exported_at).total_seconds() > 60)

    @property
    def exported(self) -> list[str]:
        return [key for key, step in self.steps.items() if step.state not in (NOT_EXPORTED, NOT_APPLICABLE, NO_ALIGNMENT)]


def aligner_inputs(take_dir: Path) -> tuple[Path, dict[str, list[dict[str, Any]]], str | None] | None:
    """The aLigner YAML used for this take and the values each kind of step reads from it."""
    path = _find_aligner_export_yaml(take_dir)
    if path is None:
        return None
    data = yaml.safe_load(path.read_text()) or {}
    entries = _read_mocap_entries(data)
    rows = {
        "actors": [_row(entry) for entry in _collapse_actor_mocap_entries(entries)],
        "props": [_row(entry) for entry in entries if entry.source_path.suffix.lower() == ".c3d"],
    }
    for values in rows.values():
        values.sort(key=lambda row: row["name"].lower())
    return path, rows, _format(data)


def fingerprint(values: list[dict[str, Any]]) -> str:
    text = yaml.safe_dump(values, sort_keys=True)
    return hashlib.sha256(text.encode()).hexdigest()[:16]


def record_step(take_dir: Path, key: str, outputs: list[Path] | None = None, **details: Any) -> None:
    """Remember the aLigner values a step was exported with. Never fails the export itself."""
    try:
        found = aligner_inputs(take_dir)
        if found is None:
            return
        path, inputs, aligner_format = found
        step = STEP_BY_KEY[key]
        aligned_root = take_dir / ALIGNED_EXPORT_FOLDER_NAME
        files = outputs if outputs is not None else _outputs(take_dir, key)
        record = {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "aligner_export_yaml": _relative(path, take_dir),
            "aligner_format": aligner_format,
            "fingerprint": fingerprint(inputs[step.inputs]),
            "aligner_values": inputs[step.inputs],
            "outputs": sorted(_relative(file, aligned_root) for file in files),
            **details,
        }
        status_path = aligned_root / ALIGNED_REPORTS_FOLDER_NAME / STATUS_FILE
        status_path.parent.mkdir(parents=True, exist_ok=True)
        data = _load_yaml(status_path)
        data.setdefault("steps", {})[key] = record
        temporary = status_path.with_name(STATUS_FILE + ".tmp")
        temporary.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True))
        temporary.replace(status_path)
    except (OSError, ValueError, yaml.YAMLError) as error:
        print(f"   warning: could not record export status for {key}: {error}")


def take_status(take_dir: Path) -> TakeStatus:
    result = TakeStatus(take_dir)
    calibration = any("calibration" in part.lower() for part in take_dir.parts)
    try:
        found = aligner_inputs(take_dir)
    except (OSError, ValueError, yaml.YAMLError) as error:
        found = None
        result.error = f"aLigner YAML unreadable: {error}"
    if found is not None:
        result.aligner_yaml, inputs, result.aligner_format = found
        result.aligner_exported_at = _modified(result.aligner_yaml)
        stem = result.aligner_yaml.name.split(".")[0]
        result.aligner_saved_at = _modified(result.aligner_yaml.with_name(f"{stem}.state.yaml"))
    else:
        inputs = None
    aligned_root = take_dir / ALIGNED_EXPORT_FOLDER_NAME
    records = _load_yaml(aligned_root / ALIGNED_REPORTS_FOLDER_NAME / STATUS_FILE).get("steps", {})
    for step in STEPS:
        outputs = [_relative(path, aligned_root) for path in _outputs(take_dir, step.key)]
        record = records.get(step.key)
        if step.calibration_only and not calibration and not outputs:
            status = StepStatus(NOT_APPLICABLE)
        elif inputs is None:
            status = StepStatus(NO_ALIGNMENT if not outputs else UNVERIFIED, outputs,
                                note="no aLigner export YAML in this take")
        elif record is not None:
            status = _recorded(record, inputs[step.inputs], outputs, aligned_root)
        elif outputs:
            status = _legacy(take_dir, step, inputs[step.inputs], outputs)
        else:
            status = StepStatus(NOT_EXPORTED)
        result.steps[step.key] = status
    return result


def describe_changes(old: list[dict[str, Any]], new: list[dict[str, Any]]) -> list[str]:
    before = {row["name"]: row for row in old}
    after = {row["name"]: row for row in new}
    changes = []
    for name in sorted(before.keys() | after.keys(), key=str.lower):
        if name not in after:
            changes.append(f"{name}: no longer in the aLigner export")
        elif name not in before:
            changes.append(f"{name}: new in the aLigner export")
        elif before[name] != after[name]:
            was, now = before[name], after[name]
            text = f"{name}: frames {was['start_frame']}–{was['end_frame']} → {now['start_frame']}–{now['end_frame']}"
            if was.get("sample_rate") != now.get("sample_rate"):
                text += f", rate {was.get('sample_rate')} → {now.get('sample_rate')}"
            changes.append(text)
    return changes


def _recorded(record, current, outputs, aligned_root) -> StepStatus:
    status = StepStatus(CURRENT, outputs, record)
    if record.get("fingerprint") != fingerprint(current):
        status.state = OUTDATED
        status.changes = describe_changes(record.get("aligner_values") or [], current) or ["aLigner values changed"]
    missing = [name for name in record.get("outputs") or [] if not (aligned_root / name).is_file()]
    if missing and status.state == CURRENT:
        status.state = MISSING_OUTPUTS
        status.note = f"{len(missing)} recorded outputs missing"
    elif not record.get("outputs"):
        status.note = "exported, no visible data in the crop"
    return status


def _legacy(take_dir, step, current, outputs) -> StepStatus:
    """Outputs exported before status tracking: compare the frames older reports kept, when they did."""
    reports = take_dir / ALIGNED_EXPORT_FOLDER_NAME / ALIGNED_REPORTS_FOLDER_NAME
    if step.inputs == "actors":
        old = [
            {key: row.get(key) for key in ("name", "start_frame", "end_frame")}
            for row in _load_yaml(reports / "aligned_export_summary.yaml").get("actors") or []
        ]
        now = [{key: row[key] for key in ("name", "start_frame", "end_frame")} for row in current]
    elif step.key == "props":
        old = list(_load_yaml(reports / "aligned_props_summary.yaml").get("c3d_ranges") or [])
        now = [{key: row[key] for key in ("name", "start_frame", "end_frame")} for row in current]
    else:
        old, now = [], []
    status = StepStatus(UNVERIFIED, outputs, note="exported before status tracking")
    if old:
        changes = describe_changes(_sorted(old), _sorted(now))
        if changes:
            status.state, status.changes = OUTDATED, changes
        else:
            status.note += "; frames in its old report still match"
    return status


def _outputs(take_dir: Path, key: str) -> list[Path]:
    root = take_dir / ALIGNED_EXPORT_FOLDER_NAME
    if key == "actors":
        return _files(root / ACTORS_FOLDER_NAME)
    if key == "props":
        return [path for path in _files(root / "props") if not path.name.startswith(EXTRA_PREFIX)]
    if key in ("all_props", "calibration_markers"):
        report = _load_yaml(root / ALIGNED_REPORTS_FOLDER_NAME / "aligned_scene_extras.yaml")
        name = (report.get("outputs") or {}).get(key)
        return [root / "props" / name] if name and (root / "props" / name).is_file() else []
    return _files(root / "retargeted" / key)


def _files(folder: Path) -> list[Path]:
    try:
        return sorted(path for path in folder.rglob("*") if path.is_file())
    except OSError:
        return []


def _row(entry) -> dict[str, Any]:
    return {
        "name": entry.name,
        "start_frame": int(entry.start_frame),
        "end_frame": int(entry.end_frame),
        "sample_rate": float(entry.sample_rate),
    }


def _sorted(rows):
    return sorted(rows, key=lambda row: str(row.get("name", "")).lower())


def _format(data) -> str | None:
    if isinstance(data, dict):
        return data.get("format")
    if isinstance(data, list) and data and isinstance(data[0], dict):
        return data[0].get("format")
    return None


def _relative(path: Path, root: Path) -> str:
    try:
        return Path(path).relative_to(root).as_posix()
    except ValueError:
        return Path(path).as_posix()


def _modified(path: Path) -> datetime | None:
    try:
        return datetime.fromtimestamp(path.stat().st_mtime)
    except OSError:
        return None


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text()) if path.is_file() else None
    except (OSError, yaml.YAMLError):
        return {}
    return data if isinstance(data, dict) else {}
