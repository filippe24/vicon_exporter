# # main.py

import argparse
import shutil
import sys
from pathlib import Path
from tkinter import Tk, filedialog

from bvh.converter import convert
from configuration.settings import (
    ACTORS_FOLDER_NAME,
    EXPORT_FOLDER_NAME,
    GEENO_VICON_RETARGET,
    METAHUMAN_VICON_SCRIPTS_DIR,
    METAHUMAN_VICON_TARGET_FBX,
    PROCESSED_MCP_NAME,
    SHOGUN_PATH,
)
from configuration.types import RETARGET_CONFIGS, RetargetType
from exporter.aligned_export_pipeline import (
    create_aligned_export_dirs,
    generate_aligned_actor_export_hsl,
    generate_aligned_retarget_hsl,
    load_aligned_export_plan,
    write_aligned_export_summary,
)
from exporter.export_pipeline import (
    DEFAULT_TRACKING_PROP_EXPORTS,
    TrackingPropExport,
    generate_extra_exports_hsl,
    generate_hsl,
)
from exporter.geeno_retarget_pipeline import generate_geeno_retarget_hsl
from exporter.general_retarget_pipeline import generate_general_retarget_hsl
from exporter.mannequin_retarget_pipeline import generate_mannequin_retarget_hsl
from exporter.metahuman_vicon_pipeline import export_metahuman_vicon_actor
from ui.menu import open_menu
from utils.file_search import find_take_folders
from utils.rename_face_videos import rename_face_videos
from wrapper.shogun_runner import ShogunError, run_shogun


def parse_args():
    parser = argparse.ArgumentParser(description="vicon exporter")
    parser.add_argument(
        "-f",
        "--force",
        action="store_true",
        help="force reprocessing even if output already exists",
    )
    parser.add_argument(
        "-r",
        "--retarget",
        action="store_true",
        help="run retargeting pass after export",
    )
    return parser.parse_args()


def print_pyramid():
    purple = "\033[35m"
    blue = "\033[36m"
    yellow = "\033[33m"
    reset = "\033[0m"
    bold = "\033[1m"

    lines = [
        (purple, "             vicon exporter"),
        (purple, "          ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓"),
        (purple, "               ▓▓▓▓▓▓▓▓▓▓▓▓"),
        (blue, "             ▓▓▓ ▓▓▓▓▓▓▓▓▓▓"),
        (yellow, "                     ▓▓▓▓▓▓"),
    ]

    print()
    for color, text in lines:
        print(color + bold + text + reset)
    print()


def choose_folder() -> Path | None:
    root = Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="select take folder.")
    root.destroy()
    return Path(folder) if folder else None


def _run_shogun_with_bvh_fallback(
    *,
    mcp_file: Path,
    hsl_file: Path,
    out_file: Path,
    shogun_path: Path,
    static_bvh_hsl_file: Path,
    static_bvh_hsl_content: str,
    fallback_hsl_file: Path,
    fallback_hsl_content: str,
) -> bool:
    try:
        run_shogun(
            mcp_file=mcp_file,
            hsl_file=hsl_file,
            out_file=out_file,
            shogun_path=shogun_path,
        )
        return True
    except ShogunError as error:
        if not _is_unsupported_bvh_export_error(error):
            raise

        print("   warning: Shogun could not export BVH for this skeleton.")
        print("   trying static-hand BVH fallback.")
        static_bvh_hsl_file.write_text(static_bvh_hsl_content)
        print(f"   hsl created {static_bvh_hsl_file.name}.")

        try:
            run_shogun(
                mcp_file=mcp_file,
                hsl_file=static_bvh_hsl_file,
                out_file=out_file,
                shogun_path=shogun_path,
            )
        except ShogunError as static_bvh_error:
            print(f"   warning: static-hand BVH fallback failed: {static_bvh_error}")
        else:
            print("   warning: BVH exported with static hand/finger fallback.")
            return True

        print("   retrying this take without BVH so C3D, FBX, and MCP still export.")
        fallback_hsl_file.write_text(fallback_hsl_content)
        print(f"   hsl created {fallback_hsl_file.name}.")

        run_shogun(
            mcp_file=mcp_file,
            hsl_file=fallback_hsl_file,
            out_file=out_file,
            shogun_path=shogun_path,
        )
        print(
            "   warning: BVH skipped. Use a BVH-friendly character, or retarget/"
            "convert from FBX if BVH is required for this take."
        )
        return False


def _is_unsupported_bvh_export_error(error: ShogunError) -> bool:
    output = error.output.lower()
    return (
        ".bvh" in output
        and "failed to save file" in output
        and (
            "multiple zero dof end bones" in output
            or "not supported by the bvh format" in output
        )
    )


def _process_take_legacy(
    take_dir: Path,
    shogun_path: Path,
    force: bool,
    include_tracking_props: bool = False,
):
    processed_file = take_dir / PROCESSED_MCP_NAME
    if processed_file.exists() and not force:
        print(f"⏭   skipping {take_dir.name} (already processed).")
        return
    export_dir = take_dir / EXPORT_FOLDER_NAME
    if export_dir.exists() and not force:
        print(f"  skipping {take_dir.name} (export folder already exists).")
        return

    if force:
        if processed_file.exists():
            processed_file.unlink()
        if export_dir.exists():
            shutil.rmtree(export_dir)

    print(f"\n📁 selected folder: {take_dir}.")
    print("looking for for .mcp file.")
    mcp: Path = next(take_dir.glob("*.mcp"))
    print(f"   found: {mcp.name}.")

    print("📂 creating export folders.")
    # export_dir = take_dir / "exported"
    export_dir = take_dir / EXPORT_FOLDER_NAME
    export_dir.mkdir(exist_ok=True)
    # actors_folder: str = "actors"
    actors_folder: str = ACTORS_FOLDER_NAME
    (export_dir / actors_folder).mkdir(exist_ok=True)
    print("   export folders created.")

    print("generating hsl file.")
    hsl_content = generate_hsl(
        export_dir,
        actors_folder,
        include_tracking_props=include_tracking_props,
        include_calibration_markers=(
            include_tracking_props and _is_calibration_take(take_dir)
        ),
    )
    hsl_file = take_dir / "exporter.hsl"
    hsl_file.write_text(hsl_content)
    print(f"   hsl created {hsl_file.name}.")

    out_file = take_dir / PROCESSED_MCP_NAME

    print("running shogun processing.")
    exported_bvh = _run_shogun_with_bvh_fallback(
        mcp_file=mcp,
        hsl_file=hsl_file,
        out_file=out_file,
        shogun_path=shogun_path,
        static_bvh_hsl_file=take_dir / "exporter_static_hands_bvh.hsl",
        static_bvh_hsl_content=generate_hsl(
            export_dir,
            actors_folder,
            include_tracking_props=include_tracking_props,
            include_calibration_markers=(
                include_tracking_props and _is_calibration_take(take_dir)
            ),
            static_hand_bvh=True,
        ),
        fallback_hsl_file=take_dir / "exporter_without_bvh.hsl",
        fallback_hsl_content=generate_hsl(
            export_dir,
            actors_folder,
            include_tracking_props=include_tracking_props,
            include_calibration_markers=(
                include_tracking_props and _is_calibration_take(take_dir)
            ),
            include_bvh=False,
        ),
    )
    if not exported_bvh:
        print("     complete Output saved without BVH.")
    print(f"     complete Output saved to: {out_file}\n")


def process_take(
    take_dir: Path,
    shogun_path: Path,
    force: bool,
    include_tracking_props: bool = False,
):
    processed_file = take_dir / PROCESSED_MCP_NAME
    export_dir = take_dir / EXPORT_FOLDER_NAME

    missing_tracking_prop_exports: list[TrackingPropExport] = []
    missing_calibration_markers = False
    if include_tracking_props:
        missing_tracking_prop_exports = _missing_tracking_prop_exports(export_dir)
        missing_calibration_markers = (
            _is_calibration_take(take_dir)
            and not (export_dir / "calibration_markers.c3d").exists()
        )

    has_existing_export = processed_file.exists() or (
        export_dir.exists() and any(path.is_file() for path in export_dir.rglob("*"))
    )
    has_missing_extra_exports = bool(
        missing_tracking_prop_exports or missing_calibration_markers
    )

    if has_existing_export and not force:
        if not has_missing_extra_exports:
            print(f"   skipping {take_dir.name} (already exported).")
            return

        print(f"\nselected folder: {take_dir}.")
        print("looking for original .mcp file.")
        mcp = _find_original_take_mcp(take_dir)
        if mcp is None:
            print("   no original .mcp file found, skipping.")
            return
        print(f"   found: {mcp.name}.")

        print("generating hsl file for missing extra exports.")
        hsl_content = generate_extra_exports_hsl(
            export_dir,
            tracking_prop_exports=missing_tracking_prop_exports,
            include_calibration_markers=missing_calibration_markers,
        )
        if not hsl_content or not hsl_content.strip():
            print("   no missing extra exports, skipping.")
            return

        hsl_file = take_dir / "extra_exports.hsl"
        hsl_file.write_text(hsl_content)
        print(f"   hsl created {hsl_file.name}.")

        out_file = take_dir / "extra_exports_output.mcp"
        print("running shogun extra export processing.")
        run_shogun(
            mcp_file=mcp,
            hsl_file=hsl_file,
            out_file=out_file,
            shogun_path=shogun_path,
        )
        print(f"     complete extra exports saved under: {export_dir}\n")
        return

    if force and include_tracking_props:
        missing_tracking_prop_exports = list(DEFAULT_TRACKING_PROP_EXPORTS)
        missing_calibration_markers = _is_calibration_take(take_dir)

    print(f"\nselected folder: {take_dir}.")
    print("looking for original .mcp file.")
    mcp = _find_original_take_mcp(take_dir)
    if mcp is None:
        print("   no original .mcp file found, skipping.")
        return
    print(f"   found: {mcp.name}.")

    print("creating export folders.")
    export_dir.mkdir(exist_ok=True)
    actors_folder: str = ACTORS_FOLDER_NAME
    (export_dir / actors_folder).mkdir(exist_ok=True)
    print("   export folders created.")

    print("generating hsl file.")
    hsl_content = generate_hsl(
        export_dir,
        actors_folder,
        include_tracking_props=include_tracking_props,
        include_calibration_markers=(
            include_tracking_props and _is_calibration_take(take_dir)
        ),
        tracking_prop_exports=missing_tracking_prop_exports,
    )
    hsl_file = take_dir / "exporter.hsl"
    hsl_file.write_text(hsl_content)
    print(f"   hsl created {hsl_file.name}.")

    out_file = take_dir / PROCESSED_MCP_NAME

    print("running shogun processing.")
    exported_bvh = _run_shogun_with_bvh_fallback(
        mcp_file=mcp,
        hsl_file=hsl_file,
        out_file=out_file,
        shogun_path=shogun_path,
        static_bvh_hsl_file=take_dir / "exporter_static_hands_bvh.hsl",
        static_bvh_hsl_content=generate_hsl(
            export_dir,
            actors_folder,
            include_tracking_props=include_tracking_props,
            include_calibration_markers=(
                include_tracking_props and _is_calibration_take(take_dir)
            ),
            tracking_prop_exports=missing_tracking_prop_exports,
            static_hand_bvh=True,
        ),
        fallback_hsl_file=take_dir / "exporter_without_bvh.hsl",
        fallback_hsl_content=generate_hsl(
            export_dir,
            actors_folder,
            include_tracking_props=include_tracking_props,
            include_calibration_markers=(
                include_tracking_props and _is_calibration_take(take_dir)
            ),
            tracking_prop_exports=missing_tracking_prop_exports,
            include_bvh=False,
        ),
    )
    if not exported_bvh:
        print("     complete Output saved without BVH.")
    print(f"     complete Output saved to: {out_file}\n")


def process_mannequin_retargeting(take_dir: Path, shogun_path: Path):
    print(f"\n🎯 mannequin retargeting: {take_dir}")

    export_dir = take_dir / EXPORT_FOLDER_NAME / ACTORS_FOLDER_NAME

    # find all actor .mcp files
    actor_mocaps = list(export_dir.glob("*.mcp"))
    if not actor_mocaps:
        print("   ⚠ no actor .mcp files found, skipping.")
        return

    # create retarget folder.
    retarget_dir = take_dir / EXPORT_FOLDER_NAME / "retargeted"
    retarget_dir.mkdir(exist_ok=True)

    for actor_mcp in actor_mocaps:
        print(f"   ▶ retargeting actor: {actor_mcp.name}")

        # generate retarget HSL.
        hsl_content = generate_mannequin_retarget_hsl(
            actor_source_path=actor_mcp,
            output_path=retarget_dir,
        )

        hsl_file = take_dir / f"retarget_{actor_mcp.stem}.hsl"
        hsl_file.write_text(hsl_content)

        out_file = retarget_dir / f"{actor_mcp.stem}_retargeted.mcp"

        run_shogun(
            mcp_file=actor_mcp,
            hsl_file=hsl_file,
            out_file=out_file,
            shogun_path=shogun_path,
        )


def process_geeno_retargeting(take_dir: Path, shogun_path: Path, force: bool):
    print(f"\n🤖 Geeno retargeting: {take_dir}")

    # ---------------------------------------------------------
    # 1. Determine which MCP to use (processed > original)
    # ---------------------------------------------------------
    processed_mcp = take_dir / PROCESSED_MCP_NAME
    original_mcp = _find_original_take_mcp(take_dir)

    if processed_mcp.exists():
        mcp_file = processed_mcp
    elif original_mcp is not None:
        mcp_file = original_mcp
    else:
        print("   ⚠ No MCP file found, skipping.")
        return

    print(f"   • Using MCP: {mcp_file.name}")

    # ---------------------------------------------------------
    # 2. Output folder is ALWAYS exported/actors (no geeno folder)
    # ---------------------------------------------------------
    export_root = take_dir / EXPORT_FOLDER_NAME
    actors_dir = export_root / ACTORS_FOLDER_NAME

    if not actors_dir.exists():
        print(f"   ⚠ Actors folder missing: {actors_dir}")
        return

    # ---------------------------------------------------------
    # 3. Load the VSR retarget file from project root
    # ---------------------------------------------------------
    project_root = Path(__file__).resolve().parents[0]  # vicon_exporter/
    retarget_vsr = project_root / GEENO_VICON_RETARGET

    if not retarget_vsr.exists():
        print(f"   ❌ ERROR: Geeno retarget VSR not found at: {retarget_vsr}")
        return

    print(f"   • Using retargeter: {retarget_vsr}")

    # ---------------------------------------------------------
    # 4. Generate HSL (EXPORT_DIR must be exported/)
    # ---------------------------------------------------------
    hsl_content = generate_geeno_retarget_hsl(
        output_path=export_root,
        retarget_vsr_file_path=retarget_vsr,
        actors_output_folder=ACTORS_FOLDER_NAME,
    )
    print(hsl_content)
    hsl_file = take_dir / "geeno_retarget.hsl"
    hsl_file.write_text(hsl_content)

    # ---------------------------------------------------------
    # 5. Run Shogun retargeting
    #    NOTE: Output MCP is NOT needed; Shogun will generate
    #    FBX/BVH directly into exported/actors/
    # ---------------------------------------------------------
    dummy_output_mcp = take_dir / "geeno_dummy_output.mcp"

    print("   • Running Shogun retargeting...")
    run_shogun(
        mcp_file=mcp_file,
        hsl_file=hsl_file,
        out_file=dummy_output_mcp,
        shogun_path=shogun_path,
    )

    print(f"   ✔ Geeno retarget complete → actors written to {actors_dir}")


def process_general_retargeting(
    take_dir: Path,
    shogun_path: Path,
    retarget_type: RetargetType,
    overwrite: bool = False,
):
    configuration = RETARGET_CONFIGS[retarget_type]

    print(f"\n🤖  retargeting ({configuration.name}): {take_dir}")

    # -----------------------------------------------------
    # 1.determine which MCP to use (processed > original).
    # -----------------------------------------------------
    processed_mcp = take_dir / PROCESSED_MCP_NAME
    original_mcp = _find_original_take_mcp(take_dir)

    if processed_mcp.exists():
        mcp_file = processed_mcp
    elif original_mcp is not None:
        mcp_file = original_mcp
    else:
        print("   ⚠ no MCP file found, skipping.")
        return

    print(f"   • using MCP: {mcp_file.name}")

    # -------------------------------------------
    # 2. Keep each retarget method in its own output folder.
    # -------------------------------------------
    export_root = take_dir / EXPORT_FOLDER_NAME
    folder_name = {
        RetargetType.MANNEQUIN: "metahuman_vsr",
        RetargetType.MANNEQUIN_ADJUSTED: "metahuman_legacy",
        RetargetType.GEENO: "geeno",
    }[retarget_type]
    actors_dir = export_root / "retargeted" / folder_name

    if not overwrite and any(actors_dir.glob(f"*_{configuration.output_name}_*.fbx")):
        print("   keeping existing retarget exports, skipping this output group.")
        return

    actors_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------
    # 3. load the VSR retarget file from project root.
    # ------------------------------------------------
    project_root = Path(__file__).resolve().parents[0]  # vicon_exporter/
    retarget_vsr = project_root / configuration.vsr_source_path

    if not retarget_vsr.exists():
        print(f"    ERROR: retarget VSR not found at: {retarget_vsr}")
        return

    print(f"   • using retargeter: {retarget_vsr}")

    # ---------------------------------------------------------
    # 4. Generate HSL (EXPORT_DIR must be exported/)
    # ---------------------------------------------------------
    hsl_content = generate_general_retarget_hsl(
        template_path=configuration.hsl_source_path,
        output_path=export_root,
        retarget_vsr_file_path=retarget_vsr,
        actors_output_folder=f"retargeted/{folder_name}",
        file_name_prefix=f"{configuration.output_name}_",
    )
    print(hsl_content)
    hsl_file = take_dir / f"{configuration.output_name}_retarget.hsl"
    hsl_file.write_text(hsl_content)

    # ---------------------------------------------------------
    # 5. Run Shogun retargeting
    #    NOTE: Output MCP is NOT needed; Shogun will generate
    #    FBX directly into this method's output folder.
    # ---------------------------------------------------------
    dummy_output_mcp = take_dir / f"temp_{configuration.output_name}_output.mcp"

    print("   • Running Shogun retargeting...")
    run_shogun(
        mcp_file=mcp_file,
        hsl_file=hsl_file,
        out_file=dummy_output_mcp,
        shogun_path=shogun_path,
    )

    print(
        f"   ✔ {configuration.output_name} retarget complete → actors written to {actors_dir}"
    )


def process_metahuman_vicon_retargeting(
    take_dir: Path,
    shogun_path: Path,
    *,
    target_fbx: Path = METAHUMAN_VICON_TARGET_FBX,
    aligned: bool = False,
    overwrite: bool = False,
):
    mode = "aligned" if aligned else "full take"
    print(f"\nVicon automatic MetaHuman retarget ({mode}): {take_dir}")
    if aligned:
        plan = load_aligned_export_plan(take_dir)
        if plan is None:
            return
        actors = [
            (
                entry.source_mcp_path,
                entry.actor_prefix,
                (entry.start_frame, entry.end_frame),
            )
            for entry in plan.mocap_entries
        ]
        output_dir = plan.retargeted_dir / "metahuman_vicon"
        scripts_dir = plan.scripts_dir
    else:
        export_root = take_dir / EXPORT_FOLDER_NAME
        actor_sources = {
            path.stem: path.with_suffix(".mcp")
            for extension in ("fbx", "c3d", "bvh")
            for path in sorted(
                (export_root / ACTORS_FOLDER_NAME).glob(f"*_.{extension}")
            )
        }
        actor_sources.update(
            {
                path.stem: path
                for path in sorted((export_root / ACTORS_FOLDER_NAME).glob("*_.mcp"))
            }
        )
        actors = [
            (path, path.stem.removesuffix("_"), None) for path in actor_sources.values()
        ]
        output_dir = export_root / "retargeted" / "metahuman_vicon"
        scripts_dir = export_root / "scripts"
    if not actors:
        print("   no actor MCP sources found; run classic export first.")
        return
    for actor_mcp, actor_name, frame_range in actors:
        if not actor_mcp.is_file():
            fallback = _find_retarget_source_mcp(take_dir)
            if fallback is not None:
                print(
                    f"   actor MCP missing; isolating {actor_name} from {fallback.name}"
                )
                actor_mcp = fallback
        try:
            export_metahuman_vicon_actor(
                actor_mcp=actor_mcp,
                actor_name=actor_name,
                target_fbx=target_fbx,
                scripts_dir=METAHUMAN_VICON_SCRIPTS_DIR,
                output_dir=output_dir,
                generated_scripts_dir=scripts_dir,
                shogun_path=shogun_path,
                frame_range=frame_range,
                overwrite=overwrite,
            )
        except (OSError, RuntimeError, ValueError) as error:
            print(
                f"   warning: Vicon MetaHuman export failed for {actor_name}: {error}"
            )


def process_aligned_export_and_retargeting(
    take_dir: Path,
    shogun_path: Path,
    *,
    export_standard: bool = True,
    retarget_metahuman: bool = True,
    retarget_geeno: bool = True,
    overwrite: bool = False,
):
    print(f"\nAligned export + MetaHuman + Geeno retargeting: {take_dir}")

    plan = load_aligned_export_plan(take_dir)
    if plan is None:
        return

    mcp_file = _find_retarget_source_mcp(take_dir)
    if mcp_file is None:
        print("   warning: no MCP file found, skipping.")
        return

    create_aligned_export_dirs(plan)

    print(f"   using MCP: {mcp_file.name}")
    print(f"   using aLigner YAML: {plan.export_yaml_path.name}")
    print(f"   aligned frame range: {plan.start_frame} -> {plan.end_frame}")
    print(f"   output: {plan.output_root}")

    keep_actors = not overwrite and any(plan.actors_dir.iterdir())
    if export_standard and not keep_actors:
        _export_aligned_standard(plan, mcp_file, shogun_path)
    elif export_standard:
        print("   keeping existing standard aligned exports.")

    for retarget_type, folder_name, prefix in [
        (RetargetType.MANNEQUIN, "metahuman", "metahuman_aligned"),
        (RetargetType.GEENO, "geeno", "geeno_aligned"),
    ]:
        enabled = retarget_metahuman if folder_name == "metahuman" else retarget_geeno
        if not enabled:
            continue
        output_dir = plan.retargeted_dir / folder_name
        if not overwrite and output_dir.exists() and any(output_dir.iterdir()):
            print(f"   keeping existing aligned {folder_name} exports.")
            continue
        configuration = RETARGET_CONFIGS[retarget_type]
        project_root = Path(__file__).resolve().parent
        retarget_vsr = project_root / configuration.vsr_source_path
        template_path = project_root / configuration.hsl_source_path
        if not retarget_vsr.exists():
            print(f"   warning: retarget VSR missing: {retarget_vsr}")
            continue
        hsl_file = plan.scripts_dir / f"aligned_retarget_{folder_name}.hsl"
        hsl_file.write_text(
            generate_aligned_retarget_hsl(
                template_path=template_path,
                plan=plan,
                retarget_vsr_file_path=retarget_vsr,
                retarget_folder_name=folder_name,
                file_name_prefix=prefix,
            )
        )
        try:
            run_shogun(
                mcp_file=mcp_file,
                hsl_file=hsl_file,
                out_file=plan.output_root / f"temp_{folder_name}_aligned_output.mcp",
                shogun_path=shogun_path,
            )
        except RuntimeError as error:
            print(f"   warning: {folder_name} aligned retarget failed: {error}")
            print(f"   inspect generated HSL: {hsl_file}")

    summary_path = plan.reports_dir / "aligned_export_summary.yaml"
    if overwrite or not summary_path.exists():
        write_aligned_export_summary(plan)
    print(f"   aligned export summary: {summary_path}")


def _export_aligned_standard(plan, mcp_file: Path, shogun_path: Path):
    actor_hsl = plan.scripts_dir / "aligned_export_all_actors.hsl"
    actor_hsl.write_text(generate_aligned_actor_export_hsl(plan))
    actor_output_mcp = plan.output_root / "aligned_actor_export_output.mcp"

    print("   exporting cropped aligned actor files...")
    _run_shogun_with_bvh_fallback(
        mcp_file=mcp_file,
        hsl_file=actor_hsl,
        out_file=actor_output_mcp,
        shogun_path=shogun_path,
        static_bvh_hsl_file=(
            plan.scripts_dir / "aligned_export_all_actors_static_hands_bvh.hsl"
        ),
        static_bvh_hsl_content=generate_aligned_actor_export_hsl(
            plan,
            static_hand_bvh=True,
        ),
        fallback_hsl_file=plan.scripts_dir
        / "aligned_export_all_actors_without_bvh.hsl",
        fallback_hsl_content=generate_aligned_actor_export_hsl(
            plan,
            include_bvh=False,
        ),
    )


def _export_aligned_actor_mcps(
    *,
    plan,
    take_dir: Path,
    shogun_path: Path,
) -> list[Path]:
    aligned_actor_mcps: list[Path] = []

    print("   exporting cropped aligned actor files...")
    for actor_entry in plan.mocap_entries:
        actor_source_mcp = actor_entry.source_mcp_path
        if not actor_source_mcp.exists():
            print(
                f"   warning: actor MCP missing for {actor_entry.actor_prefix}, "
                f"expected: {actor_source_mcp}"
            )
            continue

        hsl_file = plan.scripts_dir / f"aligned_export_{actor_entry.actor_prefix}.hsl"
        hsl_file.write_text(generate_aligned_actor_export_hsl(plan, actor_entry))
        actor_output_mcp = (
            plan.output_root / f"temp_{actor_entry.actor_prefix}_aligned_output.mcp"
        )

        print(
            f"   exporting {actor_entry.actor_prefix}: "
            f"{actor_entry.start_frame} -> {actor_entry.end_frame}"
        )
        _run_shogun_with_bvh_fallback(
            mcp_file=actor_source_mcp,
            hsl_file=hsl_file,
            out_file=actor_output_mcp,
            shogun_path=shogun_path,
            static_bvh_hsl_file=(
                plan.scripts_dir
                / f"aligned_export_{actor_entry.actor_prefix}_static_hands_bvh.hsl"
            ),
            static_bvh_hsl_content=generate_aligned_actor_export_hsl(
                plan,
                actor_entry,
                static_hand_bvh=True,
            ),
            fallback_hsl_file=(
                plan.scripts_dir
                / f"aligned_export_{actor_entry.actor_prefix}_without_bvh.hsl"
            ),
            fallback_hsl_content=generate_aligned_actor_export_hsl(
                plan,
                actor_entry,
                include_bvh=False,
            ),
        )

        aligned_actor_mcp = plan.actors_dir / f"{actor_entry.actor_prefix}_aligned.mcp"
        if aligned_actor_mcp.exists():
            aligned_actor_mcps.append(aligned_actor_mcp)
        else:
            matching_outputs = sorted(
                plan.actors_dir.glob(f"{actor_entry.actor_prefix[:3]}*_aligned.mcp")
            )
            if matching_outputs:
                aligned_actor_mcps.extend(matching_outputs)
            else:
                print(
                    f"   warning: aligned MCP was not found for "
                    f"{actor_entry.actor_prefix}"
                )

    if aligned_actor_mcps:
        return sorted(set(aligned_actor_mcps))

    fallback_mcp = _find_retarget_source_mcp(take_dir)
    if fallback_mcp is None:
        print("   warning: no fallback MCP file found.")
        return []

    print(
        "   warning: no per-actor MCP sources were found; "
        "falling back to the full take MCP."
    )
    hsl_file = plan.scripts_dir / "aligned_export_all_actors.hsl"
    hsl_file.write_text(generate_aligned_actor_export_hsl(plan))
    actor_output_mcp = plan.output_root / "aligned_actor_export_output.mcp"
    _run_shogun_with_bvh_fallback(
        mcp_file=fallback_mcp,
        hsl_file=hsl_file,
        out_file=actor_output_mcp,
        shogun_path=shogun_path,
        static_bvh_hsl_file=(
            plan.scripts_dir / "aligned_export_all_actors_static_hands_bvh.hsl"
        ),
        static_bvh_hsl_content=generate_aligned_actor_export_hsl(
            plan,
            static_hand_bvh=True,
        ),
        fallback_hsl_file=plan.scripts_dir
        / "aligned_export_all_actors_without_bvh.hsl",
        fallback_hsl_content=generate_aligned_actor_export_hsl(
            plan,
            include_bvh=False,
        ),
    )
    return sorted(plan.actors_dir.glob("*_aligned.mcp"))


def _find_retarget_source_mcp(take_dir: Path) -> Path | None:
    processed_mcp = take_dir / PROCESSED_MCP_NAME
    if processed_mcp.exists():
        return processed_mcp

    return _find_original_take_mcp(take_dir)


def _find_original_take_mcp(take_dir: Path) -> Path | None:
    generated_names = {
        PROCESSED_MCP_NAME,
        "extra_exports_output.mcp",
        "geeno_dummy_output.mcp",
    }
    original_mcps = [
        path
        for path in sorted(take_dir.glob("*.mcp"))
        if path.name not in generated_names and not path.name.startswith("temp_")
    ]
    return original_mcps[0] if original_mcps else None


def _missing_tracking_prop_exports(export_dir: Path) -> list[TrackingPropExport]:
    return [
        export
        for export in DEFAULT_TRACKING_PROP_EXPORTS
        if not (export_dir / export.output_filename).exists()
    ]


def _is_calibration_take(take_dir: Path) -> bool:
    return any("calibration" in part.lower() for part in take_dir.parts)


def find_bvh_files(root: Path):
    return [f for f in root.rglob("*.bvh") if not f.name.endswith("_converted.bvh")]


def process_bvh(root: Path):
    bvh_files = find_bvh_files(root)
    if not bvh_files:
        print("⚠ No BVH files found.")
        return

    print(f"🔍 Found {len(bvh_files)} BVH files.")
    for bvh in bvh_files:
        out = bvh.with_name(bvh.stem + "_converted.bvh")
        print(f"   ▶ Converting {bvh.name} → {out.name}")
        convert(bvh, out)


def process_face_videos(take_folders):
    print("\n🎥 Renaming face videos...")
    for t in take_folders:
        rename_face_videos(t)


if __name__ == "__main__":
    print_pyramid()

    selection = open_menu()

    if not selection.folder:
        print("❌ No folder selected.")
        sys.exit(1)

    if not selection.folder.exists():
        print(f"Selected folder does not exist: {selection.folder}")
        sys.exit(1)

    if not selection.folder.is_dir():
        print(f"Selected path is not a folder: {selection.folder}")
        sys.exit(1)

    take_folders = find_take_folders(selection.folder)

    for curr_take_directry in take_folders:
        print(" •", curr_take_directry)

    # Run export
    if selection.run_export:
        for curr_take_directry in take_folders:
            print(f"\n▶ Processing take: {curr_take_directry}")
            process_take(
                take_dir=curr_take_directry,
                shogun_path=SHOGUN_PATH,
                force=selection.overwrite,
                include_tracking_props=selection.include_tracking_props,
            )

    if selection.run_mannequin_retarget:
        print("\n🎯 Running mannequin retargeting pass...")
        for curr_take_directry in take_folders:
            process_general_retargeting(
                take_dir=curr_take_directry,
                shogun_path=SHOGUN_PATH,
                retarget_type=RetargetType.MANNEQUIN,
                overwrite=selection.overwrite,
            )
            # process_mannequin_retargeting(take_dir=t, shogun_path=SHOGUN_PATH)

    if selection.run_mannequin_adjusted_retarget:
        print("\n🎯 Running mannequinadjusted retargeting pass...")
        for curr_take_directry in take_folders:
            process_general_retargeting(
                take_dir=curr_take_directry,
                shogun_path=SHOGUN_PATH,
                retarget_type=RetargetType.MANNEQUIN_ADJUSTED,
                overwrite=selection.overwrite,
            )

    if selection.run_geeno_retarget:
        print("\n🤖 Running Geeno retargeting pass...")
        for curr_take_directry in take_folders:
            process_general_retargeting(
                take_dir=curr_take_directry,
                shogun_path=SHOGUN_PATH,
                retarget_type=RetargetType.GEENO,
                overwrite=selection.overwrite,
            )
            # process_geeno_retargeting(take_dir=t, shogun_path=SHOGUN_PATH, force=True)

    if (
        selection.run_aligned_export
        or selection.run_aligned_metahuman
        or selection.run_aligned_geeno
    ):
        print("\nRunning aligned export + MetaHuman + Geeno pass...")
        for curr_take_directry in take_folders:
            process_aligned_export_and_retargeting(
                take_dir=curr_take_directry,
                shogun_path=SHOGUN_PATH,
                export_standard=selection.run_aligned_export,
                retarget_metahuman=selection.run_aligned_metahuman,
                retarget_geeno=selection.run_aligned_geeno,
                overwrite=selection.overwrite,
            )

    # Run BVH conversion
    if selection.run_metahuman_vicon or selection.run_aligned_metahuman_vicon:
        for curr_take_directry in take_folders:
            for aligned in (False, True):
                enabled = (
                    selection.run_aligned_metahuman_vicon
                    if aligned
                    else selection.run_metahuman_vicon
                )
                if enabled:
                    process_metahuman_vicon_retargeting(
                        take_dir=curr_take_directry,
                        shogun_path=SHOGUN_PATH,
                        target_fbx=selection.metahuman_vicon_target_fbx,
                        aligned=aligned,
                        overwrite=selection.overwrite,
                    )

    # Run BVH conversion
    if selection.run_convert_bvh:
        print("\n🔄 Converting all BVH files in folder...")
        process_bvh(selection.folder)

    # Run face video renaming
    if selection.run_rename_face_videos:
        process_face_videos(take_folders)

    print("\n✨ Done!")

    # for take_directory in main_folder.iterdir():
    #     if take_directory.is_dir():
    #         process_take(take_dir=take_directory, shogun_path=shogun_path)

    # process_take(take_dir=main_folder, shogun_path=shogun_path)

    # # later on for all the take.
    # root = Path("recordingDate")

    # for take in root.iterdir():
    #     if take.is_dir():
    #         process_take(take)
