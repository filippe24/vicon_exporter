"""MetaHuman export using Vicon's supplied automatic UE5 setup scripts."""

from pathlib import Path
from tempfile import TemporaryDirectory

from wrapper.shogun_runner import resolve_shogun_path, run_shogun

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SETUP_SCRIPT = "SetupRetargetToUE5Mannequin.hsl"


def _hsl_path(path: Path) -> str:
    value = path.resolve().as_posix()
    if any(char in value for char in ('"', "\n", "\r")):
        raise ValueError(f"Path cannot be represented in HSL: {path}")
    return value


def generate_metahuman_vicon_hsl(
    *,
    target_fbx: Path,
    scripts_dir: Path,
    output_fbx: Path,
    frame_range: tuple[int, int] | None = None,
    actor_name: str | None = None,
) -> str:
    if frame_range is not None and frame_range[1] < frame_range[0]:
        raise ValueError("Aligned end frame precedes start frame")
    play_range = (
        "" if frame_range is None else f"playRange {frame_range[0]} {frame_range[1]};\n"
    )
    isolation = ""
    if actor_name is not None:
        if not actor_name or any(
            char in actor_name for char in ('"', "\\", "\n", "\r", "*", "?")
        ):
            raise ValueError("Invalid actor name for HSL selection")
        isolation = f'''// MCP selected saves may still contain the entire scene.
select;
selectByType Character;
string $vicon_all_characters[] = `getModules -sel`;
select;
selectByName "{actor_name}*" -type Character;
if( `getNumModules -sel` != 1 )
{{
    print "Cannot uniquely identify actor {actor_name} in the MCP." -error;
    print $vicon_all_characters;
    return;
}}
string $vicon_keep_character = `getModule`;
int $vicon_actor_index;
for ($vicon_actor_index = 0; $vicon_actor_index < `getCount $vicon_all_characters`; $vicon_actor_index += 1)
{{
    if ($vicon_all_characters[$vicon_actor_index] != $vicon_keep_character)
    {{
        select $vicon_all_characters[$vicon_actor_index];
        SelectChildren_Add_All;
        delete;
    }}
}}
'''
    return f'''// Vicon Shogun Post 1.21 documented MetaHuman/UE5 setup workflow.
// Input must contain one solved standard Shogun VSS subject.
{isolation}select;
selectByType Character;
if( `getNumModules -sel` != 1 )
{{
    print "Vicon MetaHuman export requires exactly one subject." -error;
    return;
}}
string $vicon_subject = `getModule`;
selectByType SolvingSetup;
if( `getNumModules -sel` != 1 )
{{
    print "Vicon MetaHuman export requires a solved standard Shogun VSS." -error;
    return;
}}

// Build a fresh target setup, independently of the legacy saved VSR.
selectByType RetargetingSetup;
if( `getNumModules -sel` > 0 )
{{
    SelectChildren_Add_All;
    delete;
}}
select $vicon_subject;
setCurrentSubject $vicon_subject;
fbxImportOptions -asSolving false -importToCurrentSubject true -removeNamespaces true -stripCharacterNameFromChildren true;
loadFile -importType "curClipCreateNew" "{_hsl_path(target_fbx)}";
fbxImportOptions -importToCurrentSubject false;

selectByName "Retargeting" -type RetargetingSetup;
if( `getNumModules -sel` != 1 )
{{
    print "FBX import did not create a single Retargeting setup." -error;
    return;
}}
string $vicon_target = `getModule`;
selectByName "root" -type RetargetingBone -childOf $vicon_target;
if( `getNumModules -sel` != 1 )
{{
    print "Target FBX must contain one retarget root bone." -error;
    return;
}}
selectByName "pelvis" -type RetargetingBone -childOf $vicon_target;
if( `getNumModules -sel` != 1 )
{{
    print "Target FBX must contain one retarget pelvis bone." -error;
    return;
}}

// Register the installed scripts, including the main script's helpers.
addScriptPath "{_hsl_path(scripts_dir)}" -reparse;
SetupRetargetToUE5Mannequin;

// Apply the export range after setup, then export only the target hierarchy.
{play_range}select $vicon_subject;
setCurrentSubject $vicon_subject;
retarget -selectedCharacters;
select $vicon_target;
SelectChildren_Add_All;
saveFile -s "{_hsl_path(output_fbx)}";
'''


def export_metahuman_vicon_actor(
    *,
    actor_mcp: Path,
    target_fbx: Path,
    scripts_dir: Path | None,
    output_dir: Path,
    generated_scripts_dir: Path,
    actor_name: str,
    shogun_path: Path,
    frame_range: tuple[int, int] | None = None,
    overwrite: bool = False,
) -> Path | None:
    suffix = "_aligned" if frame_range is not None else ""
    output_fbx = output_dir / f"{actor_name}_metahuman_vicon{suffix}.fbx"
    if output_fbx.exists() and not overwrite:
        print(f"   keeping {output_fbx.name}")
        return output_fbx
    if not actor_mcp.is_file():
        raise FileNotFoundError(
            f"Actor MCP missing: {actor_mcp}. Run classic export first."
        )
    target_fbx = target_fbx if target_fbx.is_absolute() else PROJECT_ROOT / target_fbx
    if not target_fbx.is_file() or target_fbx.suffix.lower() != ".fbx":
        raise FileNotFoundError(f"UE5 target FBX missing or invalid: {target_fbx}")
    resolved_shogun = resolve_shogun_path(shogun_path)
    if scripts_dir is None:
        scripts_dir = resolved_shogun.parent / "Scripts" / "Retargeting"
    elif not scripts_dir.is_absolute():
        scripts_dir = PROJECT_ROOT / scripts_dir
    if not (scripts_dir / SETUP_SCRIPT).is_file():
        raise FileNotFoundError(
            f"Vicon setup script missing: {scripts_dir / SETUP_SCRIPT}"
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    generated_scripts_dir.mkdir(parents=True, exist_ok=True)
    hsl_file = generated_scripts_dir / f"{actor_name}_metahuman_vicon{suffix}.hsl"
    # A failed setup must not appear successful because an older FBX exists.
    # Commit the new FBX only after Shogun has actually produced it.
    with TemporaryDirectory(prefix="vicon_metahuman_", dir=output_dir) as working_dir:
        staged_fbx = Path(working_dir) / output_fbx.name
        hsl_file.write_text(
            generate_metahuman_vicon_hsl(
                target_fbx=target_fbx,
                scripts_dir=scripts_dir,
                output_fbx=staged_fbx,
                frame_range=frame_range,
                actor_name=actor_name,
            )
        )
        try:
            run_shogun(
                mcp_file=actor_mcp,
                hsl_file=hsl_file,
                out_file=Path(working_dir) / "retargeted.mcp",
                shogun_path=resolved_shogun,
            )
            if not staged_fbx.is_file():
                raise RuntimeError(
                    f"Vicon setup produced no FBX. Inspect {hsl_file} and the Shogun log."
                )
            staged_fbx.replace(output_fbx)
        finally:
            # Leave a reusable script with the permanent output path.
            hsl_file.write_text(
                generate_metahuman_vicon_hsl(
                    target_fbx=target_fbx,
                    scripts_dir=scripts_dir,
                    output_fbx=output_fbx,
                    frame_range=frame_range,
                    actor_name=actor_name,
                )
            )
    return output_fbx
