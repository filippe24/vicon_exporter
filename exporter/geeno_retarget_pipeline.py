# exporter/geeno_retarget_pipeline.py
from pathlib import Path

from configuration.settings import GEENO_RETARGET_TEMPLATE


def generate_geeno_retarget_hsl(
    output_path: Path,
    retarget_vsr_file_path: Path,
    actors_output_folder: str = "actors",
):
    template = GEENO_RETARGET_TEMPLATE.read_text()

    return (
        template.replace("{ACTORS_FOLDER}", actors_output_folder)
        .replace("{EXPORT_DIR}", str(output_path).replace("\\", "/"))
        .replace("{RETARGET_VSR_PATH}", str(retarget_vsr_file_path).replace("\\", "/"))
        .replace("{GEENO_FILE_NAME}", "geeno_")
    )
