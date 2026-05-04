# exporter/geeno_retarget_pipeline.py
from pathlib import Path


def generate_general_retarget_hsl(
    template_path: Path,
    output_path: Path,
    retarget_vsr_file_path: Path,
    actors_output_folder: str = "actors",
    file_name_prefix: str = "retargeted_",
) -> str:
    if not template_path.exists:
        return ""
    template = template_path.read_text()
    return (
        template.replace("{ACTORS_FOLDER}", actors_output_folder)
        .replace("{EXPORT_DIR}", str(output_path).replace("\\", "/"))
        .replace("{RETARGET_VSR_PATH}", str(retarget_vsr_file_path).replace("\\", "/"))
        .replace("{NEW_FILE_NAME}", file_name_prefix)
    )
