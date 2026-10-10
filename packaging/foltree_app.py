"""Entry point of the standalone app that PyInstaller bundles.

The bundle is the desktop app only: double-clicking it should open a window,
not a console. The CLI stays available through `pip install foltree`.

Set `FOLTREE_SMOKE_TEST=1` to open the main window, draw it once and exit 0.
CI runs every bundle that way, which catches a missing module or theme file
that would otherwise only show up on a customer's machine.
"""

import os
import sys

from foltree import gui


def smoke_test() -> int:
    import tempfile

    # Never touch the real settings of whoever runs the check.
    os.environ["FOLTREE_CONFIG_DIR"] = tempfile.mkdtemp(prefix="foltree-smoke-")
    gui._check_tk()
    gui.ctk.set_default_color_theme("blue")
    app = gui.FoltreeApp()
    app.update()
    app.destroy()
    print("foltree bundle OK")
    return 0


if __name__ == "__main__":
    if os.environ.get("FOLTREE_SMOKE_TEST") == "1":
        sys.exit(smoke_test())
    gui.main()
