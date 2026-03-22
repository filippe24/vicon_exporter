# exporter/export_pipeline.py

from pathlib import Path


def generate_hsl(export_dir: Path, actors_folder: str = "actors", clapperboard_base_name: str = "clapperboard_"):
    ''' code to generate dynamic hls file to run in shogun post.'''
    if export_dir:
        export_dir:Path = Path(export_dir.as_posix())

        actors_folder: str = "actors"
        template: str = Path("hsl/template.hsl").read_text()

        print(str(export_dir).replace('\\', '/'))
        return template.replace(
            "{ACTORS_FOLDER}",
            actors_folder
        ).replace(
            "{CLAPPERBOARD_NAME}",
            clapperboard_base_name
        ).replace(
            "{EXPORT_DIR}",
            str(export_dir).replace('\\', '/')
        )