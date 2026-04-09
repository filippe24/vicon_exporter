import re
from pathlib import Path


def rename_face_videos(root_take_dir: Path):
    """
    Recursively finds take folders and renames MP4 files inside face-* folders to:
        <actor>_<date>_take<take_number>.mp4
    """

    # Find all take folders inside this directory (including itself)
    take_folders = [
        d
        for d in root_take_dir.rglob("*")
        if d.is_dir() and re.match(r"take\d+", d.name, re.IGNORECASE)
    ]

    # Also include the folder itself if it is a take folder
    if re.match(r"take\d+", root_take_dir.name, re.IGNORECASE):
        take_folders.append(root_take_dir)

    if not take_folders:
        print(f"⚠ No take folders found in {root_take_dir}")
        return

    for take_dir in take_folders:
        print(f"\n🎥 Renaming face videos in {take_dir}")

        # Extract take number
        try:
            take_number = re.findall(r"\d+", take_dir.name)[0]
            date_folder = take_dir.parent.parent.name  # "<date>"
            base_name = f"{date_folder}_take{take_number}"
        except Exception:
            print(f"⚠ Could not parse date/take number for {take_dir}")
            continue

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
