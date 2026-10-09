"""Preferences the desktop app remembers between launches.

Stored as a small JSON file in the platform's usual config folder. Every read
and write is best-effort: a missing, unreadable or hand-mangled file falls
back to the defaults instead of stopping the app from opening.

Set `FOLTREE_CONFIG_DIR` to use another folder (the tests do this so they
never touch the real settings).
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from typing import Any, Dict

from .ignore import DEFAULT_IGNORE

DEFAULTS: Dict[str, Any] = {
    "format": "Tree",
    "depth": "All",
    "sizes": False,
    "gitignore": False,
    "symlinks": False,
    "ignore_patterns": "\n".join(DEFAULT_IGNORE) + "\n",
    "appearance": "System",
    "geometry": "1040x700",
    "last_folder": "",
    "last_destination": "",
    "open_after_build": True,
    "write_readme": False,
}


def config_dir() -> str:
    override = os.environ.get("FOLTREE_CONFIG_DIR")
    if override:
        return override
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
    elif sys.platform == "darwin":
        base = os.path.expanduser("~/Library/Application Support")
    else:
        base = os.environ.get("XDG_CONFIG_HOME") or os.path.expanduser("~/.config")
    return os.path.join(base, "foltree")


def settings_path() -> str:
    return os.path.join(config_dir(), "settings.json")


def load() -> Dict[str, Any]:
    """Defaults overlaid with whatever valid values the file holds."""
    settings = dict(DEFAULTS)
    try:
        with open(settings_path(), "r", encoding="utf-8") as handle:
            stored = json.load(handle)
    except (OSError, ValueError):
        return settings
    if not isinstance(stored, dict):
        return settings
    for key, default in DEFAULTS.items():
        value = stored.get(key)
        # A value of the wrong type (an edited file, an older version) is
        # ignored rather than allowed to crash a widget later on.
        if value is not None and isinstance(value, type(default)):
            settings[key] = value
    return settings


def save(settings: Dict[str, Any]) -> None:
    """Write atomically, so a crash mid-write cannot leave a corrupt file."""
    data = {key: settings.get(key, default) for key, default in DEFAULTS.items()}
    folder = config_dir()
    try:
        os.makedirs(folder, exist_ok=True)
        handle, temp = tempfile.mkstemp(dir=folder, prefix=".settings-", suffix=".json")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
        os.replace(temp, settings_path())
    except OSError:
        pass  # remembering preferences is a convenience, never a failure
