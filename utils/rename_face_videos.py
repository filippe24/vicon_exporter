import re
from pathlib import Path


def rename_face_videos(take_dir: Path):
    """
    Renames MP4 files inside face-* folders to:
        <actor>_<date>_take<take_number>.mp4

    Actor is extracted from folder name:
        face-j  → j
        faceA   → A
        face-john → john
    """

    # Extract date and take number from folder structure
    try:
        take_name = take_dir.name  # "take03"
        take_number = re.findall(r"\d+", take_name)[0]

        date_folder = take_dir.parent.parent.name  # "<date>"
        base_name = f"{date_folder}_take{take_number}"
    except Exception:
        print(f"⚠ Could not parse date/take number for {take_dir}")
        return

    # Find face-* folders
    face_folders = [
        f
        for f in take_dir.iterdir()
        if f.is_dir() and f.name.lower().startswith("face")
    ]

    if not face_folders:
        print(f"⚠ No face-* folders found in {take_dir}")
        return

    print(f"🎥 Renaming face videos in {take_dir.name}")

    for folder in face_folders:
        folder_name = folder.name

        # Extract actor ID (anything after "face" or "face-")
        actor = re.sub(r"^face[-_]*", "", folder_name, flags=re.IGNORECASE)

        # Fallback if empty
        if not actor:
            actor = "unknown"

        # Clean actor string (letters only)
        actor = re.sub(r"[^A-Za-z0-9]+", "", actor)

        mp4_files = list(folder.glob("*.mp4"))

        if not mp4_files:
            print(f"   • No MP4 files in {folder.name}")
            continue

        for i, mp4 in enumerate(mp4_files):
            # If multiple MP4s exist, append index
            suffix = f"_{i}" if len(mp4_files) > 1 else ""

            new_name = f"{actor}_{base_name}{suffix}.mp4"
            new_path = mp4.with_name(new_name)

            print(f"   • {mp4.name} → {new_name}")
            mp4.rename(new_path)
