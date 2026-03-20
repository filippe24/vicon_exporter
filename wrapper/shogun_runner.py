# wrapper/shogun_runner.py

import subprocess
from pathlib import Path


def run_shogun(mcp_file: Path, hsl_file: Path, out_file: Path, shogun_path: Path):
    
    print(hsl_file)

    cmd = [
        shogun_path,
        "-old",
        str(mcp_file),
        str(hsl_file),
        str(out_file),
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)

    print(result.stdout)
    print(result.stderr)

    if result.returncode != 0:
        raise RuntimeError("Shogun failed")