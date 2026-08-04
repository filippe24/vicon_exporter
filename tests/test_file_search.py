import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from utils.file_search import find_take_folders


class FindTakeFoldersTests(unittest.TestCase):
    def test_missing_root_returns_no_takes(self):
        with TemporaryDirectory() as temp_dir:
            missing_root = Path(temp_dir) / "missing"

            self.assertEqual(find_take_folders(missing_root), [])

    def test_hidden_aligner_folder_is_skipped(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            take_dir = root / "take"
            aligner_dir = root / ".aligner"
            take_dir.mkdir()
            aligner_dir.mkdir()
            (take_dir / "take.mcp").write_text("", encoding="utf-8")
            (aligner_dir / "internal.mcp").write_text("", encoding="utf-8")

            self.assertEqual(find_take_folders(root), [take_dir])


if __name__ == "__main__":
    unittest.main()
