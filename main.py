# # main.py

import argparse
import os
import sys
from pathlib import Path
from tkinter import Tk, filedialog

from bvh.converter import convert
from configuration.settings import (
    ACTORS_FOLDER_NAME,
    EXPORT_FOLDER_NAME,
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
from exporter.aligned_props_pipeline import export_aligned_props
from exporter.aligned_scene_extras import export_aligned_scene_extras
from exporter.export_pipeline import (
    DEFAULT_TRACKING_PROP_EXPORTS,
    TrackingPropExport,
    generate_extra_exports_hsl,
    generate_hsl,
)
from exporter.export_status import STEP_BY_KEY, record_step
from exporter.general_retarget_pipeline import generate_general_retarget_hsl
from ui.menu import UserSelection, open_menu
from utils.file_search import find_take_folders
from utils.rename_face_videos import rename_face_videos
from wrapper.shogun_runner import ShogunError, run_shogun


def parse_args():
    parser = argparse.ArgumentParser(
        description="vicon exporter. Without --take the menu opens; with --take the "
        "chosen aligned steps run on those takes without the menu."
    )
    parser.add_argument(
        "--take",
        action="append",
        type=Path,
        default=[],
        help="take folder to process (repeat for several)",
    )
    parser.add_argument(
        "--steps",
        default="",
        help="comma-separated aligned steps: " + ", ".join(STEP_BY_KEY),
    )
    parser.add_argument(
        "-f",
        "--overwrite",
        action="store_true",
        help="replace existing outputs (needed to refresh outdated exports)",
    )
    parser.add_argument(
        "--prop-crop", choices=("first", "extremes"), default="first"
    )
    return parser.parse_args()


def selection_from_args(args) -> UserSelection:
    selection = UserSelection()
    steps = [key.strip() for key in args.steps.split(",") if key.strip()]
    unknown = [key for key in steps if key not in STEP_BY_KEY]
    if unknown or not steps:
        sys.exit(f"Choose --steps from {', '.join(STEP_BY_KEY)} (got {args.steps!r}).")
    for key in steps:
        setattr(selection, STEP_BY_KEY[key].option, True)
    selection.overwrite = args.overwrite
    selection.prop_crop_policy = args.prop_crop
    takes = [take.resolve() for take in args.take]
    missing = [str(take) for take in takes if not take.is_dir()]
    if missing:
        sys.exit("Take folders not found:\n" + "\n".join(missing))
    selection.folder = Path(os.path.commonpath(takes)) if len(takes) > 1 else takes[0]
    return selection


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


def process_take(
    take_dir: Path,
    shogun_path: Path,
    force: bool,
    include_tracking_props: bool = False,
):
    export_dir = take_dir / EXPORT_FOLDER_NAME

    missing_tracking_prop_exports: list[TrackingPropExport] = []
    missing_calibration_markers = False
    if include_tracking_props:
        missing_tracking_prop_exports = _missing_tracking_prop_exports(export_dir)
        missing_calibration_markers = (
            _is_calibration_take(take_dir)
            and not (export_dir / "calibration_markers.c3d").exists()
        )

    has_existing_export = export_dir.exists() and any(
        path.is_file() for path in export_dir.rglob("*")
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

        print("running shogun extra export processing.")
        run_shogun(
            mcp_file=mcp,
            hsl_file=hsl_file,
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

    print("running shogun processing.")
    exported_bvh = _run_shogun_with_bvh_fallback(
        mcp_file=mcp,
        hsl_file=hsl_file,
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
    print(f"     complete Output saved to: {export_dir}\n")


def process_general_retargeting(
    take_dir: Path,
    shogun_path: Path,
    retarget_type: RetargetType,
    overwrite: bool = False,
):
    configuration = RETARGET_CONFIGS[retarget_type]

    print(f"\n🤖  retargeting ({configuration.name}): {take_dir}")

    # -----------------------------------------------------
    # 1. the original take MCP.
    # -----------------------------------------------------
    mcp_file = _find_original_take_mcp(take_dir)
    if mcp_file is None:
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
    # 5. Run Shogun retargeting: FBX goes directly into this
    #    method's output folder.
    # ---------------------------------------------------------
    print("   • Running Shogun retargeting...")
    run_shogun(
        mcp_file=mcp_file,
        hsl_file=hsl_file,
        shogun_path=shogun_path,
    )

    print(
        f"   ✔ {configuration.output_name} retarget complete → actors written to {actors_dir}"
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

    mcp_file = _find_original_take_mcp(take_dir)
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
        record_step(take_dir, "actors")
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
                shogun_path=shogun_path,
            )
        except RuntimeError as error:
            print(f"   warning: {folder_name} aligned retarget failed: {error}")
            print(f"   inspect generated HSL: {hsl_file}")
        else:
            record_step(take_dir, folder_name)

    summary_path = plan.reports_dir / "aligned_export_summary.yaml"
    if overwrite or not summary_path.exists():
        write_aligned_export_summary(plan)
    print(f"   aligned export summary: {summary_path}")


def _export_aligned_standard(plan, mcp_file: Path, shogun_path: Path):
    actor_hsl = plan.scripts_dir / "aligned_export_all_actors.hsl"
    actor_hsl.write_text(generate_aligned_actor_export_hsl(plan))

    print("   exporting cropped aligned actor files...")
    _run_shogun_with_bvh_fallback(
        mcp_file=mcp_file,
        hsl_file=actor_hsl,
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


def _find_original_take_mcp(take_dir: Path) -> Path | None:
    generated_names = {
        PROCESSED_MCP_NAME,
        "extra_exports_output.mcp",
        "geeno_dummy_output.mcp",
        "aligned_actor_export_output.mcp",
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
    args = parse_args()

    if args.take:
        selection = selection_from_args(args)
        take_folders = [take.resolve() for take in args.take]
    else:
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
    from utils.batch_report import BatchReport

    batch = BatchReport(selection.folder)
    process_take = batch.track(process_take, "Full actor export")
    process_general_retargeting = batch.track(
        process_general_retargeting, lambda kw: f"Retarget {kw.get('retarget_type')}"
    )
    process_aligned_export_and_retargeting = batch.track(
        process_aligned_export_and_retargeting,
        lambda kw: (
            "Aligned actors"
            if kw.get("export_standard")
            else "Aligned MetaHuman"
            if kw.get("retarget_metahuman")
            else "Aligned Geeno"
        ),
    )
    export_aligned_props = batch.track(export_aligned_props, "Aligned individual props")
    export_aligned_scene_extras = batch.track(
        export_aligned_scene_extras, "Aligned scene extras"
    )
    process_bvh = batch.track(process_bvh, "BVH conversion")
    process_face_videos = batch.track(process_face_videos, "Face video renaming")

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
            for standard, metahuman, geeno in (
                (selection.run_aligned_export, False, False),
                (False, selection.run_aligned_metahuman, False),
                (False, False, selection.run_aligned_geeno),
            ):
                if standard or metahuman or geeno:
                    process_aligned_export_and_retargeting(
                        take_dir=curr_take_directry,
                        shogun_path=SHOGUN_PATH,
                        export_standard=standard,
                        retarget_metahuman=metahuman,
                        retarget_geeno=geeno,
                        overwrite=selection.overwrite,
                    )

    prop_warnings = []
    if (
        selection.run_aligned_props
        or selection.run_aligned_combined_props
        or selection.run_aligned_calibration_markers
    ):
        for take_dir in take_folders:
            try:
                source = _find_original_take_mcp(take_dir)
                if source is None:
                    raise ValueError(f"No source MCP found in {take_dir}")
                for exporter, options, enabled in (
                    (export_aligned_props, {}, selection.run_aligned_props),
                    (
                        export_aligned_scene_extras,
                        {
                            "combined": selection.run_aligned_combined_props,
                            "calibration_markers": selection.run_aligned_calibration_markers,
                        },
                        selection.run_aligned_combined_props
                        or selection.run_aligned_calibration_markers,
                    ),
                ):
                    if enabled:
                        warning = exporter(
                            take_dir,
                            source,
                            SHOGUN_PATH,
                            policy=selection.prop_crop_policy,
                            overwrite=selection.overwrite,
                            **options,
                        )
                        if warning and warning not in prop_warnings:
                            prop_warnings.append(warning)
            except (OSError, RuntimeError, ValueError) as error:
                prop_warnings.append(f"{take_dir}: aligned prop export failed: {error}")
                batch.record_failure(take_dir, "Aligned props setup", error)

    # Run BVH conversion
    if selection.run_convert_bvh:
        print("\n🔄 Converting all BVH files in folder...")
        process_bvh(selection.folder)

    # Run face video renaming
    if selection.run_rename_face_videos:
        process_face_videos(take_folders)

    if prop_warnings:
        print("\nAligned prop export warnings:")
        for warning in prop_warnings:
            print(f"   warning: {warning}")
    batch.finish()
    print("\nBatch finished.")
