import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wrapper import shogun_runner


class FakeShogun:
    """Writes the output MCP it is given, like ShogunPostCL -old."""

    def __init__(self, cmd, **_kwargs):
        self.out_file = Path(cmd[-1])
        self.out_file.write_text("full take copy")
        self.stdout = []
        self.returncode = 0

    def wait(self):
        return 0


class ShogunRunnerTests(unittest.TestCase):
    def test_output_mcp_is_written_beside_the_script_then_deleted(self):
        with tempfile.TemporaryDirectory() as temp:
            scripts = Path(temp)
            hsl = scripts / "export.hsl"
            hsl.write_text("select;")
            calls = []

            def popen(cmd, **kwargs):
                calls.append(FakeShogun(cmd, **kwargs))
                return calls[-1]

            with (
                patch.object(shogun_runner, "resolve_shogun_path", return_value=Path("ShogunPostCL.exe")),
                patch.object(shogun_runner.subprocess, "Popen", side_effect=popen),
            ):
                shogun_runner.run_shogun(scripts / "take.mcp", hsl, None, Path("ShogunPostCL.exe"))
            self.assertEqual(calls[0].out_file.parent.parent, scripts)
            self.assertFalse(calls[0].out_file.exists())
            self.assertEqual(sorted(path.name for path in scripts.iterdir()), ["export.hsl", "export.shogun.log"])


if __name__ == "__main__":
    unittest.main()
