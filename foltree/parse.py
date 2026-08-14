"""Text -> Node, with format auto-detection."""

from __future__ import annotations

import json
import re
from typing import List, Optional, Sequence, Tuple

from .node import Node
from .render import TRUNCATED_MARK, resolve_format


class ParseError(Exception):
    pass


_CONNECTORS = ("├── ", "└── ", "|-- ", "`-- ", "├──", "└──")
_GUIDE_UNIT = 4  # every tree prefix segment is exactly four characters wide

# Extensionless names that are almost always files, and dot-names that are
# almost always directories. Without these the "does it contain a dot?" guess
# turns LICENSE into a folder and .github into a file.
_KNOWN_FILES = {
    "dockerfile", "makefile", "license", "licence", "readme", "changelog",
    "contributing", "authors", "notice", "procfile", "gemfile", "rakefile",
    "vagrantfile", "jenkinsfile", "cname", "codeowners", "copying", "install",
    "news", "todo", "version", ".gitignore", ".gitattributes", ".gitmodules",
    ".dockerignore", ".editorconfig", ".npmrc", ".nvmrc", ".env", ".babelrc",
    ".eslintrc", ".prettierrc", ".gitkeep", ".keep",
}
_KNOWN_DIRS = {
    ".git", ".github", ".gitlab", ".vscode", ".idea", ".venv", ".circleci",
    ".husky", ".config", ".cache", "node_modules", "__pycache__", "venv",
}

_STATS_SUFFIX = re.compile(
    r"\s*\((?:\d+\s+files?(?:,\s*)?)?(?:[\d.]+\s*(?:B|KB|MB|GB|TB))?\)\s*$"
)
_ERROR_SUFFIX = re.compile(r"\s{2}\[[^\]]*\]\s*$")


def _clean_name(name: str) -> str:
    name = _ERROR_SUFFIX.sub("", name)
    stripped = _STATS_SUFFIX.sub("", name)
    # Only drop the suffix if it actually looked like stats, never a bare "()".
    if stripped != name and stripped.strip():
        name = stripped
    return name.strip()


def _is_noise(name: str) -> bool:
    return not name or name.strip(" .'\"") == "" or name.strip("'\"") == TRUNCATED_MARK


def guess_is_dir(name: str, has_children: bool) -> bool:
    """Best-effort file/directory classification for a bare name."""
    if name.endswith("/"):
        return True
    if has_children:
        return True

    lowered = name.lower()
    if lowered in _KNOWN_DIRS:
        return True
    if lowered in _KNOWN_FILES:
        return False
    if "." in name[1:]:  # a real extension, e.g. main.py or .env.local
        return False
    if name.startswith("."):
        return False
    return True


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def detect_format(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        raise ParseError("Nothing to parse.")

    if stripped[0] in "{[":
        return "json"

    lines = [line for line in stripped.splitlines() if line.strip()]
    if any(connector in line for line in lines for connector in _CONNECTORS):
        return "tree"
    if any("**" in line or "`" in line for line in lines):
        return "markdown"

    bullets = [line for line in lines if re.match(r"^\s*[-*+]\s", line)]
    if bullets:
        if any(re.search(r":\s*(\[\])?\s*$", line) for line in lines):
            return "yaml"
        return "markdown"
    if re.search(r":\s*$", lines[0]):
        return "yaml"
    return "indented"


# --------------------------------------------------------------------------
# Per-format line readers -> (depth, name) pairs
# --------------------------------------------------------------------------

def _tree_pairs(lines: Sequence[str]) -> List[Tuple[int, str]]:
    pairs: List[Tuple[int, str]] = []
    for line in lines:
        position = -1
        width = 0
        for connector in _CONNECTORS:
            found = line.find(connector)
            if found != -1 and (position == -1 or found < position):
                position, width = found, len(connector)
        if position == -1:
            # A bare line at this point is the root header.
            pairs.append((0, _clean_name(line.strip())))
        else:
            depth = position // _GUIDE_UNIT + 1
            pairs.append((depth, _clean_name(line[position + width:])))
    return pairs


def _indent_pairs(lines: Sequence[str], strip: Optional[re.Pattern] = None) -> List[Tuple[int, str]]:
    """Read (column, body) then convert columns to depths with a stack.

    Using a stack rather than `columns // 4` means any consistent indent width
    works -- 2-space markdown, 4-space text, and the mixed widths the YAML
    dialect produces all parse the same way.

    Bodies are returned with their format markers intact; each caller strips
    those first and only then removes stat suffixes, because a suffix is at
    the end of the *name*, not of the decorated line.
    """
    raw: List[Tuple[int, str]] = []
    for line in lines:
        column = len(line) - len(line.lstrip(" \t"))
        body = line.strip()
        if strip:
            match = strip.match(body)
            if not match:
                continue
            body = match.group(1)
        raw.append((column, body))

    pairs: List[Tuple[int, str]] = []
    columns: List[int] = []
    for column, name in raw:
        while columns and column < columns[-1]:
            columns.pop()
        if not columns or column > columns[-1]:
            columns.append(column)
        pairs.append((len(columns) - 1, name))
    return pairs


_MD_ITEM = re.compile(r"^[-*+]\s+(.*)$")
_YAML_ITEM = re.compile(r"^(?:-\s+)?(.*)$")


def _plain_pairs(lines: Sequence[str]) -> List[Tuple[int, str]]:
    return [(depth, _clean_name(body)) for depth, body in _indent_pairs(lines)]


def _markdown_pairs(lines: Sequence[str]) -> List[Tuple[int, str]]:
    pairs = _indent_pairs(lines, _MD_ITEM)
    return [(depth, _clean_name(body.strip("*`").strip())) for depth, body in pairs]


def _yaml_pairs(lines: Sequence[str]) -> List[Tuple[int, str]]:
    cleaned: List[Tuple[int, str]] = []
    for depth, body in _indent_pairs(lines, _YAML_ITEM):
        body = re.sub(r":\s*(\[\])?\s*$", "", body).strip()
        if len(body) >= 2 and body[0] == body[-1] and body[0] in "'\"":
            body = body[1:-1]
        cleaned.append((depth, _clean_name(body)))
    return cleaned


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def _build_from_pairs(pairs: Sequence[Tuple[int, str]]) -> Node:
    pairs = [(depth, name) for depth, name in pairs if not _is_noise(name)]
    if not pairs:
        raise ParseError("No entries found in the structure.")

    root = Node(name="", is_dir=True)
    stack: List[Node] = [root]
    base = pairs[0][0]

    for depth, name in pairs:
        level = max(0, depth - base) + 1
        while len(stack) > level:
            stack.pop()
        while len(stack) < level:
            # Tolerate a skipped level rather than throwing the structure away.
            filler = Node(name="_", is_dir=True)
            stack[-1].add(filler)
            stack.append(filler)

        node = Node(name=name.rstrip("/"), is_dir=name.endswith("/"))
        stack[-1].add(node)
        stack.append(node)

    for node in root.walk():
        if node is root:
            continue
        node.is_dir = guess_is_dir(node.name + ("/" if node.is_dir else ""), bool(node.children))

    # A single top-level entry is the real root; several means the text held a
    # fragment, so keep the anonymous wrapper for build() to unpack.
    if len(root.children) == 1 and root.children[0].is_dir:
        return root.children[0]
    return root


def parse(text: str, fmt: str = "auto") -> Node:
    """Parse `text` into a Node tree. `fmt='auto'` detects the format."""
    if not text or not text.strip():
        raise ParseError("Nothing to parse.")

    key = "auto" if (fmt or "auto").strip().lower() == "auto" else resolve_format(fmt)
    if key == "auto":
        key = detect_format(text)

    if key == "json":
        try:
            data = json.loads(text)
        except ValueError as exc:
            raise ParseError(f"Invalid JSON: {exc}") from exc
        if isinstance(data, list):
            root = Node(name="", is_dir=True)
            for entry in data:
                root.add(Node.from_dict(entry))
            return root
        if not isinstance(data, dict):
            raise ParseError("JSON must be an object or a list of objects.")
        try:
            return Node.from_dict(data)
        except KeyError as exc:
            raise ParseError(f"Missing key in JSON structure: {exc}") from exc

    lines = [line for line in text.splitlines() if line.strip()]
    if key == "tree" or key == "ascii":
        pairs = _tree_pairs(lines)
    elif key == "markdown":
        pairs = _markdown_pairs(lines)
    elif key == "yaml":
        pairs = _yaml_pairs(lines)
    elif key == "indented":
        pairs = _plain_pairs(lines)
    else:
        raise ParseError(f"Cannot parse format {key!r}.")

    return _build_from_pairs(pairs)
