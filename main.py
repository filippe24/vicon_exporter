# import os
# from wrapper.vicon_wrapper import export_take

# ROOT = r"C:\Users\jovan\Documents\project\dati\data_gilab\mocap_actors_16_03_2026\1-street\take1"


# # main.py

from pathlib import Path
from tkinter import Tk, filedialog
from typing import List
from exporter.export_pipeline import generate_hsl
from wrapper.shogun_runner import run_shogun


def print_pyramid():
    PURPLE = "\033[35m"
    BLUE = "\033[36m"
    YELLOW = "\033[33m"
    RESET = "\033[0m"
    BOLD = "\033[1m"

    lines = [
        (PURPLE, "             vicon exporter"),
        (PURPLE, "          ▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓"),
        (PURPLE, "               ▓▓▓▓▓▓▓▓▓▓▓▓"),
        (BLUE,   "             ▓▓▓ ▓▓▓▓▓▓▓▓▓▓"),
        (YELLOW, "                     ▓▓▓▓▓▓"),
    ]

    print()
    for color, text in lines:
        print(color + BOLD + text + RESET)
    print()


def choose_folder() -> Path:
    root = Tk()
    root.withdraw()
    folder = filedialog.askdirectory(title="select take folder.")
    root.destroy()
    return Path(folder) if folder else None

def find_take_folders(root: Path) -> List[Path]:
    """return all folders under root that contain an .mcp file."""

    take_folders = []

    # A) the folder contains mcp file.
    if any(root.glob("*.mcp")):
        take_folders.append(root)
        return take_folders

    # B) recursively look for sub-folders.
    for sub in root.iterdir():
        if sub.is_dir():
            take_folders.extend(find_take_folders(sub))

    return take_folders


def process_take(take_dir: Path, shogun_path: Path):
    print(f"\n📁 selected folder: {take_dir}.")
    print("looking for for .mcp file.")
    mcp: Path = next(take_dir.glob("*.mcp"))
    print(f"   found: {mcp.name}.")

    print("📂 creating export folders.")
    export_dir = take_dir / "exported"
    export_dir.mkdir(exist_ok=True)
    actors_folder: str = "actors"
    (export_dir / actors_folder).mkdir(exist_ok=True)
    print(f"   export folders created.")


    print("generating hsl file.")
    hsl_content = generate_hsl(export_dir, actors_folder)
    hsl_file = take_dir / "exporter.hsl"
    hsl_file.write_text(hsl_content)
    print(f"   hsl created {hsl_file.name}.")

    out_file = take_dir / "processed.mcp"

    print("running shogun processing.")
    run_shogun(mcp_file=mcp, hsl_file=hsl_file, out_file=out_file, shogun_path=shogun_path)
    print(f"     complete Output saved to: {out_file}\n")

if __name__ == "__main__":
    shogun_path = Path(r"C:\Program Files\Vicon\ShogunPost1.18\ShogunPostCL.exe")
    print_pyramid()
    # test for a take.
    print("📂 select the folder...")
    # take_path = Path(r"G:\My Drive\mocap 16-02-2026\1-living-room\take-1")
    main_folder = choose_folder()
    
    if not main_folder:
        print("❌ no folder selected :(.")
        exit(1)
    
    take_folders = find_take_folders(main_folder)
    for t in take_folders:
        print("   •", t)

    for t in take_folders:
        print(f"\n processing take: {t}")
        process_take(take_dir=t, shogun_path=shogun_path)

    print("success!")

    # for take_directory in main_folder.iterdir():
    #     if take_directory.is_dir():
    #         process_take(take_dir=take_directory, shogun_path=shogun_path)
   
   
    # process_take(take_dir=main_folder, shogun_path=shogun_path)

    # # later on for all the take.
    # root = Path("recordingDate")

    # for take in root.iterdir():
    #     if take.is_dir():
    #         process_take(take)