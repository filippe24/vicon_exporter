import unittest
from pathlib import Path

from configuration.settings import RETARGET_GENERAL_TEMPLATE
from exporter.aligned_export_pipeline import (
    AlignedExportPlan,
    generate_aligned_actor_export_hsl,
)
from exporter.export_pipeline import generate_hsl
from exporter.general_retarget_pipeline import generate_general_retarget_hsl


class ActorFilenameCollisionTests(unittest.TestCase):
    def assert_collision_aware(self, hsl: str) -> None:
        self.assertIn("int $j;", hsl)
        self.assertIn("string $actor_file_stem;", hsl)
        self.assertIn("$actor_file_stem = $first;", hsl)
        self.assertIn("$j != $i", hsl)
        self.assertIn("`strLeft $sel[$j] 3` == $first", hsl)
        self.assertIn("$actor_file_stem = $sel[$i];", hsl)

    def test_classic_export_uses_full_name_only_for_colliding_prefixes(self):
        hsl = generate_hsl(Path("take/exported"))
        self.assert_collision_aware(hsl)
        for extension in ("c3d", "fbx", "bvh", "mcp"):
            self.assertIn(f'$actor_file_stem + "_.{extension}"', hsl)

    def test_saved_vsr_retarget_uses_same_collision_rule(self):
        hsl = generate_general_retarget_hsl(
            template_path=RETARGET_GENERAL_TEMPLATE,
            output_path=Path("take/exported"),
            retarget_vsr_file_path=Path("models/basic.vsr"),
        )
        self.assert_collision_aware(hsl)
        self.assertIn('$actor_file_stem + "_retargeted_.fbx"', hsl)

    def test_aligned_export_uses_same_collision_rule(self):
        root = Path("take/aligned_exports")
        plan = AlignedExportPlan(
            take_dir=Path("take"),
            export_yaml_path=Path("take/.aligner/take.export.yaml"),
            output_root=root,
            actors_dir=root / "actors",
            retargeted_dir=root / "retargeted",
            reports_dir=root / "reports",
            scripts_dir=root / "scripts",
            mocap_entries=[],
            start_frame=10,
            end_frame=20,
        )
        hsl = generate_aligned_actor_export_hsl(plan)
        self.assert_collision_aware(hsl)
        self.assertIn('$actor_file_stem + "_aligned.mcp"', hsl)


if __name__ == "__main__":
    unittest.main()
