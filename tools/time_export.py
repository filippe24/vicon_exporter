"""Time the export of one take in each Shogun mode and compare them.

    uv run python tools/time_export.py --take D:/copy/take --steps original,actors,props,metahuman

Runs main.py on the take with Overwrite once per mode, then prints and saves the seconds of every
step, and checks that both modes wrote the same files. It replaces the take's exports, so run it on
a copy of the take.
"""

import argparse
import csv
import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

MAIN = Path(__file__).resolve().parent.parent / "main.py"
# Written by every run whatever the mode: scripts, logs and reports, not exports.
IGNORED_FOLDERS = {"scripts", "reports", ".vicon_exporter_reports"}
IGNORED_SUFFIXES = {".hsl", ".log", ".json", ".yaml"}


def written_since(take: Path, started: float) -> dict[str, int]:
    """Export files modified since `started`: relative path -> size."""
    files = {}
    for path in take.rglob("*"):
        if (
            path.is_file()
            and path.suffix.lower() not in IGNORED_SUFFIXES
            and not IGNORED_FOLDERS.intersection(path.relative_to(take).parts[:-1])
            and path.stat().st_mtime >= started
        ):
            files[path.relative_to(take).as_posix()] = path.stat().st_size
    return files


def run_mode(take: Path, steps: str, mode: str, report: Path) -> tuple[list[dict], dict[str, int], float]:
    print(f"\n=== {mode}: {steps} on {take}")
    started = time.time()
    subprocess.run(
        [sys.executable, str(MAIN), "--take", str(take), "--steps", steps, "--overwrite",
         "--shogun-mode", mode, "--report", str(report)],
        cwd=MAIN.parent,
        check=False,
    )
    seconds = time.time() - started
    rows = json.loads(report.read_text(encoding="utf-8")) if report.exists() else []
    return rows, written_since(take, started - 2), seconds


def comparison(modes: list[str], results: dict) -> list[dict]:
    """One row per step: status, seconds and Shogun seconds in each mode."""
    operations = list(dict.fromkeys(row["operation"] for mode in modes for row in results[mode][0]))
    table = []
    for operation in operations:
        line = {"step": operation}
        for mode in modes:
            row = next((row for row in results[mode][0] if row["operation"] == operation), {})
            line[f"{mode} status"] = row.get("status", "")
            line[f"{mode} s"] = row.get("seconds", "")
            line[f"{mode} shogun s"] = row.get("shogun_seconds", "")
        table.append(line)
    total = {"step": "TOTAL (whole run)"}
    for mode in modes:
        total[f"{mode} status"] = ""
        total[f"{mode} s"] = round(results[mode][2], 1)
        total[f"{mode} shogun s"] = round(sum(row.get("shogun_seconds", 0) for row in results[mode][0]), 1)
    return [*table, total]


def print_table(table: list[dict]):
    columns = list(table[0])
    widths = [max(len(column), *(len(str(row[column])) for row in table)) for column in columns]
    for values in [columns, *([row[column] for column in columns] for row in table)]:
        print("  ".join(str(value).ljust(width) for value, width in zip(values, widths, strict=True)))


def file_differences(modes: list[str], results: dict) -> list[str]:
    first, second = (results[mode][1] for mode in modes[:2])
    lines = [f"only in {modes[0]}: {name}" for name in sorted(first.keys() - second.keys())]
    lines += [f"only in {modes[1]}: {name}" for name in sorted(second.keys() - first.keys())]
    lines += [
        f"size differs: {name} ({first[name]} vs {second[name]} bytes)"
        for name in sorted(first.keys() & second.keys())
        if first[name] != second[name]
    ]
    return lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--take", type=Path, required=True, help="a copy of a take folder")
    parser.add_argument("--steps", required=True, help="as main.py --steps, e.g. original,actors,props")
    parser.add_argument("--modes", default="old,runscript", help="order of the runs (default: old,runscript)")
    parser.add_argument("--yes", action="store_true", help="do not ask before replacing the take's exports")
    args = parser.parse_args()
    take = args.take.resolve()
    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    if not take.is_dir():
        sys.exit(f"Take folder not found: {take}")
    if not args.yes and input(f"This replaces the exports in {take}. Is it a copy? [y/N] ").lower() != "y":
        sys.exit("Stopped.")

    folder = take / ".vicon_exporter_reports" / f"timing_{datetime.now():%Y%m%d_%H%M%S}"
    folder.mkdir(parents=True)
    results = {mode: run_mode(take, args.steps, mode, folder / f"batch_{mode}.json") for mode in modes}

    table = comparison(modes, results)
    print(f"\nTIMING ({take.name}, steps {args.steps})")
    print_table(table)
    differences = file_differences(modes, results) if len(modes) > 1 else []
    print(f"\n{len(results[modes[-1]][1])} files written by {modes[-1]}.")
    if differences:
        print("Files differ between the modes:")
        for line in differences:
            print(f"  {line}")
    elif len(modes) > 1:
        print(f"{modes[0]} and {modes[1]} wrote the same files with the same sizes.")

    with open(folder / "timing.csv", "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(table[0]))
        writer.writeheader()
        writer.writerows(table)
    (folder / "files.txt").write_text("\n".join(differences) or "same files and sizes", encoding="utf-8")
    print(f"Saved in {folder}")


if __name__ == "__main__":
    main()
