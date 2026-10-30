"""Show which aligned outputs each take has and which need a new export.

    uv run status.py [FOLDER]
"""

import sys
from pathlib import Path

from ui.status_browser import open_status_browser

if __name__ == "__main__":
    open_status_browser(Path(sys.argv[1]) if len(sys.argv) > 1 else None)
