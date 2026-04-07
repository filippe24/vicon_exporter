from pathlib import Path


def find_take_folders(root: Path) -> list[Path]:
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


def find_bvh_files(root: Path):
    return [
        f
        for f in root.rglob("*.bvh")
        if not f.name.endswith(".tmp.bvh") and not f.name.endswith("_converted.bvh")
    ]
