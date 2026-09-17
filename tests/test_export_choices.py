import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from exporter.aligned_export_pipeline import AlignedExportPlan
from main import _find_original_take_mcp, process_aligned_export_and_retargeting, process_take


class ExportChoiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        take = Path(self.temp.name)
        root = take / "aligned_exports"
        self.plan = AlignedExportPlan(
            take, take / "take.export.yaml", root, root / "actors",
            root / "retargeted", root / "reports", root / "scripts", [], 10, 20,
        )
        self.source = take / "take.mcp"
        self.source.touch()

    def run_export(self, **choices):
        with (
            patch("main.load_aligned_export_plan", return_value=self.plan),
            patch("main._find_retarget_source_mcp", return_value=self.source),
            patch("main._export_aligned_standard") as standard,
            patch("main.run_shogun") as shogun,
        ):
            process_aligned_export_and_retargeting(
                self.plan.take_dir, Path("ShogunPostCL.exe"), **choices,
            )
        return standard, shogun

    def test_standard_only_does_not_retarget(self):
        standard, shogun = self.run_export(retarget_metahuman=False, retarget_geeno=False)
        standard.assert_called_once()
        shogun.assert_not_called()

    def test_keep_preserves_existing_standard_files(self):
        self.plan.actors_dir.mkdir(parents=True)
        existing = self.plan.actors_dir / "S01_aligned.fbx"
        existing.write_text("existing motion")
        standard, _ = self.run_export(retarget_metahuman=False, retarget_geeno=False)
        standard.assert_not_called()
        self.assertEqual(existing.read_text(), "existing motion")

    def test_overwrite_runs_existing_standard_group(self):
        self.plan.actors_dir.mkdir(parents=True)
        (self.plan.actors_dir / "S01_aligned.fbx").touch()
        standard, _ = self.run_export(
            overwrite=True, retarget_metahuman=False, retarget_geeno=False,
        )
        standard.assert_called_once()

    def test_keep_skips_existing_retarget_groups_without_standard_export(self):
        for name in ("metahuman", "geeno"):
            folder = self.plan.retargeted_dir / name
            folder.mkdir(parents=True)
            (folder / "existing.fbx").write_text("existing motion")
        standard, shogun = self.run_export(export_standard=False)
        standard.assert_not_called()
        shogun.assert_not_called()

    def test_retarget_only_runs_selected_target(self):
        with patch("main.generate_aligned_retarget_hsl", return_value="retarget;") as generate:
            standard, shogun = self.run_export(
                export_standard=False, retarget_metahuman=False, retarget_geeno=True,
            )
        standard.assert_not_called()
        shogun.assert_called_once()
        self.assertEqual(generate.call_args.kwargs["retarget_folder_name"], "geeno")

    def test_original_source_ignores_generated_mcp_files(self):
        for name in ("extra_exports_output.mcp", "processed.mcp", "temp_geeno_output.mcp"):
            (self.plan.take_dir / name).touch()
        self.assertEqual(_find_original_take_mcp(self.plan.take_dir), self.source)

    def test_keep_classic_preserves_partial_exports(self):
        folder = self.plan.take_dir / "exported" / "actors"
        folder.mkdir(parents=True)
        existing = folder / "S01_.fbx"
        existing.write_text("partial export")
        with patch("main.run_shogun") as shogun:
            process_take(self.plan.take_dir, Path("ShogunPostCL.exe"), force=False)
        shogun.assert_not_called()
        self.assertEqual(existing.read_text(), "partial export")


if __name__ == "__main__":
    unittest.main()
