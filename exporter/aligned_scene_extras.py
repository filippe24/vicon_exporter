"""Optional scene exports, independent of the individual prop output group."""

from pathlib import Path

import yaml

from configuration.settings import ALIGNED_EXPORT_FOLDER_NAME
from exporter.aligned_group import Part
from exporter.aligned_props_pipeline import generate_aligned_props_hsl, read_prop_crop
from exporter.export_status import record_step


def read_extra_outputs(root: Path) -> dict[str, str]:
    report = root / "reports" / "aligned_scene_extras.yaml"
    return (
        (yaml.safe_load(report.read_text()) or {}).get("outputs", {})
        if report.exists()
        else {}
    )


def unique_extra_name(base: str, occupied: set[str]) -> str:
    name = f"{base}.c3d"
    index = 1
    while name.casefold() in occupied:
        name = f"{base}_{index}.c3d"
        index += 1
    return name


def generate_unassigned_hsl(path: Path, start: int, end: int) -> str:
    return f'''// Vicon's documented selector for unlabeled trajectories.
playRange {start} {end};
select ;
selectByName "_*" -type Marker;
string $free[] = `getModules -selected -type Marker`;
select ;
int $i;
int $j;
int $free_keys[];
int $free_visible;
int $free_count = 0;
int $num_free = `getCount $free`;
int $num_free_keys;
int $free_start;
int $free_end;
for ($i = 0; $i < $num_free; $i += 1)
{{
    $free_visible = 0;
    $free_keys = `getTrajectories $free[$i]`;
    $num_free_keys = `getCount $free_keys`;
    for ($j = 0; $j < $num_free_keys; $j += 2)
    {{
        if ($j + 1 < $num_free_keys)
        {{
            $free_start = $free_keys[$j];
            $free_end = $free_keys[$j + 1];
            if ($free_start <= {end} && $free_end >= {start})
            {{
                $free_visible = 1;
            }}
        }}
    }}
    if ($free_visible == 1)
    {{
        select -a $free[$i];
        $free_count += 1;
    }}
}}
if ($free_count > 0)
{{
    c3dExportOptions -writeUnlabeled true -preserveGaps true -filterMin false -filterMax false;
    saveFile -s "{path.as_posix()}";
}}
select ;
'''


def protect_extra_names(root: Path, incoming: set[str]) -> set[str]:
    outputs = read_extra_outputs(root)
    occupied = incoming | {p.name.casefold() for p in (root / "props").iterdir()}
    changed = False
    for key, name in list(outputs.items()):
        path = root / "props" / name
        if name.casefold() in incoming and path.exists():
            replacement = unique_extra_name(f"__vicon_exporter_{key}__", occupied)
            path.replace(path.with_name(replacement))
            outputs[key] = replacement
            occupied.add(replacement.casefold())
            changed = True
    if changed:
        report = root / "reports" / "aligned_scene_extras.yaml"
        data = yaml.safe_load(report.read_text()) or {}
        data["outputs"] = outputs
        report.write_text(yaml.safe_dump(data, sort_keys=False))
    return {name.casefold() for name in outputs.values()}


def aligned_scene_extras_part(
    take_dir: Path,
    stage: Path,
    *,
    combined: bool = False,
    calibration_markers: bool = False,
    policy: str = "first",
    overwrite: bool = False,
) -> Part | None:
    if calibration_markers and not any(
        "calibration" in p.lower() for p in take_dir.parts
    ):
        print(f"   skipping unassigned markers: {take_dir} is not a calibration take")
        calibration_markers = False
    if not combined and not calibration_markers:
        return None
    source, _, start, end, warning = read_prop_crop(take_dir, policy)
    root = take_dir / ALIGNED_EXPORT_FOLDER_NAME
    props = root / "props"
    outputs = read_extra_outputs(root)
    requested = {
        key
        for key, enabled in (
            ("all_props", combined),
            ("calibration_markers", calibration_markers),
        )
        if enabled
    }
    pending = {
        key
        for key in requested
        if overwrite or key not in outputs or not (props / outputs[key]).exists()
    }
    if not pending:
        print("   keeping existing aligned scene extras")
        return None
    work = stage / "scene_extras"
    individuals = work / "individuals"
    individuals.mkdir(parents=True)
    hsl = ""
    if "all_props" in pending:
        hsl += generate_aligned_props_hsl(
            individuals, start, end, combined_path=work / "all_props.c3d"
        )
    if "calibration_markers" in pending:
        hsl += generate_unassigned_hsl(work / "calibration_markers.c3d", start, end)
    print(f"   aligned scene extras ({', '.join(sorted(pending))}): {start} -> {end}")

    def finish():
        for folder in (props, root / "reports"):
            folder.mkdir(parents=True, exist_ok=True)
        # The props part may have renamed an extra since, so read the names again.
        outputs = read_extra_outputs(root)
        occupied = {p.name.casefold() for p in props.iterdir()}
        occupied.update(p.name.casefold() for p in individuals.glob("*.c3d"))
        for key in sorted(pending):
            staged = work / f"{key}.c3d"
            if not staged.exists():
                old_name = outputs.pop(key, None)
                if old_name:
                    (props / old_name).unlink(missing_ok=True)
                print(f"   no visible data for {key}; no C3D written")
                continue
            old_name = outputs.get(key)
            if old_name and old_name.casefold() not in {
                p.name.casefold() for p in individuals.glob("*.c3d")
            }:
                occupied.discard(old_name.casefold())
            name = unique_extra_name(f"__vicon_exporter_{key}__", occupied)
            staged.replace(props / name)
            if old_name and old_name != name:
                (props / old_name).unlink(missing_ok=True)
            outputs[key] = name
            occupied.add(name.casefold())
            print(f"   scene export: {props / name}")
        (root / "reports" / "aligned_scene_extras.yaml").write_text(
            yaml.safe_dump(
                {
                    "outputs": outputs,
                    "aligner_export_yaml": str(source),
                    "start_frame": start,
                    "end_frame": end,
                    "warning": warning,
                },
                sort_keys=False,
            )
        )
        for key in sorted(pending):
            record_step(take_dir, key, crop_policy=policy)

    return Part("scene extras", sorted(pending), hsl, finish, warning)
