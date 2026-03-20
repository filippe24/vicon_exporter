import subprocess
import os

SHOGUN_POST_CL = r"C:\Program Files\Vicon\ShogunPost1.18\ShogunPostCL.exe"


def export_take(take_folder):
    take_name = os.path.basename(take_folder)

    export_dir = os.path.join(take_folder, "exported")
    os.makedirs(export_dir, exist_ok=True)

    c3d_path = os.path.join(export_dir, "markers_world.c3d")

    # cmd = [
    #     SHOGUN_POST_CL,
    #     "-take", take_folder,
    #     "-exportC3D", c3d_path,
    #     "-exportFBX", export_dir,
    # ]
    cmd = [
        "ShogunPostCL",
        "-old",
        infile,
        script,
        infile  # output MCP (can overwrite or temp)
    ]

    subprocess.run(cmd, check=True)
    print("Running:", " ".join(cmd))

    result = subprocess.run(cmd, capture_output=True, text=True)

    print(result.stdout)
    print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError("Shogun export failed")