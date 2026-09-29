import os
import tempfile
import unittest
from pathlib import Path

from exporter.aligned_export_pipeline import _find_aligner_export_yaml


class AlignedYamlSelectionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.take = Path(self.temp.name) / "renamed_take"
        self.take.mkdir()

    def export(self, relative_path, timestamp):
        path = self.take / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}")
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

    def test_no_exports_returns_none(self):
        self.assertIsNone(_find_aligner_export_yaml(self.take))
