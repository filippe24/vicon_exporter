import subprocess
from pathlib import Path


class ShogunError(RuntimeError):
    def __init__(self, message: str, returncode: int, output: str):
        super().__init__(message)
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


def run_shogun(mcp_file: Path, hsl_file: Path, out_file: Path, shogun_path: Path):
    resolved_shogun_path = resolve_shogun_path(shogun_path)

    print("   running Shogun:")
    print(f"     - exe: {resolved_shogun_path}")
    print(f"     - mcp: {mcp_file}")
    print(f"     - hsl: {hsl_file}")
    print(f"     - out: {out_file}")

    cmd = [
        str(resolved_shogun_path),
        "-old",
        str(mcp_file),
        str(hsl_file),
        str(out_file),
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )

    output_lines: list[str] = []

    print("   shogun output:")
    if process.stdout is not None:
        for line in process.stdout:
            clean_line = line.rstrip()
            output_lines.append(clean_line)
            print("      " + clean_line)

    process.wait()

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
