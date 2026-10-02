"""Export Vicon props using the C3D crop windows saved by aLigner."""

from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from configuration.settings import ALIGNED_EXPORT_FOLDER_NAME
from exporter.aligned_export_pipeline import (
    _find_aligner_export_yaml,
    _read_mocap_entries,
)
from wrapper.shogun_runner import run_shogun


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
) -> str:
    hsl = f'''// Keep props with at least one marker sample inside the inclusive crop.
playRange {start} {end};
select ;
selectProps;
// selectProps already selects the prop roots. Props are not necessarily
// Character modules, so do not filter this list by module type.
string $props[] = `getModules -selected`;
int $included[];
int $p;
int $m;
int $k;
int $visible;
string $markers[];
int $keys[];
string $filename;
for ($p = 0; $p < `getCount $props`; $p += 1)
{{
    select ;
    // Match the established clapperboard / eye-tracker export sequence:
    // select the prop root, then add its whole hierarchy to the selection.
    select $props[$p];
    selectChildren -recursive -a $props[$p];
    $markers = `getModules -selected -type Marker`;
    $visible = 0;
    for ($m = 0; $m < `getCount $markers`; $m += 1)
    {{
        if ($visible == 0)
        {{
            // getKeys Translation returns the marker's translation-key frames.
            // Do not use hasKey here: it requires a single channel such as
            // TranslationX and rejects the aggregate Translation property.
            $keys = `getKeys Translation -onMod $markers[$m]`;
            for ($k = 0; $k < `getCount $keys`; $k += 1)
            {{
                if ($keys[$k] >= {start} && $keys[$k] <= {end})
                {{
                    $visible = 1;
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
    }}
    else
    {{
        print ("Skipped prop (no marker samples in crop): " + $props[$p]);
    }}
    $included[$p] = $visible;
}}
select ;
'''
    if combined_path is not None:
        hsl += f'''// Collect exactly the props accepted by the visibility filter.
int $combined_count = 0;
for ($p = 0; $p < `getCount $props`; $p += 1)
{{
    if ($included[$p] == 1)
    {{
        select -a $props[$p];
        selectChildren -recursive -a $props[$p];
        $combined_count += 1;
    }}
}}
if ($combined_count > 0)
{{
    c3dExportOptions -collapseSubjects true -preserveGaps true -writeUnlabeled false;
    saveFile -s "{combined_path.as_posix()}";
}}
select ;
'''
    return hsl


def export_aligned_props(
    take_dir: Path,
    source_mcp: Path,
    shogun_path: Path,
    *,
    policy: str = "first",
    overwrite: bool = False,
) -> str | None:
    source, entries, start, end, warning = read_prop_crop(take_dir, policy)
    root = take_dir / ALIGNED_EXPORT_FOLDER_NAME
    output_dir = root / "props"
    if not overwrite and output_dir.exists() and any(output_dir.iterdir()):
        print(f"   keeping existing aligned prop exports: {output_dir}")
        return warning
    scripts = root / "scripts"
    reports = root / "reports"
    for directory in (output_dir, scripts, reports):
        directory.mkdir(parents=True, exist_ok=True)
    script = scripts / "aligned_export_props.hsl"
    print(f"   exporting aligned props: {start} -> {end}")
    # Stage the entire selected group so failed runs preserve previous exports,
    # and a successful overwrite removes props no longer visible in the crop.
    with TemporaryDirectory(prefix="props_", dir=root) as staging:
        staging_dir = Path(staging)
        script.write_text(generate_aligned_props_hsl(staging_dir, start, end))
        run_shogun(source_mcp, script, staging_dir / "output.mcp", shogun_path)
        from exporter.aligned_scene_extras import protect_extra_names

        extra_names = protect_extra_names(
            root, {p.name.casefold() for p in staging_dir.glob("*.c3d")}
        )
        for old_file in output_dir.glob("*.c3d"):
            if old_file.name.casefold() not in extra_names:
                old_file.unlink()
        for new_file in staging_dir.glob("*.c3d"):
            new_file.replace(output_dir / new_file.name)
    script.write_text(generate_aligned_props_hsl(output_dir, start, end))
    (reports / "aligned_props_summary.yaml").write_text(
        yaml.safe_dump(
            {
                "aligner_export_yaml": str(source),
                "source_mcp": str(source_mcp),
                "crop_policy": policy,
                "start_frame": start,
                "end_frame": end,
                "c3d_ranges": [
                    {
                        "name": e.name,
                        "start_frame": e.start_frame,
                        "end_frame": e.end_frame,
                    }
                    for e in entries
                ],
                "warning": warning,
            },
            sort_keys=False,
        )
    )
    return warning
