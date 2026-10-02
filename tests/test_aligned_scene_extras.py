import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from exporter.aligned_scene_extras import (
    export_aligned_scene_extras,
    protect_extra_names,
    read_extra_outputs,
)


class SceneExtrasTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.take = Path(self.temp.name)
        self.root = self.take / "aligned_exports"
        self.props = self.root / "props"
        self.props.mkdir(parents=True)
        self.crop = patch(
            "exporter.aligned_scene_extras.read_prop_crop",
            return_value=(
                self.take / "take.export.yaml",
                [],
                10,
                20,
                None,
            ),
        )
        self.crop.start()
        self.addCleanup(self.crop.stop)

    def export(self, **options):
        return export_aligned_scene_extras(
            self.take, self.take / "take.mcp", Path("shogun"), **options
        )

    def test_keep_adds_combined_without_changing_individual_props(self):
        existing = self.props / "cup.c3d"
        existing.write_text("original")

        def run(_source, script, output, _exe):
            self.assertIn("collapseSubjects true", script.read_text())
            (output.parent / "all_props.c3d").write_text("combined")
            (output.parent / "individuals/__vicon_exporter_all_props__.c3d").touch()

        with patch("exporter.aligned_scene_extras.run_shogun", side_effect=run):
            self.export(combined=True)
        name = read_extra_outputs(self.root)["all_props"]
        self.assertEqual(name, "__vicon_exporter_all_props___1.c3d")
        self.assertEqual(existing.read_text(), "original")
        with patch("exporter.aligned_scene_extras.run_shogun") as run:
            self.export(combined=True)
        run.assert_not_called()

    def test_calibration_option_skips_other_folders(self):
        with patch("exporter.aligned_scene_extras.run_shogun") as run:
            self.export(calibration_markers=True)
        run.assert_not_called()

    def test_calibration_parent_is_case_insensitive_and_filters_samples(self):
        self.take = self.take / "Room_CALIBRATION" / "001"

        def run(_source, script, output, _exe):
            hsl = script.read_text()
            self.assertIn('selectByName "_*" -type Marker;', hsl)
            self.assertIn("getKeys Translation", hsl)
            self.assertIn("-writeUnlabeled true", hsl)
            (output.parent / "calibration_markers.c3d").write_text("free")

        with patch("exporter.aligned_scene_extras.run_shogun", side_effect=run):
            self.export(calibration_markers=True)
        root = self.take / "aligned_exports"
        self.assertIn("calibration_markers", read_extra_outputs(root))

    def test_overwrite_failure_preserves_previous_aggregate(self):
        report = self.root / "reports/aligned_scene_extras.yaml"
        report.parent.mkdir()
        report.write_text(yaml.safe_dump({"outputs": {"all_props": "aggregate.c3d"}}))
        old = self.props / "aggregate.c3d"
        old.write_text("previous")
        with (
            patch(
                "exporter.aligned_scene_extras.run_shogun",
                side_effect=RuntimeError("failed"),
            ),
            self.assertRaises(RuntimeError),
        ):
            self.export(combined=True, overwrite=True)
        self.assertEqual(old.read_text(), "previous")

    def test_later_prop_collision_relocates_aggregate(self):
        report = self.root / "reports/aligned_scene_extras.yaml"
        report.parent.mkdir()
        report.write_text(yaml.safe_dump({"outputs": {"all_props": "cup.c3d"}}))
        (self.props / "cup.c3d").write_text("aggregate")
        protected = protect_extra_names(self.root, {"cup.c3d"})
        name = read_extra_outputs(self.root)["all_props"]
        self.assertIn(name.casefold(), protected)
        self.assertFalse((self.props / "cup.c3d").exists())
        self.assertEqual((self.props / name).read_text(), "aggregate")
