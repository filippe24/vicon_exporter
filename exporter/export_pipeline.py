# exporter/export_pipeline.py

from pathlib import Path


def generate_hsl(actors, export_dir: Path):
    ''' code to generate dynamic hls file to run in shogun post.'''
    export_dir = export_dir.as_posix()
    actor_blocks = []

    for actor in actors:
        actor_blocks.append(f'''
            selectByName "{actor}";
            selectChildren "{actor}";
            saveFile -s "{export_dir}/actors/{actor}.fbx";
            saveFile -s "{export_dir}/actors/{actor}.bvh";
        ''')

    # for actor in actors:
    #     actor_blocks.append(f'''
    #         select "{actor}\\*";
    #         saveFile -s "{export_dir}/actors/{actor}.fbx";
    #         saveFile -s "{export_dir}/actors/{actor}.bvh";
    #     ''')


    template = Path("hsl/template.hsl").read_text()

    return template.replace(
        "{ACTOR_EXPORTS}",
        "\n".join(actor_blocks)
    ).replace(
        "{EXPORT_DIR}",
        export_dir.as_posix()
    )