# import os
# from wrapper.vicon_wrapper import export_take

# ROOT = r"C:\Users\jovan\Documents\project\dati\data_gilab\mocap_actors_16_03_2026\1-street\take1"


# # main.py

from pathlib import Path
from exporter.export_pipeline import generate_hsl
from wrapper.shogun_runner import run_shogun


def process_take(take_dir: Path, shogun_path: Path):
    mcp: Path = next(take_dir.glob("*.mcp"))

    export_dir = take_dir / "exported"
    export_dir.mkdir(exist_ok=True)
    actors_folder: str = "actors"
    (export_dir / actors_folder).mkdir(exist_ok=True)

    hsl_content = generate_hsl(export_dir, actors_folder)

    hsl_file = take_dir / "temp.hsl"
    hsl_file.write_text(hsl_content)

    out_file = take_dir / "processed.mcp"

    run_shogun(mcp_file=mcp, hsl_file=hsl_file, out_file=out_file, shogun_path=shogun_path)


if __name__ == "__main__":
    shogun_path = Path(r"C:\Program Files\Vicon\ShogunPost1.18\ShogunPostCL.exe")
    
    # test for a take.
    take_path = Path(r"G:\My Drive\mocap 16-02-2026\1-living-room\take-1")
    process_take(take_dir=take_path, shogun_path=shogun_path)

    # # later on for all the take.
    # root = Path("recordingDate")

    # for take in root.iterdir():
    #     if take.is_dir():
    #         process_take(take)