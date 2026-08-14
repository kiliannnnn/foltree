"""Filesystem -> Node."""

from __future__ import annotations

import os
from typing import Optional

from .ignore import IgnoreRules, load_gitignore
from .node import Node


class ScanError(Exception):
    pass


def scan(
    root: str,
    rules: Optional[IgnoreRules] = None,
    max_depth: Optional[int] = None,
    include_sizes: bool = False,
    use_gitignore: bool = False,
    follow_symlinks: bool = False,
) -> Node:
    """Walk `root` and return the tree.

    `max_depth` counts levels below the root; the root itself is depth 0, so
    `max_depth=1` lists the root's direct children only. Directories cut off
    by the limit are marked `truncated` so renderers can show an ellipsis
    instead of silently pretending the tree ended there.

    Unreadable directories are recorded on the node's `error` field rather
    than aborting the scan -- a single locked folder should not lose you the
    whole structure.
    """
    root = os.path.abspath(os.path.expanduser(root))
    if not os.path.isdir(root):
        raise ScanError(f"Not a directory: {root}")

    rules = rules or IgnoreRules()
    if use_gitignore:
        rules = IgnoreRules(r.source for r in rules.rules)
        rules.add_many(load_gitignore(root))

    name = os.path.basename(root.rstrip(os.sep)) or root
    tree = Node(name=name, is_dir=True)
    seen_dirs = {os.path.realpath(root)}

    def walk(node: Node, path: str, rel: str, depth: int) -> None:
        if max_depth is not None and depth >= max_depth:
            try:
                with os.scandir(path) as entries:
                    node.truncated = any(True for _ in entries)
            except OSError:
                pass
            return

        try:
            entries = list(os.scandir(path))
        except OSError as exc:
            node.error = exc.strerror or str(exc)
            return

        for entry in sorted(entries, key=lambda e: e.name.lower()):
            child_rel = f"{rel}/{entry.name}" if rel else entry.name
            try:
                is_dir = entry.is_dir(follow_symlinks=follow_symlinks)
            except OSError:
                is_dir = False

            if rules.match(child_rel, is_dir):
                continue

            child = Node(name=entry.name, is_dir=is_dir)

            if is_dir:
                real = os.path.realpath(entry.path)
                if follow_symlinks and real in seen_dirs:
                    child.error = "symlink loop"  # don't recurse into ourselves
                    node.add(child)
                    continue
                seen_dirs.add(real)
                node.add(child)
                walk(child, entry.path, child_rel, depth + 1)
            else:
                if include_sizes:
                    try:
                        child.size = entry.stat(follow_symlinks=False).st_size
                    except OSError:
                        child.size = None
                node.add(child)

    walk(tree, root, "", 0)
    # Directories first, then files -- os.scandir order is filesystem-dependent
    # and would otherwise make output non-reproducible across machines.
    tree.sort()
    return tree
