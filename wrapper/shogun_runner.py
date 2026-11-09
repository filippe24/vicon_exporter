import subprocess
import time
from pathlib import Path
from tempfile import TemporaryDirectory

from configuration import settings


class ShogunError(RuntimeError):
    def __init__(self, message: str, returncode: int, output: str):
        errors = [line.strip() for line in output.splitlines() if "ERROR:" in line]
        super().__init__(f"{message}: {errors[0]}" if errors else message)
        self.returncode = returncode
        self.output = output


def resolve_shogun_path(shogun_path: Path) -> Path:
    """Return an existing ShogunPostCL executable path."""

    requested_path = Path(shogun_path).expanduser()
    if requested_path.exists():
        return requested_path

    discovered_paths = _discover_shogun_post_cl_paths()
    if discovered_paths:
        resolved_path = discovered_paths[0]
        print(f"   warning: configured Shogun path not found: {requested_path}")
        print(f"   using discovered Shogun: {resolved_path}")
        return resolved_path

    searched = "\n".join(f"     - {path}" for path in [requested_path])
    raise FileNotFoundError(
        "ShogunPostCL.exe was not found. Update SHOGUN_PATH in "
        "configuration/settings.py or install Vicon Shogun Post.\n"
        f"   searched:\n{searched}"
    )


def run_shogun(mcp_file: Path, hsl_file: Path, shogun_path: Path, mode: str | None = None):
    """Run the HSL script on the take MCP and print how long Shogun took.

    "runscript": a copy of the script that first loads the take runs with -runScript; nothing else is written.
    "old": -old mode also writes a full copy of the take, which takes about as long as loading it. That copy
    goes to a temporary folder beside the script and is deleted. Kept to compare timings.
    Without `mode`, SHOGUN_MODE from the settings (main.py --shogun-mode overrides it)."""
    mode = mode or settings.SHOGUN_MODE
    if mode == "runscript":
        script = hsl_file.with_suffix(".runscript.hsl")
        script.write_text(f'loadFile "{mcp_file.as_posix()}";\n' + hsl_file.read_text())
        _run(["-runScript", str(script)], hsl_file, shogun_path)
    elif mode == "old":
        with TemporaryDirectory(prefix="shogun_output_", dir=hsl_file.parent) as scratch:
            discarded = Path(scratch) / "discarded.mcp"
            _run(["-old", str(mcp_file), str(hsl_file), str(discarded)], hsl_file, shogun_path)
    else:
        raise ValueError(f"Unknown Shogun mode {mode!r}: use 'runscript' or 'old'")


def _run(arguments: list[str], hsl_file: Path, shogun_path: Path):
    cmd = [str(resolve_shogun_path(shogun_path)), *arguments]
    print(f"   running Shogun: {subprocess.list2cmdline(cmd)}")

    started = time.perf_counter()
    process = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )
    # -runScript waits for "exit" once the script is done; a failing script exits by itself.
    try:
        process.stdin.write("exit\n")
        process.stdin.close()
    except OSError:
        pass

    output_lines: list[str] = []
    counts: dict[str, int] = {}
    print("   shogun output:")
    for line in process.stdout:
        clean_line = line.rstrip()
        output_lines.append(clean_line)
        counts[clean_line] = counts.get(clean_line, 0) + 1
        if counts[clean_line] == 1:
            print("      " + clean_line)
    process.wait()
    timing = f"shogun time: {time.perf_counter() - started:.1f} s"

    log_path = hsl_file.with_suffix(".shogun.log")
    output_lines.append(timing)
    log_path.write_text("\n".join(output_lines), encoding="utf-8")
    repeats = sum(count - 1 for count in counts.values())
    if repeats:
        print(f"   condensed {repeats} repeated log lines")
    print(f"   full Shogun log: {log_path}")
    print(f"   {timing}")

    if process.returncode != 0:
        raise ShogunError(
            "shogun failed",
            returncode=process.returncode,
            output="\n".join(output_lines),
        )


def _discover_shogun_post_cl_paths() -> list[Path]:
    vicon_root = Path(r"C:\Program Files\Vicon")
    if not vicon_root.exists():
        return []

    candidates = [
        path / "ShogunPostCL.exe"
        for path in vicon_root.glob("ShogunPost*")
        if path.is_dir()
    ]
    existing_candidates = [path for path in candidates if path.exists()]
    return sorted(existing_candidates, key=_version_sort_key, reverse=True)


def _version_sort_key(path: Path) -> tuple[int, ...]:
    version_text = path.parent.name.replace("ShogunPost", "")
    parts: list[int] = []
    for part in version_text.split("."):
        if part.isdigit():
            parts.append(int(part))
    return tuple(parts)
