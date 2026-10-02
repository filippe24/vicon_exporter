"""Optional scene exports, independent of the individual prop output group."""

from pathlib import Path
from tempfile import TemporaryDirectory

import yaml

from configuration.settings import ALIGNED_EXPORT_FOLDER_NAME
from exporter.aligned_props_pipeline import generate_aligned_props_hsl, read_prop_crop
from wrapper.shogun_runner import run_shogun


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
for ($i = 0; $i < `getCount $free`; $i += 1)
{{
    $free_visible = 0;
    $free_keys = `getKeys Translation -onMod $free[$i]`;
    for ($j = 0; $j < `getCount $free_keys`; $j += 1)
    {{
        if ($free_keys[$j] >= {start} && $free_keys[$j] <= {end})
        {{
            $free_visible = 1;
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


def export_aligned_scene_extras(
    take_dir: Path,
    source_mcp: Path,
    shogun_path: Path,
    *,
    combined: bool = False,
    calibration_markers: bool = False,
    policy: str = "first",
    overwrite: bool = False,
) -> str | None:
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
        return warning
    for folder in (props, root / "scripts", root / "reports"):
        folder.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="scene_extras_", dir=root) as temp:
        stage = Path(temp)
        individuals = stage / "individuals"
        individuals.mkdir()
        script = root / "scripts" / "aligned_scene_extras.hsl"
        hsl = ""
        if "all_props" in pending:
            hsl += generate_aligned_props_hsl(
                individuals, start, end, combined_path=stage / "all_props.c3d"
            )
        if "calibration_markers" in pending:
            hsl += generate_unassigned_hsl(
                stage / "calibration_markers.c3d", start, end
            )
        script.write_text(hsl)
        run_shogun(source_mcp, script, stage / "output.mcp", shogun_path)
        occupied = {p.name.casefold() for p in props.iterdir()}
        occupied.update(p.name.casefold() for p in individuals.glob("*.c3d"))
        for key in sorted(pending):
            staged = stage / f"{key}.c3d"
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
                "source_mcp": str(source_mcp),
                "aligner_export_yaml": str(source),
                "start_frame": start,
                "end_frame": end,
                "warning": warning,
            },
            sort_keys=False,
        )
    )
    return warning
