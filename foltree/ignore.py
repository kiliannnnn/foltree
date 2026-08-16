"""Gitignore-style pattern matching.

The previous implementation tested `pattern in path`, which meant `.git` also
matched `.gitignore` and `dist` also matched `distribution`. This module
implements the subset of gitignore semantics that actually matters here:

* blank lines and `#` comments are skipped
* `!pattern` re-includes something an earlier pattern excluded
* a trailing `/` restricts the pattern to directories
* a leading or embedded `/` anchors the pattern to the scan root
* a pattern without any `/` matches a basename at any depth
* `*`, `?`, `[abc]` and `**` behave as in gitignore

Plain names like `.git`, `node_modules` or `dist` keep working exactly as
users expect, they are simply matched as whole path segments now.
"""

from __future__ import annotations

import os
import re
from typing import Iterable, List, Sequence

DEFAULT_IGNORE: Sequence[str] = (
    ".git",
    ".svn",
    ".hg",
    "node_modules",
    "__pycache__",
    ".venv",
    "venv",
    "dist",
    "build",
    ".vscode",
    ".idea",
    ".env",
    ".env.local",
    "vendor",
    ".DS_Store",
    "*.pyc",
)


def _translate(pattern: str) -> str:
    """Translate one gitignore glob into a regex body (no anchors)."""
    out: List[str] = []
    i, n = 0, len(pattern)
    while i < n:
        char = pattern[i]
        i += 1
        if char == "*":
            if i < n and pattern[i] == "*":
                i += 1
                if i < n and pattern[i] == "/":
                    i += 1
                    out.append("(?:.*/)?")  # `**/` spans zero or more directories
                else:
                    out.append(".*")
            else:
                out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = i
            if end < n and pattern[end] == "!":
                end += 1
            if end < n and pattern[end] == "]":
                end += 1
            while end < n and pattern[end] != "]":
                end += 1
            if end >= n:
                out.append(r"\[")
            else:
                body = pattern[i:end].replace("\\", r"\\")
                if body.startswith("!"):
                    body = "^" + body[1:]
                out.append("[" + body + "]")
                i = end + 1
        elif char == "\\":
            if i < n:
                out.append(re.escape(pattern[i]))
                i += 1
            else:
                out.append(re.escape("\\"))
        else:
            out.append(re.escape(char))
    return "".join(out)


class _Rule:
    __slots__ = ("self_re", "descendant_re", "negated", "dir_only", "source")

    def __init__(self, pattern: str):
        self.source = pattern
        self.negated = pattern.startswith("!")
        if self.negated:
            pattern = pattern[1:]

        self.dir_only = pattern.endswith("/")
        if self.dir_only:
            pattern = pattern[:-1]

        # A `/` anywhere but the very end anchors the pattern to the root.
        anchored = "/" in pattern
        pattern = pattern.lstrip("/")

        body = ("" if anchored else "(?:.*/)?") + _translate(pattern)
        self.self_re = re.compile("^" + body + "$")
        # Anything below a matched directory is ignored too, so rules are
        # still correct when a caller checks a deep path directly.
        self.descendant_re = re.compile("^" + body + "/.*$")

    def matches(self, rel_path: str, is_dir: bool) -> bool:
        if self.descendant_re.match(rel_path):
            # Only a directory can have descendants, so `dir_only` is satisfied.
            return True
        if self.dir_only and not is_dir:
            return False
        return self.self_re.match(rel_path) is not None


class IgnoreRules:
    """An ordered set of gitignore-style rules. Later rules win."""

    def __init__(self, patterns: Iterable[str] = ()):
        self.rules: List[_Rule] = []
        self.add_many(patterns)

    def add_many(self, patterns: Iterable[str]) -> "IgnoreRules":
        for raw in patterns:
            self.add(raw)
        return self

    def add(self, raw: str) -> "IgnoreRules":
        line = raw.rstrip("\n").rstrip()
        if not line or line.lstrip().startswith("#"):
            return self
        self.rules.append(_Rule(line.strip()))
        return self

    def match(self, rel_path: str, is_dir: bool = False) -> bool:
        """True when `rel_path` (relative, posix separators) should be ignored."""
        rel_path = rel_path.replace(os.sep, "/").strip("/")
        if not rel_path:
            return False
        ignored = False
        for rule in self.rules:
            if rule.matches(rel_path, is_dir):
                ignored = not rule.negated
        return ignored

    def __bool__(self) -> bool:
        return bool(self.rules)

    def __len__(self) -> int:
        return len(self.rules)

    @classmethod
    def from_text(cls, text: str) -> "IgnoreRules":
        return cls(text.splitlines())


def load_gitignore(root: str) -> List[str]:
    """Read pattern lines from `<root>/.gitignore`, or [] if there is none."""
    path = os.path.join(root, ".gitignore")
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            return handle.read().splitlines()
    except OSError:
        return []
