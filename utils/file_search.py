from pathlib import Path

from configuration.settings import (
    ALIGNED_EXPORT_FOLDER_NAME,
    EXPORT_FOLDER_NAME,
    PROCESSED_MCP_NAME,
)

SKIPPED_TAKE_SEARCH_FOLDERS = {
    ".git",
    ".aligner",
    "__pycache__",
    EXPORT_FOLDER_NAME.lower(),
    ALIGNED_EXPORT_FOLDER_NAME.lower(),
    "aligner._data",
    "actors",
    "retargeted",
}


def find_take_folders(root: Path) -> list[Path]:
    """Return original take folders under root that contain an .mcp file."""

    take_folders = []

    if root.name.startswith(".") or root.name.lower() in SKIPPED_TAKE_SEARCH_FOLDERS:
        return take_folders

    try:
        original_mcps = [
            path for path in root.glob("*.mcp") if path.name != PROCESSED_MCP_NAME
        ]
    except OSError:
        return take_folders

    if original_mcps:
        take_folders.append(root)

    try:
        subfolders = sorted(root.iterdir())
    except OSError:
        return take_folders

    for sub in subfolders:
        try:
            if sub.is_dir():
                take_folders.extend(find_take_folders(sub))
        except OSError:
            continue

    return take_folders


def find_bvh_files(root: Path):
    return [
        f
        for f in root.rglob("*.bvh")
        if not f.name.endswith(".tmp.bvh") and not f.name.endswith("_converted.bvh")
    ]
