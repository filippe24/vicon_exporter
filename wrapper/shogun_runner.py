# wrapper/shogun_runner.py

import subprocess
from pathlib import Path


def run_shogun(mcp_file: Path, hsl_file: Path, out_file: Path, shogun_path: Path):

    print("   ▶ running Shogun:")
    print(f"     - mcp: {mcp_file}")
    print(f"     - hsl: {hsl_file}")
    print(f"     - out: {out_file}")
    cmd = [
        shogun_path,
        "-old",
        str(mcp_file),
        str(hsl_file),
        str(out_file),
    ]

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        universal_newlines=True,
    )
    # Read stdout live
    print("   ── shogun output:")
    for line in process.stdout:
        print("      " + line.rstrip())

    # Read stderr live
    for line in process.stderr:
        print("      [ERR] " + line.rstrip())

    process.wait()

    if process.returncode != 0:
        raise RuntimeError("❌ shogun failed")

    # result = subprocess.run(cmd, capture_output=True, text=True)
    # print(result.stdout)
    # print(result.stderr)

    # if result.returncode != 0:
    #     raise RuntimeError("Shogun failed")
