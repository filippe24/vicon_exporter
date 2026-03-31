# exporter/export_pipeline.py

from pathlib import Path

def generate_hsl(output_path: Path, actors_folder: str = "actors", clapperboard_base_name: str = "clapperboard_"):
    ''' code to generate dynamic hls file to run in shogun post.'''
    if output_path:
        output_path:Path = Path(output_path.as_posix())

        # actors_folder: str = "actors"
        template: str = Path("hsl/template.hsl").read_text()
        # template: str = Path(HSL_FILENAME).read_text()

        print(str(output_path).replace('\\', '/'))
        return template.replace(
            "{ACTORS_FOLDER}",
            actors_folder
        ).replace(
            "{CLAPPERBOARD_NAME}",
            clapperboard_base_name
        ).replace(
            "{EXPORT_DIR}",
            str(output_path).replace('\\', '/')
        )