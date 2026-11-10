import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from exporter.aligned_scene_extras import (
    aligned_scene_extras_part,
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

    def part(self, **options):
        self.stage = self.take / "stage" / "scene_extras"
        return aligned_scene_extras_part(self.take, self.take / "stage", **options)

    def test_keep_adds_combined_without_changing_individual_props(self):
        existing = self.props / "cup.c3d"
        existing.write_text("original")
        part = self.part(combined=True)
        self.assertEqual(part.steps, ["all_props"])
        self.assertIn("collapseSubjects true", part.hsl)
        (self.stage / "all_props.c3d").write_text("combined")
        (self.stage / "individuals/__vicon_exporter_all_props__.c3d").touch()
        part.finish()
        name = read_extra_outputs(self.root)["all_props"]
        self.assertEqual(name, "__vicon_exporter_all_props___1.c3d")
        self.assertEqual(existing.read_text(), "original")
        self.assertIsNone(self.part(combined=True))

    def test_calibration_option_skips_other_folders(self):
        self.assertIsNone(self.part(calibration_markers=True))

    def test_calibration_parent_is_case_insensitive_and_filters_samples(self):
        self.take = self.take / "Room_CALIBRATION" / "001"
        part = self.part(calibration_markers=True)
        self.assertIn('selectByName "_*" -type Marker;', part.hsl)
        self.assertIn("getTrajectories", part.hsl)
        self.assertIn("-writeUnlabeled true", part.hsl)
        (self.stage / "calibration_markers.c3d").write_text("free")
        part.finish()
        self.assertIn("calibration_markers", read_extra_outputs(self.take / "aligned_exports"))

    def test_overwrite_keeps_previous_aggregate_until_finish(self):
        report = self.root / "reports/aligned_scene_extras.yaml"
        report.parent.mkdir()
        report.write_text(yaml.safe_dump({"outputs": {"all_props": "aggregate.c3d"}}))
        old = self.props / "aggregate.c3d"
        old.write_text("previous")
        self.part(combined=True, overwrite=True)
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
