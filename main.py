# # main.py

import argparse
import shutil
from pathlib import Path
from tkinter import Tk, filedialog

from configuration.settings import (
    ACTORS_FOLDER_NAME,
    EXPORT_FOLDER_NAME,
    PROCESSED_MCP_NAME,
    SHOGUN_PATH,
)
from exporter.export_pipeline import generate_hsl
from exporter.retarget_pipeline import generate_retarget_hsl
from ui.menu import open_menu
from utils.file_search import find_take_folders
from wrapper.bvh_converter import convert_vicon_bvh_to_target
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


def choose_folder() -> Path:
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

    # out_file = take_dir / "processed.mcp"
    out_file = take_dir / PROCESSED_MCP_NAME

    print("running shogun processing.")
    run_shogun(
        mcp_file=mcp, hsl_file=hsl_file, out_file=out_file, shogun_path=shogun_path
    )
    print(f"     complete Output saved to: {out_file}\n")


def process_retargeting(take_dir: Path, shogun_path: Path):
    print(f"\n🎯 retargeting: {take_dir}")

    export_dir = take_dir / EXPORT_FOLDER_NAME / ACTORS_FOLDER_NAME

    # find all actor .mcp files
    actor_mcps = list(export_dir.glob("*.mcp"))
    if not actor_mcps:
        print("   ⚠ no actor .mcp files found, skipping.")
        return

    # create retarget folder
    retarget_dir = take_dir / EXPORT_FOLDER_NAME / "retargeted"
    retarget_dir.mkdir(exist_ok=True)

    for actor_mcp in actor_mcps:
        print(f"   ▶ retargeting actor: {actor_mcp.name}")

        # generate retarget HSL
        hsl_content = generate_retarget_hsl(
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
        convert_vicon_bvh_to_target(bvh, out)


if __name__ == "__main__":
    print_pyramid()

    selection = open_menu()

    if not selection.folder:
        print("❌ No folder selected.")
        exit(1)

    take_folders = find_take_folders(selection.folder)

    for t in take_folders:
        print(" •", t)

    # Run export
    if selection.run_export:
        for t in take_folders:
            print(f"\n▶ Processing take: {t}")
            process_take(take_dir=t, shogun_path=SHOGUN_PATH, force=True)

    # Run retarget
    if selection.run_retarget:
        print("\n🎯 Running retargeting pass...")
        for t in take_folders:
            process_retargeting(take_dir=t, shogun_path=SHOGUN_PATH)

    # Run BVH conversion
    if selection.run_convert_bvh:
        print("\n🔄 Converting all BVH files in folder...")
        process_bvh(selection.folder)

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
