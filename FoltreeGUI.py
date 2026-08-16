"""Backwards-compatible entry point.

The app now lives in the `foltree` package. This shim stays so that
`python FoltreeGUI.py` -- and any shortcut pointing at it -- keeps working.
Prefer `./run.sh`, `run.bat`, or `python -m foltree`.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from foltree.gui import main  # noqa: E402

if __name__ == "__main__":
    main()
