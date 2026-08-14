"""Node -> filesystem."""

from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

from .ignore import IgnoreRules
from .node import Node


class BuildError(Exception):
    pass


# Characters Windows rejects in filenames, plus the path separators. Names are
# sanitised rather than rejected so a structure pasted from an LLM still builds.
_UNSAFE = re.compile(r'[<>:"|?*\x00-\x1f]')
_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}


def _safe_name(name: str) -> Optional[str]:
    """Return a filesystem-safe single path component, or None to skip it."""
    name = name.strip().strip("/\\").strip()
    if not name or name in (".", ".."):
        return None
    if re.match(r"^[A-Za-z]:$", name):  # a bare drive letter
        return None
    name = _UNSAFE.sub("_", name).replace("/", "_").replace("\\", "_")
    name = name.rstrip(" .") or None
    if name and name.split(".")[0].lower() in _RESERVED:
        name = "_" + name
    return name


def plan(root: Node, dest: str) -> List[Tuple[str, bool]]:
    """Compute the (path, is_dir) list `build` would create, without touching disk.

    Every path is checked to stay inside `dest`, so a structure containing
    `../../etc` cannot escape the output folder.
    """
    dest = os.path.abspath(os.path.expanduser(dest))
    entries: List[Tuple[str, bool]] = []

    def visit(node: Node, parent: str) -> None:
        for child in node.children:
            name = _safe_name(child.name)
            if name is None:
                continue
            path = os.path.join(parent, name)
            if os.path.commonpath([dest, os.path.abspath(path)]) != dest:
                raise BuildError(f"Refusing to write outside the output folder: {child.name}")
            entries.append((path, child.is_dir))
            if child.is_dir:
                visit(child, path)

    # An unnamed root is the fragment wrapper from parse(); its children belong
    # directly in dest. A named root becomes a folder of its own.
    if root.name:
        wrapper = Node(name="", is_dir=True)
        wrapper.add(root)
        visit(wrapper, dest)
    else:
        visit(root, dest)
    return entries


def build(
    root: Node,
    dest: str,
    dry_run: bool = False,
    overwrite: bool = False,
    rules: Optional[IgnoreRules] = None,
) -> List[str]:
    """Create the structure under `dest` and return the paths created.

    Existing files are left alone unless `overwrite=True`; the old version
    truncated whatever it found, which could silently empty real files when a
    structure was rebuilt into a populated folder.
    """
    dest = os.path.abspath(os.path.expanduser(dest))
    entries = plan(root, dest)

    if rules:
        filtered = []
        for path, is_dir in entries:
            rel = os.path.relpath(path, dest).replace(os.sep, "/")
            if not rules.match(rel, is_dir):
                filtered.append((path, is_dir))
        entries = filtered

    if dry_run:
        return [path for path, _ in entries]

    if not os.path.isdir(dest):
        os.makedirs(dest, exist_ok=True)

    created: List[str] = []
    for path, is_dir in entries:
        try:
            if is_dir:
                os.makedirs(path, exist_ok=True)
            else:
                parent = os.path.dirname(path)
                if parent and not os.path.isdir(parent):
                    os.makedirs(parent, exist_ok=True)
                if os.path.exists(path) and not overwrite:
                    continue
                with open(path, "w", encoding="utf-8"):
                    pass
        except OSError as exc:
            raise BuildError(f"Could not create {path}: {exc}") from exc
        created.append(path)
    return created
