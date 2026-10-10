"""Build the standalone desktop app for the platform this runs on.

    pip install pyinstaller -r requirements.txt
    python packaging/build.py

Produces one archive in `dist/`, named after the version and platform:

    Foltree-3.1.0-windows-x64.zip     (Foltree/Foltree.exe inside)
    Foltree-3.1.0-macos-arm64.zip     (Foltree.app inside)
    Foltree-3.1.0-linux-x64.tar.gz    (Foltree/Foltree inside)

The bundle carries its own Python and Tk, so the person who downloads it needs
neither. PyInstaller cannot cross-compile: build each platform on that
platform (the release workflow does all three).
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tarfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from foltree import __version__  # noqa: E402

NAME = "Foltree"
BUNDLE_ID = "io.github.kiliannnnn.foltree"
DIST = os.path.join(ROOT, "dist")
WORK = os.path.join(ROOT, "build", "pyinstaller")


def platform_tag() -> str:
    system = {"win32": "windows", "darwin": "macos"}.get(sys.platform, "linux")
    machine = platform.machine().lower()
    arch = {"amd64": "x64", "x86_64": "x64", "aarch64": "arm64"}.get(machine, machine)
    return f"{system}-{arch}"


def run_pyinstaller() -> None:
    import PyInstaller.__main__

    args = [
        os.path.join(ROOT, "packaging", "foltree_app.py"),
        "--name", NAME,
        "--windowed",            # no console window next to the app
        "--onedir",              # starts faster and trips antivirus less than --onefile
        "--noconfirm",
        "--clean",
        "--distpath", DIST,
        "--workpath", WORK,
        "--specpath", WORK,
        "--paths", ROOT,
        # customtkinter loads its themes and fonts from files next to its code.
        "--collect-data", "customtkinter",
        "--osx-bundle-identifier", BUNDLE_ID,
    ]
    icon = os.path.join(ROOT, "packaging", "icon.ico" if sys.platform == "win32" else "icon.icns")
    if sys.platform != "linux" and os.path.exists(icon):
        args += ["--icon", icon]
    PyInstaller.__main__.run(args)


def archive() -> str:
    base = os.path.join(DIST, f"{NAME}-{__version__}-{platform_tag()}")
    if sys.platform == "darwin":
        # ditto keeps the symlinks and extended attributes an .app depends on;
        # Python's zipfile would flatten them and break the bundle.
        target = base + ".zip"
        subprocess.run(["ditto", "-c", "-k", "--keepParent",
                        os.path.join(DIST, f"{NAME}.app"), target], check=True)
    elif sys.platform == "win32":
        target = shutil.make_archive(base, "zip", DIST, NAME)
    else:
        target = base + ".tar.gz"
        with tarfile.open(target, "w:gz") as tar:
            tar.add(os.path.join(DIST, NAME), arcname=NAME)
    return target


def main() -> int:
    run_pyinstaller()
    print(f"\nBuilt {archive()}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
