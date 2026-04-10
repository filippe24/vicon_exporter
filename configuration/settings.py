# configuration/settings.py
from pathlib import Path

# path to ShogunPostCL executable.
SHOGUN_PATH = Path(r"C:\Program Files\Vicon\ShogunPost1.18\ShogunPostCL.exe")

# name of the folder where exported files go
EXPORT_FOLDER_NAME = "exported"

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
MANNEQUIN_RETARGET_TEMPLATE = Path(r"hsl\retarget_mannequin_template.hsl")

GEENO_VICON_RETARGET = Path(r"models/geeno.vsr")
