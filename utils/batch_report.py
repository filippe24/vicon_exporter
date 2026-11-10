"""Collect operation outcomes while preserving live console progress.

With a progress file, every operation also appends a JSON line when it starts and when it ends, which
the status window reads while the export runs. Creating `<progress>.stop` skips the remaining operations.
"""

import io
import json
import re
import sys
import time
from collections import Counter
from contextlib import redirect_stdout
from datetime import datetime
from functools import wraps
from pathlib import Path

_SHOGUN_TIME = re.compile(r"shogun time: ([\d.]+) s")
_SHOGUN_LOG = re.compile(r"full Shogun log: (.+)$")


class _Tee(io.StringIO):
    def __init__(self, stream):
        super().__init__()
        self.stream = stream

    def write(self, value):
        self.stream.write(value)
        return super().write(value)

    def flush(self):
        self.stream.flush()


class BatchReport:
    def __init__(self, root: Path, path: Path | None = None, progress: Path | None = None, on_done=None):
        """`path`: where finish() writes the JSON; by default a new file in root/.vicon_exporter_reports/.
        `on_done(row)` runs after each operation."""
        self.root = root
        self.path = path
        self.progress = progress
        self.on_done = on_done
        self.rows = []

    def stopped(self) -> bool:
        return self.progress is not None and self.progress.with_suffix(".stop").exists()

    def track(self, function, label, steps=()):
        """`steps`: the export status steps the operation runs, or a function of its keyword arguments."""

        @wraps(function)
        def run(*args, **kwargs):
            candidate = kwargs.get("take_dir", args[0] if args else self.root)
            take = Path(candidate) if isinstance(candidate, (str, Path)) else self.root
            operation = label(kwargs) if callable(label) else label
            keys = list(steps(kwargs) if callable(steps) else steps)
            if self.stopped():
                self._add({"take": str(take), "operation": operation, "status": "SKIPPED",
                           "detail": ["stopped before it started"], "steps": keys})
                return None
            self._event({"event": "start", "take": str(take), "operation": operation, "steps": keys})
            capture = _Tee(sys.stdout)
            started = time.perf_counter()
            result = None
            error = None
            with redirect_stdout(capture):
                try:
                    result = function(*args, **kwargs)
                except (OSError, RuntimeError, ValueError) as exc:
                    error = str(exc)
                    print(f"   FAILED {operation}: {exc}")
            seconds = round(time.perf_counter() - started, 1)
            lines = capture.getvalue().splitlines()
            shogun_seconds = round(sum(float(m[1]) for line in lines if (m := _SHOGUN_TIME.search(line))), 1)
            if isinstance(result, str) and result:
                lines.append(f"warning: {result}")
            # Successful BVH recovery resolves errors from the preceding attempt.
            recovery = max(
                (
                    i
                    for i, line in enumerate(lines)
                    if "BVH exported with static hand/finger fallback." in line
                    or "warning: BVH skipped." in line
                ),
                default=-1,
            )
            failures = [
                line.strip()
                for line in lines[recovery + 1 :]
                if re.search(
                    r"ERROR:|FAILED |warning:.*failed|ERROR:.*not found", line, re.I
                )
            ]
            warnings = [line.strip() for line in lines if "warning:" in line.lower()]
            kept = any(
                "keeping " in line.lower() or "already exported" in line.lower()
                for line in lines
            )
            exported = any(
                "Saved file " in line or "Exported prop:" in line for line in lines
            )
            status = (
                "FAILED"
                if error or failures
                else "WARNING"
                if warnings
                else "KEPT"
                if kept and not exported
                else "OK"
            )
            if (
                status == "OK"
                and not exported
                and any(
                    "skipping " in line.lower() or "no visible data" in line.lower()
                    for line in lines
                )
            ):
                status = "SKIPPED"
            detail = failures or warnings or ([error] if error else [])
            logs = [m[1] for line in lines if (m := _SHOGUN_LOG.search(line))]
            self._add(
                {
                    "take": str(take),
                    "operation": operation,
                    "status": status,
                    "detail": detail,
                    "seconds": seconds,
                    "shogun_seconds": shogun_seconds,
                    "steps": keys,
                    "log": logs[-1] if logs else "",
                }
            )
            return result

        return run

    def record_failure(self, take, operation, error, steps=()):
        self._add(
            {
                "take": str(take),
                "operation": operation,
                "status": "FAILED",
                "detail": [str(error)],
                "steps": list(steps),
            }
        )

    def _add(self, row):
        self.rows.append(row)
        self._event({"event": "done", **row})
        if self.on_done is not None:
            self.on_done(row)

    def _event(self, event):
        if self.progress is None:
            return
        try:
            with open(self.progress, "a", encoding="utf-8") as handle:
                handle.write(json.dumps({"time": datetime.now().isoformat(timespec="seconds"), **event}) + "\n")
        except OSError as error:
            print(f"   warning: could not write progress: {error}")

    def finish(self):
        print("\nBATCH RESULTS")
        print(
            " | ".join(
                f"{key}: {value}"
                for key, value in sorted(
                    Counter(r["status"] for r in self.rows).items()
                )
            )
        )
        for row in self.rows:
            try:
                take = str(Path(row["take"]).relative_to(self.root)) or "."
            except ValueError:
                take = row["take"]
            timing = f" | {row['seconds']:.0f} s (Shogun {row['shogun_seconds']:.0f} s)" if "seconds" in row else ""
            print(f"  {row['status']:7} | {take} | {row['operation']}{timing}")
            if row["detail"]:
                print(f"            {row['detail'][0]}")
        path = self.path or self.root / ".vicon_exporter_reports" / f"batch_{datetime.now():%Y%m%d_%H%M%S_%f}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.rows, indent=2), encoding="utf-8")
        print(f"  Detailed results: {path}")
