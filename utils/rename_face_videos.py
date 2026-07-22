import re
from pathlib import Path


TAKE_NUMBER_RE = re.compile(
    r"(?:^|[_\-\s])(?:take[_\-\s]*)?(\d+)(?:$|[_\-\s])",
    re.IGNORECASE,
)
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}")


def rename_face_videos(root_take_dir: Path):
    """
    Recursively finds take folders and renames MP4 files inside face-* folders to:
        <actor>_<date>_<take_number>.mp4
    """

    take_folders = find_face_video_take_folders(root_take_dir)

    if not take_folders:
        print(f"⚠ No take folders found in {root_take_dir}")
        return

    for take_dir in take_folders:
        print(f"\n🎥 Renaming face videos in {take_dir}")

        # Extract take number
        take_number = find_take_number(take_dir.name)
        date_folder = find_nearest_date_folder(take_dir)
        if take_number is None or date_folder is None:
            print(f"⚠ Could not parse date/take number for {take_dir}")
            continue
        base_name = f"{date_folder}_{take_number}"

        # Find face-* folders inside this take
        face_folders = [
            f
            for f in take_dir.iterdir()
            if f.is_dir() and f.name.lower().startswith("face")
        ]

        if not face_folders:
            print(f"   ⚠ No face-* folders found in {take_dir}")
            continue

        for folder in face_folders:
            folder_name = folder.name

            # Extract actor ID (anything after "face" or "face-")
            actor = re.sub(r"^face[-_]*", "", folder_name, flags=re.IGNORECASE)
            actor = re.sub(r"[^A-Za-z0-9]+", "", actor) or "unknown"

            mp4_files = list(folder.glob("*.mp4"))
            if not mp4_files:
                print(f"   • No MP4 files in {folder.name}")
                continue

            for i, mp4 in enumerate(mp4_files):
                suffix = f"_{i}" if len(mp4_files) > 1 else ""
                new_name = f"{actor}_{base_name}{suffix}.mp4"
                new_path = mp4.with_name(new_name)

                print(f"   • {mp4.name} → {new_name}")
                mp4.rename(new_path)


def find_face_video_take_folders(root_take_dir: Path) -> list[Path]:
    candidates = [root_take_dir, *root_take_dir.rglob("*")]
    return [
        path
        for path in candidates
        if path.is_dir()
        and find_take_number(path.name) is not None
        and any(child.is_dir() and child.name.lower().startswith("face") for child in path.iterdir())
    ]


def find_take_number(name: str) -> str | None:
    match = TAKE_NUMBER_RE.search(name)
    if match is None:
        return None
    return f"{int(match.group(1)):03d}"


def find_nearest_date_folder(path: Path) -> str | None:
    for part in reversed(path.parts):
        match = DATE_RE.search(part)
        if match is not None:
            return match.group(0)
    return None
