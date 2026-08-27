import unittest
from pathlib import Path

from exporter.aligned_export_pipeline import AlignedExportPlan
from exporter.export_pipeline import generate_hsl
from main import _is_unsupported_bvh_export_error
from wrapper.shogun_runner import ShogunError


class BvhFallbackTests(unittest.TestCase):
    def test_classic_hsl_exports_bvh_by_default(self):
        hsl = generate_hsl(Path("take/exported"), "actors")

        self.assertIn("saveFile -s $filename_bvh;", hsl)

    def test_classic_hsl_can_skip_bvh_without_dropping_other_actor_exports(self):
        hsl = generate_hsl(Path("take/exported"), "actors", include_bvh=False)

        self.assertNotIn("saveFile -s $filename_bvh;", hsl)
        self.assertIn("saveFile -s $filename_c3d;", hsl)
        self.assertIn("saveFile -s $filename_fbx;", hsl)
        self.assertIn("saveFile -s $filename_mcp;", hsl)

    def test_classic_hsl_can_try_static_hand_bvh(self):
        hsl = generate_hsl(Path("take/exported"), "actors", static_hand_bvh=True)

        self.assertIn('selectByName "*Hand*" -type SolvingBone', hsl)
        self.assertIn('setProperty "DOF" "Rx" true;', hsl)
        self.assertIn('setProperty "DOF" "Ry" true;', hsl)
        self.assertIn('setProperty "DOF" "Rz" true;', hsl)
        self.assertIn("bvhExportOptions -writeDofs true;", hsl)
        self.assertIn("saveFile -s $filename_bvh;", hsl)

    def test_detects_zero_dof_bvh_failure(self):
        error = ShogunError(
            "shogun failed",
            returncode=1,
            output=(
                "ERROR: RightHand contains multiple zero dof end bones which is "
                "not supported by the BVH format.\n"
                'ERROR: Failed to save file "take/exported/actors/Isa_.bvh"'
            ),
        )

        self.assertTrue(_is_unsupported_bvh_export_error(error))

    def test_does_not_treat_other_shogun_failures_as_bvh_fallbacks(self):
        error = ShogunError(
            "shogun failed",
            returncode=1,
            output='ERROR: Failed to save file "take/exported/actors/Isa_.fbx"',
        )

        self.assertFalse(_is_unsupported_bvh_export_error(error))


class AlignedBvhFallbackTests(unittest.TestCase):
    def test_aligned_hsl_can_skip_bvh_without_dropping_actor_mcp(self):
        from exporter.aligned_export_pipeline import generate_aligned_actor_export_hsl

        plan = AlignedExportPlan(
            take_dir=Path("take"),
            export_yaml_path=Path("take/aligner._data/take.export.yaml"),
            output_root=Path("take/aligned_exports"),
            actors_dir=Path("take/aligned_exports/actors"),
            retargeted_dir=Path("take/aligned_exports/retargeted"),
            reports_dir=Path("take/aligned_exports/reports"),
            scripts_dir=Path("take/aligned_exports/scripts"),
            mocap_entries=[],
            start_frame=10,
            end_frame=20,
        )

        hsl = generate_aligned_actor_export_hsl(plan, include_bvh=False)

        self.assertNotIn("saveFile -s $filename_bvh;", hsl)
        self.assertIn("saveFile -s $filename_c3d;", hsl)
        self.assertIn("saveFile -s $filename_fbx;", hsl)
        self.assertIn("saveFile -s $filename_mcp;", hsl)

    def test_aligned_hsl_can_try_static_hand_bvh(self):
        from exporter.aligned_export_pipeline import generate_aligned_actor_export_hsl

        plan = AlignedExportPlan(
            take_dir=Path("take"),
            export_yaml_path=Path("take/aligner._data/take.export.yaml"),
            output_root=Path("take/aligned_exports"),
            actors_dir=Path("take/aligned_exports/actors"),
            retargeted_dir=Path("take/aligned_exports/retargeted"),
            reports_dir=Path("take/aligned_exports/reports"),
            scripts_dir=Path("take/aligned_exports/scripts"),
            mocap_entries=[],
            start_frame=10,
            end_frame=20,
        )

        hsl = generate_aligned_actor_export_hsl(plan, static_hand_bvh=True)

        self.assertIn('selectByName "*Hand*" -type SolvingBone', hsl)
        self.assertIn('setProperty "DOF" "Rx" true;', hsl)
        self.assertIn('setProperty "DOF" "Ry" true;', hsl)
        self.assertIn('setProperty "DOF" "Rz" true;', hsl)
        self.assertIn("bvhExportOptions -writeDofs true;", hsl)
        self.assertIn("saveFile -s $filename_bvh;", hsl)


if __name__ == "__main__":
    unittest.main()
