from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from configuration.settings import (
    GEENO_VICON_RETARGET,
    MANNEQUIN_VICON_RETARGET_ADJUSTED,
    MANNEQUIN_VICON_RETARGET_BASIC,
    RETARGET_GENERAL_TEMPLATE,
    RETARGET_MANNEQUIN_TEMPLATE_ADJUSTED,
)


@dataclass
class RetargetConfig:
    name: str
    vsr_source_path: Path
    hsl_source_path: Path
    output_name: str = ""


class RetargetType(Enum):
    MANNEQUIN = "mannequin"
    MANNEQUIN_ADJUSTED = "mannequin_adjusted"
    GEENO = "geeno"


RETARGET_CONFIGS = {
    RetargetType.MANNEQUIN: RetargetConfig(
        name="mannequin",
        vsr_source_path=MANNEQUIN_VICON_RETARGET_BASIC,
        hsl_source_path=RETARGET_GENERAL_TEMPLATE,
        output_name="mannequin",
    ),
    RetargetType.MANNEQUIN_ADJUSTED: RetargetConfig(
        name="mannequin adjusted",
        vsr_source_path=MANNEQUIN_VICON_RETARGET_ADJUSTED,
        hsl_source_path=RETARGET_MANNEQUIN_TEMPLATE_ADJUSTED,
        output_name="mannequin_adjusted",
    ),
    RetargetType.GEENO: RetargetConfig(
        name="geeno",
        vsr_source_path=GEENO_VICON_RETARGET,
        hsl_source_path=RETARGET_GENERAL_TEMPLATE,
        output_name="geeno",
    ),
}
