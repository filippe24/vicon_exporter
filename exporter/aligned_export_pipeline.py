from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

import yaml

from configuration.settings import (
    ACTORS_FOLDER_NAME,
    ALIGNED_EXPORT_FOLDER_NAME,
    ALIGNED_REPORTS_FOLDER_NAME,
    EXPORT_FOLDER_NAME,
)


@dataclass(frozen=True)
class AlignedMocapEntry:
    name: str
    stem: str
    source_path: Path
    start_frame: int
    end_frame: int
    sample_rate: float

    @property
    def actor_prefix(self) -> str:
        return self.stem.removesuffix("_")

    @property
    def source_mcp_path(self) -> Path:
        return self.source_path.with_suffix(".mcp")


@dataclass(frozen=True)
class AlignedExportPlan:
    take_dir: Path
    export_yaml_path: Path
    output_root: Path
    actors_dir: Path
    retargeted_dir: Path
    reports_dir: Path
    scripts_dir: Path
    mocap_entries: list[AlignedMocapEntry]
    start_frame: int
    end_frame: int


def load_aligned_export_plan(take_dir: Path) -> AlignedExportPlan | None:
    export_yaml_path = _find_aligner_export_yaml(take_dir)
    if export_yaml_path is None:
        print(
            f"   warning: no aligner export YAML found in {take_dir / 'aligner._data'}"
        )
        return None

    raw_data = yaml.safe_load(export_yaml_path.read_text()) or {}
    mocap_entries = _read_mocap_entries(raw_data)
    actor_entries = _collapse_actor_mocap_entries(mocap_entries)
    # Export YAML can travel between drive letters and operating systems.
    actor_entries = [
        replace(
            entry,
            source_path=take_dir
            / EXPORT_FOLDER_NAME
            / ACTORS_FOLDER_NAME
            / str(entry.source_path).replace("\\", "/").split("/")[-1],
        )
        for entry in actor_entries
    ]

    if not actor_entries:
        print(f"   warning: no actor mocap entries found in {export_yaml_path}")
        return None

    ranges = {(entry.start_frame, entry.end_frame) for entry in actor_entries}
    if len(ranges) != 1:
        print(
            "   warning: actor mocap ranges differ; using the earliest start and latest end."
        )

    start_frame = min(entry.start_frame for entry in actor_entries)
    end_frame = max(entry.end_frame for entry in actor_entries)

    output_root = take_dir / ALIGNED_EXPORT_FOLDER_NAME
    return AlignedExportPlan(
        take_dir=take_dir,
        export_yaml_path=export_yaml_path,
        output_root=output_root,
        actors_dir=output_root / ACTORS_FOLDER_NAME,
        retargeted_dir=output_root / "retargeted",
        reports_dir=output_root / ALIGNED_REPORTS_FOLDER_NAME,
        scripts_dir=output_root / "scripts",
        mocap_entries=actor_entries,
        start_frame=start_frame,
        end_frame=end_frame,
    )


def create_aligned_export_dirs(plan: AlignedExportPlan) -> None:
    plan.actors_dir.mkdir(parents=True, exist_ok=True)
    plan.retargeted_dir.mkdir(parents=True, exist_ok=True)
    plan.reports_dir.mkdir(parents=True, exist_ok=True)
    plan.scripts_dir.mkdir(parents=True, exist_ok=True)


def generate_aligned_actor_export_hsl(
    plan: AlignedExportPlan,
    actor_entry: AlignedMocapEntry | None = None,
    include_bvh: bool = True,
    static_hand_bvh: bool = False,
) -> str:
    start_frame = (
        actor_entry.start_frame if actor_entry is not None else plan.start_frame
    )
    end_frame = actor_entry.end_frame if actor_entry is not None else plan.end_frame
    actor_label = actor_entry.actor_prefix if actor_entry is not None else "all actors"
    bvh_export_line = _bvh_export_hsl(include_bvh, static_hand_bvh)

    return f"""// Export aligned actor motion from the aLigner frame window.
// Source: {actor_label}
playRange {start_frame} {end_frame};

selectProps;
select -invert;

string $sel[] = `getModules -sel -type Character`;
int $numsel = `getCount $sel`;
int $i;
int $j;
string $first;
string $actor_file_stem;
string $actors_export_directory;
$actors_export_directory = ("{_hsl_path(plan.actors_dir)}/");

for ($i = 0; $i < $numsel; $i+= 1)
{{
    print $sel[$i];

    selectChildren -recursive $sel[$i];
    $first = `strLeft $sel[$i] 3`;
    $actor_file_stem = $first;
    for ($j = 0; $j < $numsel; $j += 1)
    {{
        if ($j != $i && `strLeft $sel[$j] 3` == $first)
        {{
            $actor_file_stem = $sel[$i];
        }}
    }}

    string $filename_c3d;
    string $filename_fbx;
    string $filename_bvh;
    string $filename_mcp;

    $filename_c3d = ($actors_export_directory + $actor_file_stem + "_aligned.c3d");
    $filename_fbx = ($actors_export_directory + $actor_file_stem + "_aligned.fbx");
    $filename_bvh = ($actors_export_directory + $actor_file_stem + "_aligned.bvh");
    $filename_mcp = ($actors_export_directory + $actor_file_stem + "_aligned.mcp");

    saveFile -s $filename_c3d;
    saveFile -s $filename_fbx;
{bvh_export_line}
    saveFile -s $filename_mcp;
}}
"""


def _bvh_export_hsl(include_bvh: bool, static_hand_bvh: bool) -> str:
    if not include_bvh:
        return "    // BVH export skipped after Shogun rejected this skeleton."

    if not static_hand_bvh:
        return "    saveFile -s $filename_bvh;"

    return """    // BVH fallback: make hand/finger placeholders writable as static joints.
    select ;
    selectByName "*Hand*" -type SolvingBone -childOf $sel[$i];
    if( `getNumModules -sel` > 0 )
    {
        setProperty "DOF" "Rx" true;
        setProperty "DOF" "Ry" true;
        setProperty "DOF" "Rz" true;
    }
    selectChildren -recursive $sel[$i];
    bvhExportOptions -writeDofs true;
    saveFile -s $filename_bvh;"""


def generate_aligned_retarget_hsl(
    *,
    template_path: Path,
    plan: AlignedExportPlan,
    retarget_vsr_file_path: Path,
    retarget_folder_name: str,
    file_name_prefix: str,
) -> str:
    template = template_path.read_text()
    output_dir = plan.retargeted_dir / retarget_folder_name
    output_dir.mkdir(parents=True, exist_ok=True)

    return (
        f"// Retarget aligned actor motion from the aLigner frame window.\n"
        f"playRange {plan.start_frame} {plan.end_frame};\n\n"
        + template.replace("{ACTORS_FOLDER}", retarget_folder_name)
        .replace("{EXPORT_DIR}", _hsl_path(plan.retargeted_dir))
        .replace("{RETARGET_VSR_PATH}", _hsl_path(retarget_vsr_file_path))
        .replace("{NEW_FILE_NAME}", file_name_prefix)
        .replace("{GEENO_FILE_NAME}", file_name_prefix)
    )


def write_aligned_export_summary(plan: AlignedExportPlan) -> Path:
    summary_path = plan.reports_dir / "aligned_export_summary.yaml"
    data: dict[str, Any] = {
        "aligner_export_yaml": str(plan.export_yaml_path),
        "source_export_folder": str(plan.take_dir / EXPORT_FOLDER_NAME),
        "aligned_export_folder": str(plan.output_root),
        "generated_scripts_folder": str(plan.scripts_dir),
        "start_frame": plan.start_frame,
        "end_frame": plan.end_frame,
        "actors": [
            {
                "name": entry.name,
                "source_path": str(entry.source_path),
                "start_frame": entry.start_frame,
                "end_frame": entry.end_frame,
                "sample_rate": entry.sample_rate,
            }
            for entry in plan.mocap_entries
        ],
    }
    summary_path.write_text(yaml.safe_dump(data, sort_keys=False))
    return summary_path


def _find_aligner_export_yaml(take_dir: Path) -> Path | None:
    data_dirs = [
        take_dir / ".aligner",
        take_dir / ".aligner" / "exports",
        take_dir / "aligner._data",
        take_dir / "aligner._data" / "exports",
        take_dir / ALIGNED_EXPORT_FOLDER_NAME / ".aligner",
        take_dir / ALIGNED_EXPORT_FOLDER_NAME / ".aligner" / "exports",
        take_dir / ALIGNED_EXPORT_FOLDER_NAME / "aligner._data",
        take_dir / ALIGNED_EXPORT_FOLDER_NAME / "aligner._data" / "exports",
    ]

    matches: list[Path] = []
    for data_dir in data_dirs:
        if data_dir.exists():
            matches.extend(path for path in data_dir.glob("*.export.yaml") if path.is_file())

    if not matches:
        return None

    return min(matches, key=_export_yaml_sort_key)


def _export_yaml_sort_key(path: Path) -> tuple[int, int, str]:
    # Folder renames can leave older exports alongside the current metadata.
    # Prefer full exports, then modification time, regardless of the take name.
    is_slim_export = ".slim." in path.name.lower()
    return (1 if is_slim_export else 0, -path.stat().st_mtime_ns, path.as_posix().lower())


def _normalize_mocap_sample_rate(sample_rate: float) -> float:
    if sample_rate <= 0.0:
        return sample_rate
    frame_time = 1.0 / sample_rate
    nearest_rate = round(sample_rate)
    if nearest_rate > 0 and abs(frame_time - (1.0 / nearest_rate)) <= 5e-7:
        return float(nearest_rate)
    return float(sample_rate)


def _read_mocap_entries(raw_data: dict[str, Any] | list[Any]) -> list[AlignedMocapEntry]:
    entries: list[AlignedMocapEntry] = []
    track_entries = _iter_export_track_entries(raw_data)

    slim_actor_stems: set[str] = set()
    for item in track_entries:
        if not isinstance(item, dict) or "file" not in item:
            continue
        file_name = str(item.get("file", "")).removesuffix(" (*)").strip()
        suffix = Path(file_name).suffix.lower()
        stem = Path(file_name).stem
        if suffix in {".bvh", ".mcp", ".fbx"} or stem.endswith("_"):
            slim_actor_stems.add(stem.lower())

    for entry_data in track_entries:
        if not isinstance(entry_data, dict):
            continue

        if "file" in entry_data and "track_type" not in entry_data:
            entry = _read_slim_mocap_entry(entry_data, slim_actor_stems)
            if entry is not None:
                entries.append(entry)
            continue

        if str(entry_data.get("track_type", "")).upper() != "MOCAP":
            continue

        entry = _read_mocap_entry(entry_data)
        if entry is not None:
            entries.append(entry)

    return entries


def _collapse_actor_mocap_entries(
    mocap_entries: list[AlignedMocapEntry],
) -> list[AlignedMocapEntry]:
    entries_by_stem: dict[str, list[AlignedMocapEntry]] = {}
    for entry in mocap_entries:
        if not _is_actor_mocap_entry(entry):
            continue
        entries_by_stem.setdefault(entry.stem.lower(), []).append(entry)

    collapsed: list[AlignedMocapEntry] = []
    for _, entries in sorted(entries_by_stem.items()):
        chosen = min(entries, key=_actor_entry_sort_key)
        c3d_match = next(
            (e for e in entries if e.source_path.suffix.lower() == ".c3d"),
            None,
        )
        if (
            c3d_match is not None
            and chosen.source_path.suffix.lower() == ".bvh"
            and chosen.sample_rate == c3d_match.sample_rate
            and (chosen.start_frame, chosen.end_frame)
            != (c3d_match.start_frame, c3d_match.end_frame)
        ):
            chosen = replace(
                chosen,
                start_frame=c3d_match.start_frame,
                end_frame=c3d_match.end_frame,
            )
        collapsed.append(chosen)
    return collapsed


def _is_actor_mocap_entry(entry: AlignedMocapEntry) -> bool:
    return any(part.lower() == ACTORS_FOLDER_NAME for part in entry.source_path.parts)


def _actor_entry_sort_key(entry: AlignedMocapEntry) -> tuple[int, str]:
    suffix = entry.source_path.suffix.lower()
    suffix_priority = {
        ".bvh": 0,
        ".mcp": 1,
        ".fbx": 2,
        ".c3d": 3,
    }
    return (suffix_priority.get(suffix, 99), entry.name.lower())


def _iter_export_track_entries(raw_data: dict[str, Any] | list[Any]) -> list[Any]:
    if isinstance(raw_data, list):
        return raw_data

    if not isinstance(raw_data, dict):
        return []

    if "timebases" in raw_data:
        # Version 2 structure
        return raw_data["timebases"]

    groups = raw_data.get("groups")
    if isinstance(groups, list):
        tracks: list[Any] = []
        for group_data in groups:
            if isinstance(group_data, dict):
                group_tracks = group_data.get("tracks", [])
                if isinstance(group_tracks, list):
                    tracks.extend(group_tracks)
        return tracks

    return list(raw_data.values())


def _contract_range(data, start, end, rate):
    """Convert aLigner v1 zero-based half-open samples into inclusive playRange."""
    sampling = data.get("sampling")
    if not isinstance(sampling, dict):
        return int(start), int(end), float(rate)
    if sampling.get("version") != 1 or sampling.get("index_origin") != 0 or sampling.get("end_exclusive") is not True:
        raise ValueError("Unsupported aLigner sample interval contract")
    if float(sampling.get("clock_scale", 1)) != 1:
        raise ValueError("Shogun MCP export does not support aLigner clock-rate edits; materialize or remove the warp first")
    geometry = data.get("geometry", {})
    transform = geometry.get("permanent_transform_meters", {}) if isinstance(geometry, dict) else {}
    if float(transform.get("scale", 1)) != 1 or any(transform.get("translation", (0, 0, 0))):
        raise ValueError("Shogun MCP export does not support aLigner permanent geometry edits")
    start = int(sampling["source_start_sample"])
    end = int(sampling["source_end_sample"])
    rate = float(sampling["source_rate_hz"])
    if start < 0 or end <= start or rate <= 0:
        raise ValueError("Invalid aLigner source sample interval")
    return start, end - 1, rate


def _read_slim_mocap_entry(
    entry_data: dict[str, Any],
    actor_stems: set[str],
) -> AlignedMocapEntry | None:
    raw_file = str(entry_data.get("file", "")).removesuffix(" (*)").strip()
    if not raw_file:
        return None
    file_path = Path(raw_file)
    suffix = file_path.suffix.lower()
    if suffix not in {".bvh", ".c3d", ".mcp", ".fbx"}:
        return None

    start_frame = entry_data.get("local_start_frame")
    end_frame = entry_data.get("local_end_frame")
    raw_rate = entry_data.get("output_fps") or entry_data.get("sample_rate")
    if start_frame is None or end_frame is None:
        return None

    sample_rate = float(raw_rate) if raw_rate is not None else 120.0
    normalized_rate = _normalize_mocap_sample_rate(sample_rate)
    local_start_sec = entry_data.get("local_start_sec")
    local_end_sec = entry_data.get("local_end_sec")
    if (
        normalized_rate != sample_rate
        and local_start_sec is not None
        and local_end_sec is not None
    ):
        start_frame = int(round(float(local_start_sec) * normalized_rate))
        end_frame = int(round(float(local_end_sec) * normalized_rate))

    start_frame, end_frame, normalized_rate = _contract_range(entry_data, start_frame, end_frame, normalized_rate)

    name = file_path.name
    stem = file_path.stem
    if len(file_path.parts) == 1 and stem.lower() in actor_stems:
        source_path = Path(ACTORS_FOLDER_NAME) / name
    else:
        source_path = file_path

    return AlignedMocapEntry(
        name=name,
        stem=stem,
        source_path=source_path,
        start_frame=int(start_frame),
        end_frame=int(end_frame),
        sample_rate=normalized_rate,
    )


def _read_mocap_entry(entry_data: dict[str, Any]) -> AlignedMocapEntry | None:
    derived_track = _first_mocap_derived_track(entry_data)

    if derived_track is not None:
        start_frame = derived_track.get("local_start_frame")
        end_frame = derived_track.get("local_end_frame")
        sample_rate = derived_track.get("sample_rate")
        source_path = entry_data.get("source_path") or derived_track.get("path")
        name = entry_data.get("name") or derived_track.get("name")
    else:
        start_frame = entry_data.get("0_local_start_frame")
        end_frame = entry_data.get("0_local_end_frame")
        sample_rate = entry_data.get("0_sample_rate")
        source_path = entry_data.get("source_path") or entry_data.get("0_track_path")
        name = entry_data.get("name") or Path(str(source_path)).name

    stem = entry_data.get("stem") or Path(str(name)).stem

    if (
        start_frame is None
        or end_frame is None
        or sample_rate is None
        or source_path is None
    ):
        return None

    raw_rate = float(sample_rate)
    normalized_rate = _normalize_mocap_sample_rate(raw_rate)
    timing = entry_data.get("timing")
    if normalized_rate != raw_rate and isinstance(timing, dict):
        local_start_sec = timing.get("local_start_sec")
        local_end_sec = timing.get("local_end_sec")
        if local_start_sec is not None and local_end_sec is not None:
            start_frame = int(round(float(local_start_sec) * normalized_rate))
            end_frame = int(round(float(local_end_sec) * normalized_rate))

    start_frame, end_frame, normalized_rate = _contract_range(
        derived_track or entry_data, start_frame, end_frame, normalized_rate)

    return AlignedMocapEntry(
        name=str(name),
        stem=str(stem),
        source_path=Path(str(source_path)),
        start_frame=int(start_frame),
        end_frame=int(end_frame),
        sample_rate=normalized_rate,
    )


def _first_mocap_derived_track(entry_data: dict[str, Any]) -> dict[str, Any] | None:
    derived_tracks = entry_data.get("derived_tracks")
    if not isinstance(derived_tracks, list):
        return None

    for derived_track in derived_tracks:
        if not isinstance(derived_track, dict):
            continue
        if str(derived_track.get("track_type", "")).lower() == "mocap":
            return derived_track

    return (
        derived_tracks[0]
        if derived_tracks and isinstance(derived_tracks[0], dict)
        else None
    )


def _hsl_path(path: Path) -> str:
    return str(path).replace("\\", "/")
