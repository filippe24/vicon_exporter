"""Export Vicon props using the C3D crop windows saved by aLigner."""

import os
from pathlib import Path
from uuid import uuid4

import yaml

from configuration.settings import ALIGNED_EXPORT_FOLDER_NAME
from exporter.aligned_export_pipeline import (
    _find_aligner_export_yaml,
    _read_mocap_entries,
)
from exporter.aligned_group import Part
from exporter.export_status import record_step


def read_prop_crop(take_dir: Path, policy: str = "first"):
    if policy not in {"first", "extremes"}:
        raise ValueError(f"Unknown prop crop policy: {policy}")
    source = _find_aligner_export_yaml(take_dir)
    if source is None:
        raise ValueError(f"No aLigner export YAML found in {take_dir}")
    entries = [
        entry
        for entry in _read_mocap_entries(yaml.safe_load(source.read_text()) or {})
        if entry.source_path.suffix.lower() == ".c3d"
    ]
    if not entries:
        raise ValueError(f"No C3D crop entries found in {source}")
    if any(entry.end_frame < entry.start_frame for entry in entries):
        raise ValueError(f"Invalid C3D crop range in {source}")
    if len({entry.sample_rate for entry in entries}) != 1:
        raise ValueError(
            f"C3D sample rates differ in {source}; frame ranges cannot be combined"
        )
    start, end = entries[0].start_frame, entries[0].end_frame
    if policy == "extremes":
        start = min(entry.start_frame for entry in entries)
        end = max(entry.end_frame for entry in entries)
    warning = None
    if len({(entry.start_frame, entry.end_frame) for entry in entries}) > 1:
        details = ", ".join(f"{e.name}: {e.start_frame}–{e.end_frame}" for e in entries)
        warning = f"{take_dir}: C3D crop ranges differ ({details}); using {policy}: {start}–{end}."
    return source, entries, start, end, warning


def generate_aligned_props_hsl(
    output_dir: Path,
    start: int,
    end: int,
    *,
    combined_path: Path | None = None,
    diagnostics: bool | None = None,
) -> str:
    if diagnostics is None:
        diagnostics = os.environ.get("VICON_EXPORTER_DIAGNOSTICS", "").lower() in {
            "1",
            "true",
            "yes",
            "on",
        }
    prop_trace = 'print ("DIAG prop: " + $props[$p]);' if diagnostics else ""
    marker_trace = 'print ("DIAG marker: " + $markers[$m]);' if diagnostics else ""
    count_trace = (
        'print "DIAG trajectory boundary count:"; print $num_keys;'
        if diagnostics
        else ""
    )
    selection_name = f"exporter_props_{uuid4().hex}"
    setup = f'selectionSet "{selection_name}";\n' if combined_path else ""
    collect = f'selectionSet "{selection_name}" -add;' if combined_path else ""
    hsl = f'''// Keep props with at least one marker sample inside the inclusive crop.
playRange {start} {end};
select ;
{setup}
selectProps;
// selectProps already selects the prop roots. Props are not necessarily
// Character modules, so do not filter this list by module type.
string $props[] = `getModules -selected`;
int $num_props = `getCount $props`;
int $p;
int $m;
int $k;
int $visible;
int $num_markers;
int $num_keys;
int $range_start;
int $range_end;
string $markers[];
int $keys[];
string $filename;
for ($p = 0; $p < $num_props; $p += 1)
{{
    {prop_trace}
    select ;
    // Match the established clapperboard / eye-tracker export sequence:
    // select the prop root, then add its whole hierarchy to the selection.
    select $props[$p];
    selectChildren -recursive -a $props[$p];
    $markers = `getModules -selected -type Marker`;
    $num_markers = `getCount $markers`;
    $visible = 0;
    for ($m = 0; $m < $num_markers; $m += 1)
    {{
        if ($visible == 0)
        {{
            {marker_trace}
            // Trajectory intervals avoid materializing every frame of a long take.
            $keys = `getTrajectories $markers[$m]`;
            $num_keys = `getCount $keys`;
            {count_trace}
            for ($k = 0; $k < $num_keys; $k += 2)
            {{
                if ($k + 1 < $num_keys)
                {{
                    $range_start = $keys[$k];
                    $range_end = $keys[$k + 1];
                    if ($range_start <= {end} && $range_end >= {start})
                    {{
                        $visible = 1;
                    }}
                }}
            }}
        }}
    }}
    if ($visible == 1)
    {{
        // Keep the root and all children selected for the C3D export.
        $filename = ("{output_dir.as_posix()}/" + $props[$p] + ".c3d");
        saveFile -s $filename;
        print ("Exported prop: " + $props[$p]);
        {collect}
    }}
    else
    {{
        print ("Skipped prop (no marker samples in crop): " + $props[$p]);
    }}
}}
select ;
'''
    if combined_path is not None:
        hsl += f'''// Collect exactly the hierarchies accepted by the filter.
selectSet "{selection_name}";
if (`getNumModules -sel` > 0)
{{
    c3dExportOptions -collapseSubjects true -preserveGaps true -writeUnlabeled false;
    saveFile -s "{combined_path.as_posix()}";
}}
select ;
selectionSet "{selection_name}" -delete;
'''
    return hsl


def aligned_props_part(
    take_dir: Path,
    stage: Path,
    *,
    policy: str = "first",
    overwrite: bool = False,
) -> Part | None:
    """Shogun saves the props into `stage`; finish() then replaces the whole group, so a failed run
    keeps the previous exports and a successful one removes props no longer visible in the crop."""
    source, entries, start, end, warning = read_prop_crop(take_dir, policy)
    root = take_dir / ALIGNED_EXPORT_FOLDER_NAME
    output_dir = root / "props"
    if not overwrite and output_dir.exists() and any(output_dir.iterdir()):
        print(f"   keeping existing aligned prop exports: {output_dir}")
        return None
    staging_dir = stage / "props"
    staging_dir.mkdir(parents=True)
    print(f"   aligned props: {start} -> {end}")

    def finish():
        from exporter.aligned_scene_extras import protect_extra_names

        exported = sorted(staging_dir.glob("*.c3d"))
        if exported:
            print(f"   Exported {len(exported)} aligned prop C3D files.")
        else:
            print("   no visible data: no props had marker samples in the crop.")
        reports = root / "reports"
        for directory in (output_dir, reports):
            directory.mkdir(parents=True, exist_ok=True)
        extra_names = protect_extra_names(root, {path.name.casefold() for path in exported})
        for old_file in output_dir.glob("*.c3d"):
            if old_file.name.casefold() not in extra_names:
                old_file.unlink()
        for new_file in exported:
            new_file.replace(output_dir / new_file.name)
        (reports / "aligned_props_summary.yaml").write_text(
            yaml.safe_dump(
                {
                    "aligner_export_yaml": str(source),
                    "crop_policy": policy,
                    "start_frame": start,
                    "end_frame": end,
                    "c3d_ranges": [
                        {"name": e.name, "start_frame": e.start_frame, "end_frame": e.end_frame}
                        for e in entries
                    ],
                    "warning": warning,
                },
                sort_keys=False,
            )
        )
        record_step(take_dir, "props", crop_policy=policy)

    return Part("props", ["props"], generate_aligned_props_hsl(staging_dir, start, end), finish, warning)
