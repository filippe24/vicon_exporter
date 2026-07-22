# configuration/settings.py
from pathlib import Path

# path to ShogunPostCL executable.
# SHOGUN_PATH = Path(r"C:\Program Files\Vicon\ShogunPost1.19\ShogunPostCL.exe")
SHOGUN_PATH = Path(r"C:\Program Files\Vicon\ShogunPost1.20\ShogunPostCL.exe")

# name of the folder where exported files go
EXPORT_FOLDER_NAME = "exported"

# name of the folder where aligner-compatible exports go.
ALIGNED_EXPORT_FOLDER_NAME = "aligned_exports"

# name of the report folder inside aligned exports.
ALIGNED_REPORTS_FOLDER_NAME = "reports"

# name of the actors folder inside the export folder.
ACTORS_FOLDER_NAME = "actors"

# name of the generated HSL file.
HSL_FILENAME = r"hsl\exporter.hsl"

# name of the processed MCP output.
PROCESSED_MCP_NAME = "processed.mcp"

# local path to the model.
LOCAL_PATH_TO_MODEL = Path(r"models\retarget_original_mannequin.fbx")

# exporter template path.
EXPORTER_TEMPLATE = Path(r"hsl\template.hsl")

# standard retarget template.
GEENO_RETARGET_TEMPLATE = Path(r"hsl\retarget_geeno_template.hsl")
OLD_MANNEQUIN_RETARGET_TEMPLATE = Path(r"hsl\retarget_mannequin_template.hsl")

RETARGET_GENERAL_TEMPLATE = Path(r"hsl\retarget_general_template.hsl")
RETARGET_MANNEQUIN_TEMPLATE_ADJUSTED = Path(
    r"hsl\retarget_mannequin_template_adjusted_for_metahuman.hsl"
)

MANNEQUIN_VICON_RETARGET_BASIC = Path(r"models/basic_mannequin.vsr")
MANNEQUIN_VICON_RETARGET_ADJUSTED = Path(r"models/adjusted_mannequin.vsr")
GEENO_VICON_RETARGET = Path(r"models/geeno.vsr")
