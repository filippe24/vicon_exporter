import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from exporter.aligned_group import Part, joined_hsl
from main import export_aligned_parts, export_aligned_take
from ui.menu import UserSelection
from wrapper.shogun_runner import ShogunError


def part(name, hsl, finished, **variants):
    return Part(name, [name], hsl, lambda: finished.append(name), **variants)


class JoinedHslTests(unittest.TestCase):
    def test_parts_keep_their_order_and_get_their_own_variables(self):
        script = joined_hsl([part("actors", "int $i; print $i;", []), part("props", "int $i;", [])])
        self.assertLess(script.index("// ---- actors"), script.index("// ---- props"))
        self.assertIn("int $p1_i; print $p1_i;", script)
        self.assertIn("int $p2_i;", script)

    def test_variant_falls_back_to_the_main_script(self):
        parts = [part("actors", "bvh;", [], without_bvh_hsl="no bvh;"), part("props", "props;", [])]
        script = joined_hsl(parts, "without_bvh_hsl")
        self.assertIn("no bvh;", script)
        self.assertIn("props;", script)


class ExportPartsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.take = Path(self.temp.name)

    def export(self, parts, side_effect=None):
        with patch("main.run_shogun", side_effect=side_effect) as shogun:
            export_aligned_parts(self.take, Path("ShogunPostCL.exe"), mcp_file=self.take / "take.mcp", parts=parts)
        return shogun

    def test_one_shogun_run_then_every_part_finishes(self):
        finished = []
        shogun = self.export([part("actors", "a;", finished), part("props", "b;", finished)])
        shogun.assert_called_once()
        script = shogun.call_args.kwargs["hsl_file"]
        self.assertEqual(script.name, "aligned_exports.hsl")
        self.assertIn("b;", script.read_text())
        self.assertEqual(finished, ["actors", "props"])

    def test_failed_run_finishes_nothing(self):
        finished = []
        with self.assertRaises(ShogunError):
            self.export([part("props", "b;", finished)], ShogunError("shogun failed", 43, "ERROR: x"))
        self.assertEqual(finished, [])

    def test_bvh_failure_reruns_the_joined_script_with_static_hands(self):
        finished = []
        bvh_error = ShogunError(
            "shogun failed",
            1,
            "ERROR: RightHand contains multiple zero dof end bones which is not supported by the BVH format.\n"
            'ERROR: Failed to save file "take/aligned_exports/actors/Isa_aligned.bvh"',
        )
        parts = [part("actors", "bvh;", finished, static_hand_hsl="static;"), part("props", "b;", finished)]
        shogun = self.export(parts, [bvh_error, None])
        retry = shogun.call_args_list[1].kwargs["hsl_file"].read_text()
        self.assertIn("static;", retry)
        self.assertIn("b;", retry)
        self.assertEqual(finished, ["actors", "props"])


class ExportTakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.take = Path(self.temp.name)
        (self.take / "take.mcp").touch()
        self.selection = UserSelection()
        self.selection.run_aligned_export = self.selection.run_aligned_props = True
        self.batch = MagicMock()
        self.run_parts = MagicMock()

    def test_a_step_that_cannot_start_does_not_stop_the_others(self):
        actors = Part("actors", ["actors"], "a;", lambda: None)
        with (
            patch("main.aligned_actors_part", return_value=actors),
            patch("main.aligned_props_part", side_effect=ValueError("No C3D crop entries")),
        ):
            warnings = export_aligned_take(self.take, self.selection, self.batch, self.run_parts)
        self.assertEqual(self.run_parts.call_args.kwargs["parts"], [actors])
        self.batch.record_failure.assert_called_once()
        self.assertEqual(self.batch.record_failure.call_args.args[3], ["props"])
        self.assertIn("No C3D crop entries", warnings[0])

    def test_staging_folder_is_removed(self):
        def prepare(_take_dir, stage, **_options):
            (stage / "props").mkdir(parents=True)
            return Part("props", ["props"], "b;", lambda: None)

        with (
            patch("main.aligned_actors_part", return_value=None),
            patch("main.aligned_props_part", side_effect=prepare),
        ):
            export_aligned_take(self.take, self.selection, self.batch, self.run_parts)
        self.run_parts.assert_called_once()
        self.assertEqual(list((self.take / "aligned_exports").glob("staging_*")), [])

    def test_nothing_selected_runs_nothing(self):
        self.selection.run_aligned_export = self.selection.run_aligned_props = False
        self.assertEqual(export_aligned_take(self.take, self.selection, self.batch, self.run_parts), [])
        self.run_parts.assert_not_called()


if __name__ == "__main__":
    unittest.main()
