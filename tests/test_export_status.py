import os
import tempfile
import unittest
from pathlib import Path

import yaml

from exporter.export_status import (
    CURRENT,
    MISSING_OUTPUTS,
    NO_ALIGNMENT,
    NOT_APPLICABLE,
    NOT_EXPORTED,
    OUTDATED,
    UNVERIFIED,
    record_step,
    take_status,
)


class ExportStatusTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.take = Path(self.temp.name) / "S001" / "I01_001"
        self.take.mkdir(parents=True)
        self.aligned = self.take / "aligned_exports"

    def write_aligner(self, start=100, end=900):
        tracks = [
            {
                "name": name,
                "track_type": "MOCAP",
                "source_path": f"C:/elsewhere/exported/actors/{name}",
                "derived_tracks": [
                    {
                        "track_type": "mocap",
                        "local_start_frame": start,
                        "local_end_frame": end,
                        "sample_rate": 120,
                    }
                ],
            }
            for name in ("Jam_.c3d", "Jam_.bvh")
        ]
        path = self.take / ".aligner" / "I01_001.export.yaml"
        path.parent.mkdir(exist_ok=True)
        path.write_text(
            yaml.safe_dump({"format": "aligner.export.v2", "groups": [{"tracks": tracks}]})
        )

    def write_output(self, relative):
        path = self.aligned / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("data")
        return path

    def test_recorded_step_is_current_until_aligner_values_change(self):
        self.write_aligner()
        self.write_output("actors/Jam_.c3d")
        record_step(self.take, "actors")
        status = take_status(self.take)
        self.assertEqual(status.aligner_format, "aligner.export.v2")
        self.assertEqual(status.steps["actors"].state, CURRENT)
        self.assertEqual(status.steps["props"].state, NOT_EXPORTED)
        self.assertEqual(status.outdated, [])

        self.write_aligner(start=112, end=912)
        status = take_status(self.take)
        self.assertEqual(status.steps["actors"].state, OUTDATED)
        self.assertEqual(status.outdated, ["actors"])
        self.assertIn("100–900 → 112–912", status.steps["actors"].changes[0])

    def test_recorded_paths_are_relative(self):
        self.write_aligner()
        self.write_output("actors/Jam_.c3d")
        record_step(self.take, "actors")
        record = yaml.safe_load((self.aligned / "reports" / "export_status.yaml").read_text())
        actors = record["steps"]["actors"]
        self.assertEqual(actors["aligner_export_yaml"], ".aligner/I01_001.export.yaml")
        self.assertEqual(actors["outputs"], ["actors/Jam_.c3d"])

    def test_deleted_outputs_are_reported(self):
        self.write_aligner()
        output = self.write_output("retargeted/geeno/Jam_.fbx")
        record_step(self.take, "geeno")
        output.unlink()
        self.write_output("retargeted/geeno/other.fbx")
        self.assertEqual(take_status(self.take).steps["geeno"].state, MISSING_OUTPUTS)

    def test_outputs_from_before_tracking_use_old_report_frames(self):
        self.write_aligner()
        self.write_output("actors/Jam_.c3d")
        self.assertEqual(take_status(self.take).steps["actors"].state, UNVERIFIED)
        summary = self.write_output("reports/aligned_export_summary.yaml")
        summary.write_text(
            yaml.safe_dump({"actors": [{"name": "Jam_.bvh", "start_frame": 50, "end_frame": 900}]})
        )
        status = take_status(self.take).steps["actors"]
        self.assertEqual(status.state, OUTDATED)
        self.assertIn("50–900 → 100–900", status.changes[0])

    def test_alignment_saved_after_aligner_export_is_flagged(self):
        self.write_aligner()
        export = self.take / ".aligner" / "I01_001.export.yaml"
        state = export.with_name("I01_001.state.yaml")
        state.write_text("{}")
        os.utime(export, (1000, 1000))
        os.utime(state, (5000, 5000))
        status = take_status(self.take)
        self.assertIsNotNone(status.aligner_exported_at)
        self.assertTrue(status.aligner_export_stale)
        os.utime(export, (5000, 5000))
        self.assertFalse(take_status(self.take).aligner_export_stale)

    def test_take_without_aligner_export(self):
        status = take_status(self.take)
        self.assertIsNone(status.aligner_yaml)
        self.assertEqual(status.steps["actors"].state, NO_ALIGNMENT)
        self.assertEqual(status.steps["calibration_markers"].state, NOT_APPLICABLE)

    def test_calibration_markers_only_apply_to_calibration_takes(self):
        take = Path(self.temp.name) / "X01_calibration" / "001"
        take.mkdir(parents=True)
        self.take = take
        self.write_aligner()
        self.assertEqual(take_status(take).steps["calibration_markers"].state, NOT_EXPORTED)


if __name__ == "__main__":
    unittest.main()
