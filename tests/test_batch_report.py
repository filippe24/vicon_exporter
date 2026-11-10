import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from utils.batch_report import BatchReport
from wrapper.shogun_runner import ShogunError


class BatchReportTests(unittest.TestCase):
    def test_multiple_jobs_continue_after_failure_and_summarize(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            report = BatchReport(root)

            def fail(_take_dir):
                raise ShogunError(
                    "shogun failed",
                    1,
                    "ERROR: Line 35: IntVar array index out of range",
                )

            def keep(_take_dir):
                print("keeping existing aligned exports")

            def success(_take_dir):
                print("Exported prop: cup")

            with redirect_stdout(io.StringIO()) as console:
                report.track(fail, "Props")(root / "take1")
                report.track(keep, "Actors")(root / "take1")
                report.track(success, "Props")(root / "take2")
                report.finish()
            self.assertEqual(
                [r["status"] for r in report.rows], ["FAILED", "KEPT", "OK"]
            )
            self.assertIn("Line 35", console.getvalue())
            self.assertEqual(
                len(list((root / ".vicon_exporter_reports").glob("*.json"))), 1
            )

    def test_caught_failure_is_not_reported_as_success(self):
        report = BatchReport(Path("takes"))

        def operation(_take_dir):
            print("warning: actor export failed: skeleton missing")

        with redirect_stdout(io.StringIO()):
            report.track(operation, "Actors")(Path("takes/001"))
        self.assertEqual(report.rows[0]["status"], "FAILED")

    def test_successful_bvh_recovery_is_a_warning(self):
        report = BatchReport(Path("takes"))

        def operation(_take_dir):
            print("ERROR: Failed to save file actor.bvh")
            print("Saved file actor.bvh")
            print("warning: BVH exported with static hand/finger fallback.")

        with redirect_stdout(io.StringIO()):
            report.track(operation, "Actors")(Path("takes/001"))
        self.assertEqual(report.rows[0]["status"], "WARNING")


class ProgressTests(unittest.TestCase):
    def test_progress_events_steps_log_and_stop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            progress = root / "progress.jsonl"
            ended = []
            report = BatchReport(root, progress=progress, on_done=ended.append)

            def actors(**_options):
                print("   full Shogun log: C:/take/scripts/actors.shogun.log")
                print("ERROR: Failed to save file")

            with redirect_stdout(io.StringIO()):
                report.track(actors, "Aligned actors", lambda _options: ["actors"])(
                    take_dir=root / "take1", export_standard=True
                )
                progress.with_suffix(".stop").touch()
                report.track(actors, "Aligned actors", ["actors"])(take_dir=root / "take2", export_standard=True)
            events = [json.loads(line) for line in progress.read_text().splitlines()]
            self.assertEqual([event["event"] for event in events], ["start", "done", "done"])
            self.assertEqual(events[1]["steps"], ["actors"])
            self.assertEqual(events[1]["status"], "FAILED")
            self.assertEqual(events[1]["log"], "C:/take/scripts/actors.shogun.log")
            self.assertEqual(events[2]["status"], "SKIPPED")
            self.assertEqual([row["status"] for row in ended], ["FAILED", "SKIPPED"])
