import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from exporter.aligned_export_pipeline import AlignedExportPlan, AlignedMocapEntry
from exporter.metahuman_vicon_pipeline import (
    export_metahuman_vicon_actor,
    generate_metahuman_vicon_hsl,
)
from main import process_metahuman_vicon_retargeting


class ViconMetaHumanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.actor = self.root / "S01_.mcp"
        self.actor.touch()
        self.target = self.root / "ue5.fbx"
        self.target.touch()
        self.scripts = self.root / "Scripts" / "Retargeting"
        self.scripts.mkdir(parents=True)
        (self.scripts / "SetupRetargetToUE5Mannequin.hsl").touch()
        self.options = {
            "actor_mcp": self.actor,
            "target_fbx": self.target,
            "scripts_dir": self.scripts,
            "output_dir": self.root / "out",
            "generated_scripts_dir": self.root / "generated",
            "actor_name": "S01",
            "shogun_path": self.root / "ShogunPostCL.exe",
        }

    def test_documented_workflow_imports_target_then_sets_up_then_retargets(self):
        hsl = generate_metahuman_vicon_hsl(
            target_fbx=self.target,
            scripts_dir=self.scripts,
            output_fbx=self.root / "out.fbx",
            frame_range=(100, 200),
        )
        self.assertLess(
            hsl.index("loadFile "), hsl.index("SetupRetargetToUE5Mannequin;")
        )
        self.assertLess(
            hsl.index("SetupRetargetToUE5Mannequin;"), hsl.index("playRange 100 200;")
        )
        self.assertLess(
            hsl.index("playRange 100 200;"), hsl.index("retarget -selectedCharacters;")
        )
        self.assertIn("-importToCurrentSubject true", hsl)
        self.assertIn("getNumModules -sel` != 1", hsl)
        self.assertNotIn("setConstraint;", hsl)
        self.assertNotIn("solve;", hsl)
        self.assertNotIn("RightForeArm", hsl)

    def test_keep_does_not_launch_shogun(self):
        self.options["output_dir"].mkdir()
        existing = self.options["output_dir"] / "S01_metahuman_vicon.fbx"
        existing.write_text("old")
        with patch("exporter.metahuman_vicon_pipeline.run_shogun") as run:
            self.assertEqual(export_metahuman_vicon_actor(**self.options), existing)
        run.assert_not_called()
        self.assertEqual(existing.read_text(), "old")

    def test_failed_overwrite_preserves_old_fbx(self):
        self.options["output_dir"].mkdir()
        existing = self.options["output_dir"] / "S01_metahuman_vicon.fbx"
        existing.write_text("old")
        with (
            patch(
                "exporter.metahuman_vicon_pipeline.resolve_shogun_path",
                return_value=self.options["shogun_path"],
            ),
            patch("exporter.metahuman_vicon_pipeline.run_shogun"),
            self.assertRaisesRegex(RuntimeError, "produced no FBX"),
        ):
            export_metahuman_vicon_actor(**self.options, overwrite=True)
        self.assertEqual(existing.read_text(), "old")

    def test_success_commits_new_fbx_and_leaves_reusable_script(self):
        def produce_output(**kwargs):
            working = kwargs["out_file"].parent
            (working / "S01_metahuman_vicon_aligned.fbx").write_text("new")

        with (
            patch(
                "exporter.metahuman_vicon_pipeline.resolve_shogun_path",
                return_value=self.options["shogun_path"],
            ),
            patch(
                "exporter.metahuman_vicon_pipeline.run_shogun",
                side_effect=produce_output,
            ) as run,
        ):
            output = export_metahuman_vicon_actor(**self.options, frame_range=(10, 20))
        self.assertEqual(output.read_text(), "new")
        self.assertEqual(run.call_args.kwargs["mcp_file"], self.actor)
        hsl = run.call_args.kwargs["hsl_file"].read_text()
        self.assertIn(output.resolve().as_posix(), hsl)
        self.assertIn("playRange 10 20;", hsl)

    def test_missing_installed_setup_script_is_actionable(self):
        (self.scripts / "SetupRetargetToUE5Mannequin.hsl").unlink()
        with (
            patch(
                "exporter.metahuman_vicon_pipeline.resolve_shogun_path",
                return_value=self.options["shogun_path"],
            ),
            self.assertRaisesRegex(FileNotFoundError, "Vicon setup script missing"),
        ):
            export_metahuman_vicon_actor(**self.options)

    def test_full_take_batches_isolated_actor_mcps(self):
        actors = self.root / "exported" / "actors"
        actors.mkdir(parents=True)
        for name in ("S01_", "S02_"):
            (actors / f"{name}.mcp").touch()
        with patch("main.export_metahuman_vicon_actor") as export:
            process_metahuman_vicon_retargeting(self.root, self.options["shogun_path"])
        self.assertEqual(export.call_count, 2)
        self.assertEqual(
            [call.kwargs["actor_name"] for call in export.call_args_list],
            ["S01", "S02"],
        )
        for call in export.call_args_list:
            self.assertEqual(call.kwargs["actor_mcp"].parent, actors)
            self.assertIsNone(call.kwargs["frame_range"])

    def test_aligned_batch_uses_each_actor_range_and_separate_destination(self):
        entries = [
            AlignedMocapEntry(
                "S01_.bvh", "S01_", self.root / "exported/actors/S01_.bvh", 10, 20, 120
            ),
            AlignedMocapEntry(
                "S02_.bvh", "S02_", self.root / "exported/actors/S02_.bvh", 12, 22, 120
            ),
        ]
        root = self.root / "aligned_exports"
        plan = AlignedExportPlan(
            self.root,
            self.root / "take.export.yaml",
            root,
            root / "actors",
            root / "retargeted",
            root / "reports",
            root / "scripts",
            entries,
            10,
            22,
        )
        with (
            patch("main.load_aligned_export_plan", return_value=plan),
            patch("main.export_metahuman_vicon_actor") as export,
        ):
            process_metahuman_vicon_retargeting(
                self.root, self.options["shogun_path"], aligned=True
            )
        self.assertEqual(
            [call.kwargs["frame_range"] for call in export.call_args_list],
            [(10, 20), (12, 22)],
        )
        for call in export.call_args_list:
            self.assertEqual(call.kwargs["actor_mcp"].suffix, ".mcp")
            self.assertEqual(
                call.kwargs["output_dir"], root / "retargeted/metahuman_vicon"
            )


if __name__ == "__main__":
    unittest.main()
