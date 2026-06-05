# # main.py

import argparse
import shutil
from pathlib import Path
from tempfile import template
from tkinter import Tk, filedialog

from bvh.converter import convert
from configuration.settings import (
    ACTORS_FOLDER_NAME,
    EXPORT_FOLDER_NAME,
    GEENO_VICON_RETARGET,
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
from exporter.export_pipeline import generate_hsl
from exporter.geeno_retarget_pipeline import generate_geeno_retarget_hsl
from exporter.general_retarget_pipeline import generate_general_retarget_hsl
from exporter.mannequin_retarget_pipeline import generate_mannequin_retarget_hsl
from ui.menu import open_menu
from utils.file_search import find_take_folders
from utils.rename_face_videos import rename_face_videos
from wrapper.shogun_runner import run_shogun


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


def process_take(take_dir: Path, shogun_path: Path, force: bool):
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
    hsl_content = generate_hsl(export_dir, actors_folder)
    hsl_file = take_dir / "exporter.hsl"
    hsl_file.write_text(hsl_content)
    print(f"   hsl created {hsl_file.name}.")

    out_file = take_dir / PROCESSED_MCP_NAME

    print("running shogun processing.")
    run_shogun(
        mcp_file=mcp, hsl_file=hsl_file, out_file=out_file, shogun_path=shogun_path
    )
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
    original_mcps = list(take_dir.glob("*.mcp"))

    if processed_mcp.exists():
        mcp_file = processed_mcp
    elif original_mcps:
        mcp_file = original_mcps[0]
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
):
    configuration = RETARGET_CONFIGS[retarget_type]

    print(f"\n🤖  retargeting ({configuration.name}): {take_dir}")

    # -----------------------------------------------------
    # 1.determine which MCP to use (processed > original).
    # -----------------------------------------------------
    processed_mcp = take_dir / PROCESSED_MCP_NAME
    original_mcps = list(take_dir.glob("*.mcp"))

    if processed_mcp.exists():
        mcp_file = processed_mcp
    elif original_mcps:
        mcp_file = original_mcps[0]
    else:
        print("   ⚠ no MCP file found, skipping.")
        return

    print(f"   • using MCP: {mcp_file.name}")

    # -------------------------------------------
    # 2. output folder is ALWAYS exported/actors
    # -------------------------------------------
    export_root = take_dir / EXPORT_FOLDER_NAME
    actors_dir = export_root / ACTORS_FOLDER_NAME

    if not actors_dir.exists():
        print(f"   ⚠ Actors folder missing: {actors_dir}")
        return

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
        actors_output_folder=ACTORS_FOLDER_NAME,
        file_name_prefix=f"{configuration.output_name}_",
    )
    print(hsl_content)
    hsl_file = take_dir / f"{configuration.output_name}_retarget.hsl"
    hsl_file.write_text(hsl_content)

    # ---------------------------------------------------------
    # 5. Run Shogun retargeting
    #    NOTE: Output MCP is NOT needed; Shogun will generate
    #    FBX/BVH directly into exported/actors/
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


def process_aligned_export_and_retargeting(take_dir: Path, shogun_path: Path):
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

    actor_hsl = take_dir / "aligned_export_actor_fbx.hsl"
    actor_hsl.write_text(generate_aligned_actor_export_hsl(plan))
    actor_output_mcp = plan.output_root / "aligned_actor_export_output.mcp"

    print("   exporting pure aligned actor files...")
    run_shogun(
        mcp_file=mcp_file,
        hsl_file=actor_hsl,
        out_file=actor_output_mcp,
        shogun_path=shogun_path,
    )

    for retarget_type, folder_name, prefix in [
        (RetargetType.MANNEQUIN, "metahuman", "metahuman_aligned"),
        (RetargetType.GEENO, "geeno", "geeno_aligned"),
    ]:
        configuration = RETARGET_CONFIGS[retarget_type]
        retarget_vsr = Path(__file__).resolve().parent / configuration.vsr_source_path

        if not retarget_vsr.exists():
            print(
                f"   warning: retarget VSR missing, skipping {configuration.name}: {retarget_vsr}"
            )
            continue

        hsl_file = take_dir / f"aligned_retarget_{folder_name}.hsl"
        hsl_file.write_text(
            generate_aligned_retarget_hsl(
                template_path=configuration.hsl_source_path,
                plan=plan,
                retarget_vsr_file_path=retarget_vsr,
                retarget_folder_name=folder_name,
                file_name_prefix=prefix,
            )
        )

        dummy_output_mcp = plan.output_root / f"temp_{folder_name}_aligned_output.mcp"
        print(f"   running {configuration.name} aligned retarget...")
        try:
            run_shogun(
                mcp_file=mcp_file,
                hsl_file=hsl_file,
                out_file=dummy_output_mcp,
                shogun_path=shogun_path,
            )
        except RuntimeError as error:
            print(f"   warning: {configuration.name} aligned retarget failed: {error}")
            print(f"   inspect generated HSL: {hsl_file}")

    summary_path = write_aligned_export_summary(plan)
    print(f"   aligned export summary: {summary_path}")


def _find_retarget_source_mcp(take_dir: Path) -> Path | None:
    processed_mcp = take_dir / PROCESSED_MCP_NAME
    if processed_mcp.exists():
        return processed_mcp

    original_mcps = [
        path for path in take_dir.glob("*.mcp") if path.name != PROCESSED_MCP_NAME
    ]
    return original_mcps[0] if original_mcps else None


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
        exit(1)

    take_folders = find_take_folders(selection.folder)

    for curr_take_directry in take_folders:
        print(" •", curr_take_directry)

    # Run export
    if selection.run_export:
        for curr_take_directry in take_folders:
            print(f"\n▶ Processing take: {curr_take_directry}")
            process_take(
                take_dir=curr_take_directry, shogun_path=SHOGUN_PATH, force=True
            )

    if selection.run_mannequin_retarget:
        print("\n🎯 Running mannequin retargeting pass...")
        for curr_take_directry in take_folders:
            process_general_retargeting(
                take_dir=curr_take_directry,
                shogun_path=SHOGUN_PATH,
                retarget_type=RetargetType.MANNEQUIN,
            )
            # process_mannequin_retargeting(take_dir=t, shogun_path=SHOGUN_PATH)

    if selection.run_mannequin_adjusted_retarget:
        print("\n🎯 Running mannequinadjusted retargeting pass...")
        for curr_take_directry in take_folders:
            process_general_retargeting(
                take_dir=curr_take_directry,
                shogun_path=SHOGUN_PATH,
                retarget_type=RetargetType.MANNEQUIN_ADJUSTED,
            )

    if selection.run_geeno_retarget:
        print("\n🤖 Running Geeno retargeting pass...")
        for curr_take_directry in take_folders:
            process_general_retargeting(
                take_dir=curr_take_directry,
                shogun_path=SHOGUN_PATH,
                retarget_type=RetargetType.GEENO,
            )
            # process_geeno_retargeting(take_dir=t, shogun_path=SHOGUN_PATH, force=True)

    if selection.run_aligned_export:
        print("\nRunning aligned export + MetaHuman + Geeno pass...")
        for curr_take_directry in take_folders:
            process_aligned_export_and_retargeting(
                take_dir=curr_take_directry,
                shogun_path=SHOGUN_PATH,
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
