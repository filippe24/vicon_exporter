import os
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

from main import selection_from_args
from tools.time_export import comparison, file_differences, written_since


class TimeExportTests(unittest.TestCase):
    def test_written_since_keeps_new_exports_only(self):
        with tempfile.TemporaryDirectory() as temp:
            take = Path(temp)
            old = take / "exported/actors/old.fbx"
            old.parent.mkdir(parents=True)
            old.write_text("old")
            os.utime(old, (0, 0))
            started = time.time() - 1
            for name in ("exported/actors/S01_.fbx", "aligned_exports/scripts/a.fbx", "exported/exporter.hsl"):
                path = take / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("new")
            self.assertEqual(written_since(take, started), {"exported/actors/S01_.fbx": 3})

    def test_comparison_lines_up_steps_and_totals(self):
        results = {
            "old": ([{"operation": "Aligned actors", "status": "OK", "seconds": 170.0, "shogun_seconds": 166.0}],
                    {}, 175.0),
            "runscript": ([{"operation": "Aligned actors", "status": "OK", "seconds": 85.0, "shogun_seconds": 82.0}],
                          {}, 90.0),
        }
        step, total = comparison(["old", "runscript"], results)
        self.assertEqual((step["old s"], step["runscript s"]), (170.0, 85.0))
        self.assertEqual((total["old s"], total["runscript shogun s"]), (175.0, 82.0))

    def test_file_differences(self):
        results = {
            "old": ([], {"a.c3d": 10, "b.fbx": 5}, 0),
            "runscript": ([], {"a.c3d": 12, "c.bvh": 1}, 0),
        }
        self.assertEqual(
            file_differences(["old", "runscript"], results),
            ["only in old: b.fbx", "only in runscript: c.bvh", "size differs: a.c3d (10 vs 12 bytes)"],
        )

    def test_original_step_runs_the_full_range_export_with_extras(self):
        with tempfile.TemporaryDirectory() as temp:
            args = SimpleNamespace(take=[Path(temp)], steps="original,actors", overwrite=True, prop_crop="first")
            selection = selection_from_args(args)
        self.assertTrue(selection.run_export and selection.include_tracking_props and selection.run_aligned_export)


if __name__ == "__main__":
    unittest.main()
