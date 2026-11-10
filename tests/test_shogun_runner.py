import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from wrapper import shogun_runner


class FakeStdin:
    def __init__(self):
        self.text = ""

    def write(self, text):
        self.text += text

    def close(self):
        pass


class FakeShogun:
    """Records the command; in -old mode it writes the output MCP like ShogunPostCL."""

    def __init__(self, cmd, returncode=0, without_runscript=False):
        self.cmd = cmd
        self.stdin = FakeStdin()
        self.stdout = ["Saved file\n"]
        self.returncode = returncode
        if cmd[1] == "-runScript" and without_runscript:  # like Shogun Post 1.20
            self.stdout, self.returncode = ["* unknown argument: -runScript\n"], 1
        if cmd[1] == "-old":
            Path(cmd[-1]).write_text("full take copy")

    def wait(self):
        return self.returncode


class ShogunRunnerTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.scripts = Path(temp.name)
        self.hsl = self.scripts / "export.hsl"
        self.hsl.write_text('saveFile -s "D:/out/markers.c3d";\n')
        self.take = Path(r"D:\takes\take 1\take.mcp")

    def run_shogun(self, mode, returncode=0, without_runscript=False):
        calls = []

        def popen(cmd, **_kwargs):
            calls.append(FakeShogun(cmd, returncode, without_runscript))
            return calls[-1]

        with (
            patch.object(shogun_runner, "resolve_shogun_path", return_value=Path("ShogunPostCL.exe")),
            patch.object(shogun_runner.subprocess, "Popen", side_effect=popen),
        ):
            shogun_runner.run_shogun(self.take, self.hsl, Path("ShogunPostCL.exe"), mode=mode)
        self.calls = calls
        return calls[0]

    def test_runscript_loads_the_take_and_writes_no_mcp(self):
        call = self.run_shogun("runscript")
        script = self.scripts / "export.runscript.hsl"
        self.assertEqual(call.cmd[1:], ["-runScript", str(script)])
        self.assertEqual(
            script.read_text(), 'loadFile "D:/takes/take 1/take.mcp";\nsaveFile -s "D:/out/markers.c3d";\n'
        )
        self.assertEqual(call.stdin.text, "exit\n")
        log = (self.scripts / "export.shogun.log").read_text()
        self.assertRegex(log, r"\[ +[\d.]+\] Saved file")
        self.assertIn("shogun time:", log)

    def test_old_mode_deletes_the_output_mcp(self):
        call = self.run_shogun("old")
        out_file = Path(call.cmd[-1])
        self.assertEqual(out_file.parent.parent, self.scripts)
        self.assertFalse(out_file.exists())
        self.assertEqual(sorted(path.name for path in self.scripts.iterdir()), ["export.hsl", "export.shogun.log"])

    def test_nonzero_exit_raises(self):
        with self.assertRaises(shogun_runner.ShogunError):
            self.run_shogun("runscript", returncode=43)

    def test_shogun_without_runscript_falls_back_to_old_mode(self):
        self.addCleanup(shogun_runner._WITHOUT_RUNSCRIPT.clear)
        self.run_shogun("runscript", without_runscript=True)
        self.assertEqual([call.cmd[1] for call in self.calls], ["-runScript", "-old"])
        self.run_shogun("runscript", without_runscript=True)
        self.assertEqual([call.cmd[1] for call in self.calls], ["-old"])


if __name__ == "__main__":
    unittest.main()
