import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from configuration.types import RetargetType
from exporter.aligned_export_pipeline import load_aligned_export_plan
from main import process_general_retargeting


class RetargetSourceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "take.mcp").touch()
        self.shogun = self.root / "ShogunPostCL.exe"

    def test_aligned_paths_are_rebased_from_windows_and_linux_metadata(self):
        data_dir = self.root / ".aligner"
        data_dir.mkdir()
        entries = []
        for actor, remote in (
            ("Jam_", "H:/My Drive/other-take/exported/actors/Jam_.bvh"),
            ("Jes_", "/home/al/GoogleDrive/other-take/exported/actors/Jes_.bvh"),
        ):
            entries.append(
                {
                    "track_type": "MOCAP",
                    "name": f"{actor}.bvh",
                    "stem": actor,
                    "source_path": remote,
                    "derived_tracks": [
                        {
                            "track_type": "mocap",
                            "local_start_frame": 10,
                            "local_end_frame": 20,
                            "sample_rate": 120,
                        }
                    ],
                }
            )
        (data_dir / f"{self.root.name}.export.yaml").write_text(
            json.dumps({"groups": [{"tracks": entries}]})
        )
        plan = load_aligned_export_plan(self.root)
        self.assertEqual(
            [entry.source_mcp_path for entry in plan.mocap_entries],
            [
                self.root / "exported/actors/Jam_.mcp",
                self.root / "exported/actors/Jes_.mcp",
            ],
        )

    def test_standalone_methods_write_separate_folders(self):
        for mode, folder in (
            (RetargetType.MANNEQUIN_ADJUSTED, "metahuman_legacy"),
            (RetargetType.MANNEQUIN, "metahuman_vsr"),
            (RetargetType.GEENO, "geeno"),
        ):
            with (
                patch(
                    "main.generate_general_retarget_hsl", return_value="retarget;"
                ) as generate,
                patch("main.run_shogun"),
            ):
                process_general_retargeting(
                    self.root, self.shogun, mode
                )
            self.assertEqual(
                generate.call_args.kwargs["actors_output_folder"],
                f"retargeted/{folder}",
            )
            self.assertTrue((self.root / "exported/retargeted" / folder).is_dir())


if __name__ == "__main__":
    unittest.main()
