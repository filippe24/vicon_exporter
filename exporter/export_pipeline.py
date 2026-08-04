# exporter/export_pipeline.py

from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple

from configuration.settings import EXPORTER_TEMPLATE


class TrackingPropExport(NamedTuple):
    module_name_pattern: str
    output_filename: str


DEFAULT_TRACKING_PROP_EXPORTS = (
    TrackingPropExport("eye_tracker_1*", "eye_tracker_1.c3d"),
    TrackingPropExport("eye_tracker_2*", "eye_tracker_2.c3d"),
)


def generate_hsl(
    output_path: Path,
    actors_output_folder: str = "actors",
    clapperboard_base_name: str = "clapperboard_",
    include_tracking_props: bool = False,
    include_calibration_markers: bool = False,
    tracking_prop_exports: Sequence[TrackingPropExport] | None = None,
):
    """code to generate dynamic hls file to run in shogun post."""
    if output_path:
        output_path = Path(output_path.as_posix())

        template: str = EXPORTER_TEMPLATE.read_text()

        additional_prop_exports = _generate_tracking_prop_exports_hsl(
            _resolve_tracking_prop_exports(
                include_tracking_props,
                tracking_prop_exports,
            )
        )

        calibration_marker_export = ""
        if include_calibration_markers:
            calibration_marker_export = _generate_calibration_marker_export_hsl()

        # print(str(output_path).replace("\\", "/"))
        return (
            template.replace("{ACTORS_FOLDER}", actors_output_folder)
            .replace("{CLAPPERBOARD_NAME}", clapperboard_base_name)
            .replace("{ADDITIONAL_PROP_EXPORTS}", additional_prop_exports)
            .replace("{CALIBRATION_MARKER_EXPORT}", calibration_marker_export)
            .replace("{EXPORT_DIR}", str(output_path).replace("\\", "/"))
        )
    return None


def generate_extra_exports_hsl(
    output_path: Path,
    tracking_prop_exports: Sequence[TrackingPropExport] | None = None,
    include_calibration_markers: bool = False,
) -> str | None:
    if not output_path:
        return None

    output_path = Path(output_path.as_posix())
    additional_prop_exports = _generate_tracking_prop_exports_hsl(
        tracking_prop_exports or ()
    )
    calibration_marker_export = ""
    if include_calibration_markers:
        calibration_marker_export = _generate_calibration_marker_export_hsl()

    return (
        f"{additional_prop_exports}\n{calibration_marker_export}".replace(
            "{EXPORT_DIR}", str(output_path).replace("\\", "/")
        ).strip()
        + "\n"
    )


def _resolve_tracking_prop_exports(
    include_tracking_props: bool,
    tracking_prop_exports: Sequence[TrackingPropExport] | None,
) -> Sequence[TrackingPropExport]:
    if tracking_prop_exports is not None:
        return tracking_prop_exports
    if include_tracking_props:
        return DEFAULT_TRACKING_PROP_EXPORTS
    return ()


def _generate_tracking_prop_exports_hsl(
    tracking_prop_exports: Sequence[TrackingPropExport],
) -> str:
    return "\n".join(
        _generate_named_prop_export_hsl(
            module_name_pattern=export.module_name_pattern,
            output_filename=export.output_filename,
            variable_name=f"tracking_prop_modules_{index}",
        )
        for index, export in enumerate(tracking_prop_exports, start=1)
    )


def _generate_named_prop_export_hsl(
    module_name_pattern: str,
    output_filename: str,
    variable_name: str,
) -> str:
    return f"""
//------- export {output_filename} ---
select ; // deselect.
selectByName "{module_name_pattern}";
string ${variable_name}[] = `getModules -selected`;
if( `getCount ${variable_name}` > 0 )
{{
\tselectChildren  -recursive -a ${variable_name} ;
\tsaveFile -s "{{EXPORT_DIR}}/{output_filename}";
}}
select ; // deselect.
"""


def _generate_calibration_marker_export_hsl() -> str:
    return """
//------- export free calibration markers ---
select ; // deselect.
selectProps;
selectByName "*" -type Character -a;
string $calibration_attached_modules[] = `getModules -selected`;
if( `getCount $calibration_attached_modules` > 0 )
{
\tselectChildren  -recursive -a $calibration_attached_modules ;
}
select -invert;
string $calibration_free_markers[] = `getModules -selected -type Marker`;
select ; // deselect.
if( `getCount $calibration_free_markers` > 0 )
{
\tselect $calibration_free_markers;
\tsaveFile -s "{EXPORT_DIR}/calibration_markers.c3d";
}
select ; // deselect.
"""
