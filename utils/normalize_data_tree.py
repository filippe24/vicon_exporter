from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

DATE_DMY_RE = re.compile(r"(?<!\d)(\d{2})-(\d{2})-(\d{4})(?!\d)")
DATE_ISO_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
TAKE_RE = re.compile(
    r"(?<![A-Za-z0-9])take[\s_-]*(\d+)(?![A-Za-z0-9])",
    re.IGNORECASE,
)
MOCAP_RE = re.compile(r"(?<![A-Za-z0-9])mocap(?![A-Za-z0-9])", re.IGNORECASE)
YAML_SUFFIXES = {".yaml", ".yml"}
DEFAULT_SKIP_DIRS = {".git", ".venv", "__pycache__"}


@dataclass(frozen=True)
class RenameOperation:
    kind: str
    source: Path
    target: Path


@dataclass(frozen=True)
class TextRewrite:
    path: Path
    backup_path: Path
    replacements: int


def normalize_name(name: str) -> str:
    """Return a stable, sortable name without changing official S/I identifiers."""

    normalized = reverse_dates(name)
    normalized = TAKE_RE.sub(lambda match: f"{int(match.group(1)):03d}", normalized)
    normalized = MOCAP_RE.sub("", normalized)
    normalized = normalized.replace(" ", "-")
    normalized = re.sub(r"_+", "_", normalized)
    normalized = re.sub(r"-+", "-", normalized)
    normalized = re.sub(r"[-_]*_[-_]*", "_", normalized)
    normalized = re.sub(r"[-_]{2,}", "_", normalized)
    normalized = normalized.strip("-_. ")
    normalized = move_date_to_front(normalized)
    normalized = re.sub(r"_+", "_", normalized)
    normalized = re.sub(r"-+", "-", normalized)
    return normalized.strip("-_. ") or name


def reverse_dates(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))
        try:
            parsed = date(year, month, day)
        except ValueError:
            return match.group(0)
        return parsed.isoformat()

    return DATE_DMY_RE.sub(replace, value)


def move_date_to_front(name: str) -> str:
    match = DATE_ISO_RE.search(name)
    if match is None or match.start() == 0:
        return name

    iso_date = match.group(0)
    without_date = (name[: match.start()] + name[match.end() :]).strip("-_. ")
    without_date = re.sub(r"[-_]+$", "", without_date).strip("-_. ")
    without_date = re.sub(r"^[-_]+", "", without_date).strip("-_. ")
    if not without_date:
        return iso_date
    return f"{iso_date}_{without_date}"


def build_rename_plan(
    root: Path,
    *,
    include_files: bool,
    rename_yaml_files: bool,
) -> list[RenameOperation]:
    operations: list[RenameOperation] = []

    for path in sorted(root.rglob("*"), key=lambda item: len(item.parts)):
        if should_skip(path, root):
            continue

        if path.is_dir():
            normalized = normalize_name(path.name)
            if normalized != path.name:
                operations.append(
                    RenameOperation("directory", path, path.with_name(normalized))
                )
            continue

        if not path.is_file():
            continue

        should_consider_file = include_files or (
            rename_yaml_files and path.suffix.lower() in YAML_SUFFIXES
        )
        if not should_consider_file:
            continue

        normalized = normalize_name(path.name)
        if normalized != path.name:
            operations.append(RenameOperation("file", path, path.with_name(normalized)))

    return operations


def should_skip(path: Path, root: Path) -> bool:
    try:
        relative_parts = path.relative_to(root).parts
    except ValueError:
        return True
    return any(part in DEFAULT_SKIP_DIRS for part in relative_parts)


def final_path_for(path: Path, operations: list[RenameOperation]) -> Path:
    matching_operations = []
    for operation in operations:
        try:
            path.relative_to(operation.source)
        except ValueError:
            continue
        matching_operations.append(operation)

    if not matching_operations:
        return path

    deepest_operation = max(
        matching_operations,
        key=lambda item: len(item.source.parts),
    )
    relative = path.relative_to(deepest_operation.source)
    ancestor_operations = [
        operation
        for operation in operations
        if len(operation.source.parts) < len(deepest_operation.source.parts)
    ]
    return final_path_for(deepest_operation.target, ancestor_operations) / relative


def final_operations(operations: list[RenameOperation]) -> list[RenameOperation]:
    finalized: list[RenameOperation] = []
    for operation in operations:
        finalized.append(
            RenameOperation(
                operation.kind,
                operation.source,
                final_path_for(operation.target, operations),
            )
        )
    return finalized


def find_conflicts(operations: list[RenameOperation]) -> list[str]:
    conflicts: list[str] = []
    finalized = final_operations(operations)
    source_keys = {path_key(operation.source) for operation in finalized}
    immediate_source_keys = {path_key(operation.source) for operation in operations}
    target_groups: dict[str, list[RenameOperation]] = {}

    for operation in finalized:
        target_groups.setdefault(path_key(operation.target), []).append(operation)

    for target_key, group in sorted(target_groups.items()):
        if len(group) > 1:
            conflicts.append(
                "multiple sources target "
                f"{target_key}: {', '.join(str(item.source) for item in group)}"
            )

    for operation in finalized:
        if operation.target.exists() and path_key(operation.target) != path_key(
            operation.source
        ):
            if path_key(operation.target) in source_keys:
                conflicts.append(
                    f"target is also being renamed, refusing possible swap: {operation.target}"
                )
            else:
                conflicts.append(f"target already exists: {operation.target}")

    for operation in operations:
        immediate_target = operation.source.with_name(operation.target.name)
        if path_key(immediate_target) == path_key(operation.source):
            continue
        if (
            immediate_target.exists()
            and path_key(immediate_target) not in immediate_source_keys
        ):
            conflicts.append(f"target sibling already exists: {immediate_target}")

    return conflicts


def path_key(path: Path) -> str:
    return str(path.resolve()).casefold()


def make_replacements(
    root: Path,
    operations: list[RenameOperation],
) -> list[tuple[str, str]]:
    replacements: set[tuple[str, str]] = set()
    finalized = final_operations(operations)

    for operation in finalized:
        replacements.add((operation.source.name, operation.target.name))
        try:
            old_relative = operation.source.relative_to(root)
            new_relative = operation.target.relative_to(root)
        except ValueError:
            continue
        replacements.add((old_relative.as_posix(), new_relative.as_posix()))
        replacements.add((str(old_relative), str(new_relative)))

    return sorted(replacements, key=lambda item: len(item[0]), reverse=True)


def count_yaml_rewrites(
    root: Path,
    replacements: list[tuple[str, str]],
) -> list[TextRewrite]:
    rewrites: list[TextRewrite] = []
    for path in sorted(root.rglob("*")):
        if should_skip(path, root) or path.suffix.lower() not in YAML_SUFFIXES:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        replacement_count = 0
        for old, _new in replacements:
            replacement_count += text.count(old)
        if replacement_count:
            rewrites.append(
                TextRewrite(
                    path=path,
                    backup_path=path.with_suffix(path.suffix + ".before-normalize.bak"),
                    replacements=replacement_count,
                )
            )
    return rewrites


def apply_renames(operations: list[RenameOperation]) -> None:
    applied: list[RenameOperation] = []
    for operation in sorted(operations, key=lambda item: len(item.source.parts)):
        current_source = final_path_for(operation.source, applied)
        current_target = current_source.with_name(operation.target.name)
        current_source.rename(current_target)
        applied.append(
            RenameOperation(operation.kind, operation.source, current_target)
        )


def rewrite_yaml_files(
    root: Path,
    replacements: list[tuple[str, str]],
) -> list[TextRewrite]:
    rewrites: list[TextRewrite] = []
    for path in sorted(root.rglob("*")):
        if should_skip(path, root) or path.suffix.lower() not in YAML_SUFFIXES:
            continue
        try:
            original = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        updated = original
        replacement_count = 0
        for old, new in replacements:
            occurrences = updated.count(old)
            if occurrences:
                updated = updated.replace(old, new)
                replacement_count += occurrences

        if updated == original:
            continue

        backup_path = path.with_suffix(path.suffix + ".before-normalize.bak")
        if backup_path.exists():
            backup_path = path.with_suffix(
                f"{path.suffix}.before-normalize.{uuid.uuid4().hex[:8]}.bak"
            )
        shutil.copy2(path, backup_path)
        path.write_text(updated, encoding="utf-8")
        rewrites.append(
            TextRewrite(
                path=path, backup_path=backup_path, replacements=replacement_count
            )
        )

    return rewrites


def write_reports(
    report_dir: Path,
    root: Path,
    operations: list[RenameOperation],
    conflicts: list[str],
    yaml_rewrites: list[TextRewrite],
) -> None:
    report_dir.mkdir(parents=True, exist_ok=True)
    finalized = final_operations(operations)

    csv_path = report_dir / "normalization_plan.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["kind", "source", "target"],
        )
        writer.writeheader()
        for operation in finalized:
            writer.writerow(
                {
                    "kind": operation.kind,
                    "source": str(operation.source),
                    "target": str(operation.target),
                }
            )

    json_path = report_dir / "normalization_plan.json"
    json_path.write_text(
        json.dumps(
            {
                "root": str(root),
                "renames": [
                    {
                        "kind": operation.kind,
                        "source": str(operation.source),
                        "target": str(operation.target),
                    }
                    for operation in finalized
                ],
                "yaml_rewrites": [
                    {
                        "path": str(rewrite.path),
                        "backup_path": str(rewrite.backup_path),
                        "replacements": rewrite.replacements,
                    }
                    for rewrite in yaml_rewrites
                ],
                "conflicts": conflicts,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    undo_path = report_dir / "undo_normalization.ps1"
    undo_path.write_text(build_undo_script(finalized), encoding="utf-8")


def build_undo_script(operations: list[RenameOperation]) -> str:
    lines = [
        "# Review before running. This only reverts path renames from the plan.",
        "$ErrorActionPreference = 'Stop'",
        "",
    ]
    for operation in sorted(
        operations,
        key=lambda item: len(item.target.parts),
        reverse=True,
    ):
        lines.append(
            "Move-Item -LiteralPath "
            f"'{escape_ps(operation.target)}' "
            f"-Destination '{escape_ps(operation.source)}'"
        )
    lines.append("")
    return "\n".join(lines)


def escape_ps(path: Path) -> str:
    return str(path).replace("'", "''")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Plan or apply conservative folder/file name normalization for Vicon data trees."
        )
    )
    parser.add_argument("root", type=Path, help="Data tree root to normalize.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the planned renames. Without this flag, only reports are written.",
    )
    parser.add_argument(
        "--rewrite-yaml",
        action="store_true",
        help=(
            "Rewrite .yaml/.yml contents by replacing exact old names and relative paths "
            "from the rename plan. Backups are written before changes."
        ),
    )
    parser.add_argument(
        "--include-files",
        action="store_true",
        help="Also normalize non-YAML file names. Use only after reviewing the dry-run plan.",
    )
    parser.add_argument(
        "--skip-yaml-file-renames",
        action="store_true",
        help="Do not rename YAML files whose names contain old take/date patterns.",
    )
    parser.add_argument(
        "--report-dir",
        type=Path,
        default=Path.cwd() / "normalization_reports",
        help="Directory where CSV/JSON/undo reports are written.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    root = args.root.expanduser().resolve()
    report_dir = args.report_dir.expanduser().resolve()

    if not root.exists() or not root.is_dir():
        print(f"Root does not exist or is not a directory: {root}")
        return 2

    operations = build_rename_plan(
        root,
        include_files=args.include_files,
        rename_yaml_files=not args.skip_yaml_file_renames,
    )
    conflicts = find_conflicts(operations)
    replacements = make_replacements(root, operations)
    yaml_rewrites = count_yaml_rewrites(root, replacements) if args.rewrite_yaml else []

    write_reports(report_dir, root, operations, conflicts, yaml_rewrites)

    print(f"Root: {root}")
    print(f"Reports: {report_dir}")
    print(f"Planned renames: {len(operations)}")
    print(f"YAML files with planned content rewrites: {len(yaml_rewrites)}")

    if conflicts:
        print("\nConflicts found. Nothing was applied.")
        for conflict in conflicts:
            print(f" - {conflict}")
        return 1

    if not args.apply:
        print(
            "\nDry run complete. Review normalization_plan.csv before running --apply."
        )
        return 0

    apply_renames(operations)
    applied_yaml_rewrites = []
    if args.rewrite_yaml:
        new_root = final_path_for(root, operations)
        applied_yaml_rewrites = rewrite_yaml_files(new_root, replacements)

    print("\nApplied renames.")
    if args.rewrite_yaml:
        print(f"Rewrote YAML files: {len(applied_yaml_rewrites)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
