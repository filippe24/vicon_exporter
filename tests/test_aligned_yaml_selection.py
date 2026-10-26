import os
import tempfile
import unittest
from pathlib import Path

from exporter.aligned_export_pipeline import (
    _find_aligner_export_yaml,
    load_aligned_export_plan,
)
from exporter.aligned_props_pipeline import read_prop_crop


class AlignedYamlSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.take = Path(self.temp.name) / "renamed_take"
        self.take.mkdir()

    def export(self, relative_path, timestamp, content="{}"):
        path = self.take / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        os.utime(path, (timestamp, timestamp))
        return path

    def test_newest_full_export_wins_even_over_matching_take_name(self):
        self.export(".aligner/renamed_take.export.yaml", 1000)
        self.export(".aligner/001.export.yaml", 1000)
        newest = self.export(".aligner/I01_001.export.yaml", 2000)
        self.export(".aligner/I01_001.slim.export.yaml", 3000)
        self.assertEqual(_find_aligner_export_yaml(self.take), newest)

    def test_compares_modification_times_across_supported_locations(self):
        self.export(".aligner/take.export.yaml", 1000)
        newest = self.export("aligner._data/exports/take.export.yaml", 2000)
        self.assertEqual(_find_aligner_export_yaml(self.take), newest)

    def test_slim_only_fallback_uses_newest(self):
        self.export(".aligner/a.slim.export.yaml", 1000)
        newest = self.export(".aligner/z.slim.export.yaml", 2000)
        self.assertEqual(_find_aligner_export_yaml(self.take), newest)

    def test_slim_export_parses_actors_and_props_with_cropped_markers(self):
        slim_yaml = """- take_duration_sec: 564.675
  legend: (*) cropped exported

- file: Jam_.bvh (*)
  output_fps: 120.0
  local_start_sec: 36.75833333333334
  local_end_sec: 601.4333333333333
  local_start_frame: 4411
  local_end_frame: 72172

- file: Jam_.c3d (*)
  output_fps: 120.0
  local_start_sec: 36.75833333333334
  local_end_sec: 601.4333333333333
  local_start_frame: 4411
  local_end_frame: 72172

- file: clapperboard.c3d (*)
  output_fps: 120.0
  local_start_sec: 36.75833333333334
  local_end_sec: 601.4333333333333
  local_start_frame: 4411
  local_end_frame: 72172
"""
        self.export(".aligner/I01_001.slim.export.yaml", 2000, slim_yaml)
        plan = load_aligned_export_plan(self.take)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.start_frame, 4411)
        self.assertEqual(plan.end_frame, 72172)
        self.assertEqual(len(plan.mocap_entries), 1)
        self.assertEqual(plan.mocap_entries[0].name, "Jam_.bvh")
        self.assertEqual(plan.mocap_entries[0].sample_rate, 120.0)

        _, c3d_entries, start, end, warning = read_prop_crop(self.take)
        self.assertEqual(start, 4411)
        self.assertEqual(end, 72172)
        self.assertEqual(len(c3d_entries), 2)
        self.assertIsNone(warning)

    def test_full_export_normalizes_legacy_6_decimal_bvh_frame_time_drift(self):
        full_yaml = """groups:
- group: group_1
  tracks:
  - track_type: MOCAP
    name: Jam_.bvh
    stem: Jam_
    source_path: G:/take/exported/actors/Jam_.bvh
    timing:
      local_start_sec: 36.75833333333334
      local_end_sec: 601.4333333333333
    derived_tracks:
    - track_type: mocap
      name: Jam_.bvh
      path: G:/take/exported/actors/Jam_.bvh
      sample_rate: 120.00480019200768
      local_start_frame: 4411
      local_end_frame: 72175
  - track_type: MOCAP
    name: Jam_.c3d
    stem: Jam_
    source_path: G:/take/exported/actors/Jam_.c3d
    timing:
      local_start_sec: 36.75833333333334
      local_end_sec: 601.4333333333333
    derived_tracks:
    - track_type: mocap
      name: Jam_.c3d
      path: G:/take/exported/actors/Jam_.c3d
      sample_rate: 120.0
      local_start_frame: 4411
      local_end_frame: 72172
"""
        self.export(".aligner/I01_001.export.yaml", 2000, full_yaml)
        plan = load_aligned_export_plan(self.take)
        self.assertIsNotNone(plan)
        self.assertEqual(plan.start_frame, 4411)
        self.assertEqual(plan.end_frame, 72172)
        self.assertEqual(plan.mocap_entries[0].sample_rate, 120.0)

    def test_no_exports_returns_none(self):
        self.assertIsNone(_find_aligner_export_yaml(self.take))
