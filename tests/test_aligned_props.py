import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

from exporter.aligned_props_pipeline import export_aligned_props, read_prop_crop


class AlignedPropsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.take = Path(self.temp.name)
        self.data = self.take / ".aligner"
        self.data.mkdir()
        self.output = self.take / "aligned_exports" / "props"

    def write_ranges(self, rows, grouped=False):
        tracks = [
            dict(
                name=name,
                track_type="MOCAP",
                source_path=f"exported/actors/{name}",
                derived_tracks=[
                    dict(
                        track_type="mocap",
                        local_start_frame=start,
                        local_end_frame=end,
                        sample_rate=120,
                    )
                ],
            )
            for name, start, end in rows
        ]
        payload = {"groups": [{"tracks": tracks}]} if grouped else {"timebases": tracks}
        (self.data / "take.export.yaml").write_text(yaml.safe_dump(payload))

    def test_c3d_only_first_and_extremes(self):
        self.write_ranges(
            [("actor.bvh", 0, 1000), ("b.c3d", 20, 30), ("a.c3d", 10, 40)]
        )
        _, entries, start, end, warning = read_prop_crop(self.take)
        self.assertEqual((start, end), (20, 30))
        self.assertEqual(len(entries), 2)
        self.assertIn("ranges differ", warning)
        self.assertEqual(read_prop_crop(self.take, "extremes")[2:4], (10, 40))

    def test_matching_grouped_ranges_have_no_warning(self):
        self.write_ranges([("a.c3d", 20, 30), ("b.c3d", 20, 30)], grouped=True)
        self.assertIsNone(read_prop_crop(self.take)[4])

    def test_no_c3d_does_not_fall_back_to_bvh(self):
        self.write_ranges([("a.bvh", 20, 30)])
        with self.assertRaisesRegex(ValueError, "No C3D"):
            read_prop_crop(self.take)

    def test_invalid_range_is_rejected(self):
        self.write_ranges([("a.c3d", 30, 20)])
        with self.assertRaisesRegex(ValueError, "Invalid"):
            read_prop_crop(self.take)

    def prepare_existing(self):
        self.write_ranges([("a.c3d", 20, 30)])
        self.output.mkdir(parents=True)
        (self.output / "unused.c3d").write_text("old")

    def export(self, **kwargs):
        return export_aligned_props(
            self.take, self.take / "take.mcp", Path("shogun"), **kwargs
        )

    def test_keep_preserves_existing_group(self):
        self.prepare_existing()
        with patch("exporter.aligned_props_pipeline.run_shogun") as run:
            self.export()
        run.assert_not_called()
        self.assertEqual((self.output / "unused.c3d").read_text(), "old")

    def test_failed_overwrite_preserves_previous_exports(self):
        self.prepare_existing()
        with patch(
            "exporter.aligned_props_pipeline.run_shogun",
            side_effect=RuntimeError("failed"),
        ):
            with self.assertRaises(RuntimeError):
                self.export(overwrite=True)
        self.assertEqual((self.output / "unused.c3d").read_text(), "old")

    def test_successful_overwrite_removes_unused_props(self):
        self.prepare_existing()

        def fake_run(source, script, output, executable):
            (output.parent / "Coffee cup.c3d").write_text("cropped")

        with patch("exporter.aligned_props_pipeline.run_shogun", side_effect=fake_run):
            self.export(overwrite=True)
        self.assertFalse((self.output / "unused.c3d").exists())
        self.assertEqual((self.output / "Coffee cup.c3d").read_text(), "cropped")
        report = yaml.safe_load(
            (self.output.parent / "reports/aligned_props_summary.yaml").read_text()
        )
        self.assertEqual((report["start_frame"], report["end_frame"]), (20, 30))


if __name__ == "__main__":
    unittest.main()
