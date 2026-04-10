# exporter/mannequin_retarget_pipeline.py
from pathlib import Path

from configuration.settings import LOCAL_PATH_TO_MODEL, MANNEQUIN_RETARGET_TEMPLATE


def generate_mannequin_retarget_hsl(actor_source_path: Path, output_path: Path):
    # template = Path("hsl/retarget_template.hsl").read_text()
    template = MANNEQUIN_RETARGET_TEMPLATE.read_text()

    return (
        template.replace("{ACTOR_MCP}", actor_source_path)
        .replace("{OUTPUT_DIR}", output_path)
        .replace("{MODEL_PATH}", LOCAL_PATH_TO_MODEL)
    )
