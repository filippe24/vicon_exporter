from pathlib import Path

from configuration.settings import (
    ALIGNED_EXPORT_FOLDER_NAME,
    EXPORT_FOLDER_NAME,
    PROCESSED_MCP_NAME,
)


SKIPPED_TAKE_SEARCH_FOLDERS = {
    ".git",
    "__pycache__",
    EXPORT_FOLDER_NAME.lower(),
    ALIGNED_EXPORT_FOLDER_NAME.lower(),
    "actors",
    "retargeted",
}


def find_take_folders(root: Path) -> list[Path]:
    """Return original take folders under root that contain an .mcp file."""

    take_folders = []

    if root.name.lower() in SKIPPED_TAKE_SEARCH_FOLDERS:
        return take_folders

    original_mcps = [
        path for path in root.glob("*.mcp") if path.name != PROCESSED_MCP_NAME
    ]
    if original_mcps:
        take_folders.append(root)

    for sub in sorted(root.iterdir()):
        if sub.is_dir():
            take_folders.extend(find_take_folders(sub))

    return take_folders


def find_bvh_files(root: Path):
    return [
        f
        for f in root.rglob("*.bvh")
        if not f.name.endswith(".tmp.bvh") and not f.name.endswith("_converted.bvh")
    ]
