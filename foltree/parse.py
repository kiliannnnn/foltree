"""Text -> Node, with format auto-detection.

Structures arrive from many places -- this app, the `tree` command, Windows
`tree /F`, `find`, `git ls-files`, and above all chat assistants -- so the
reader is deliberately forgiving:

* only the first fenced code block is read when the text contains one, so a
  whole chat answer can be pasted as-is
* trailing comments (`# entry point`, `// helpers`, `<- docs`) are dropped
* any connector width works: `├──`, `├─`, `|--`, `+---`, `\\---`, and guide
  columns of any width, not just four
* `tree`'s "3 directories, 5 files" footer and folder emoji are ignored
"""

from __future__ import annotations

import json
import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Tuple

from .node import Node
from .render import TRUNCATED_MARK, resolve_format


class ParseError(Exception):
    pass


# Extensionless names that are almost always files, and dot-names that are
# almost always directories. Without these the "does it contain a dot?" guess
# turns LICENSE into a folder and .github into a file.
_KNOWN_FILES = {
    "dockerfile", "makefile", "license", "licence", "readme", "changelog",
    "contributing", "authors", "notice", "procfile", "gemfile", "rakefile",
    "vagrantfile", "jenkinsfile", "cname", "codeowners", "copying", "install",
    "news", "todo", "version", ".gitignore", ".gitattributes", ".gitmodules",
    ".dockerignore", ".editorconfig", ".npmrc", ".nvmrc", ".env", ".babelrc",
    ".eslintrc", ".prettierrc", ".gitkeep", ".keep", "brewfile", "podfile",
    "justfile", "caddyfile", "containerfile", "pipfile", "berksfile",
}
_KNOWN_DIRS = {
    ".git", ".github", ".gitlab", ".vscode", ".idea", ".venv", ".circleci",
    ".husky", ".config", ".cache", "node_modules", "__pycache__", "venv",
    ".devcontainer", ".storybook", ".changeset", ".cargo", ".svn", ".hg",
}

_STATS_SUFFIX = re.compile(
    r"\s*\((?:\d+\s+files?(?:,\s*)?)?(?:[\d.]+\s*(?:B|KB|MB|GB|TB))?\)\s*$"
)
_ERROR_SUFFIX = re.compile(r"\s{2}\[[^\]]*\]\s*$")

# `# note` and `// note` need whitespace on both sides so names such as
# `C#` or `issue#12.md` survive; arrows are never part of a real filename.
_COMMENT = re.compile(r"\s+(?:(?:#|//)(?=\s|$)|<!--|<-+|←|⟵|⇐|-->|→|⟶|⇒).*$")
# A parenthesised note after a run of spaces: `src/    (all source code)`.
_ALIGNED_NOTE = re.compile(r"\s{2,}\(.*\)\s*$")

_FOLDER_EMOJI = ("📁", "📂", "🗂")

_FENCE = re.compile(r"^\s*(```|~~~)")
_NOISE_LINES = re.compile(
    r"^\s*(?:"
    r"\d+\s+director(?:y|ies)(?:,\s*\d+\s+files?)?"  # tree's summary footer
    r"|folder path listing.*|volume serial number.*|no subfolders exist.*"  # tree /F
    r")\s*$",
    re.IGNORECASE,
)

# Characters that may appear in front of a connector to draw guide columns.
_GUIDE_CHARS = " \t │┃║|"
# One connector: a corner/tee followed by a horizontal run, e.g. `├──`, `├─`,
# `|--`, `` `-- ``, `+---`, `\---`, or a bare tee in very compact trees.
_CONNECTOR = re.compile(r"(?:[├└┣┗╠╚┝┕┠┖+\\`|][─━═\-]+|[├└┣┗╠╚])>?[  \t]*")
_DRIVE_ROOT = re.compile(r"^(?:[A-Za-z]:)?[\\/.]*$")
# Windows `tree /F` lists files with guides only, one column deeper than the
# connector their siblings would use.
_GUIDE_WIDTH = 4


def _strip_comment(name: str) -> str:
    return _COMMENT.sub("", name)


def _strip_decorations(name: str) -> str:
    """Drop leading emoji/symbols ("📁 src") and keep a folder hint as `/`."""
    is_folder = any(name.startswith(icon) for icon in _FOLDER_EMOJI)
    index = 0
    while index < len(name):
        char = name[index]
        if char in "️‍ " or unicodedata.category(char) == "So":
            index += 1
            continue
        break
    if index == 0:
        return name
    name = name[index:]
    if is_folder and name and not name.endswith("/"):
        name += "/"
    return name


def _clean_name(name: str, comments: bool = True) -> str:
    name = _ERROR_SUFFIX.sub("", name)
    if comments:  # a quoted YAML name is taken literally
        name = _strip_comment(name)
        name = _ALIGNED_NOTE.sub("", name)
    stripped = _STATS_SUFFIX.sub("", name)
    # Only drop the suffix if it actually looked like stats, never a bare "()".
    if stripped != name and stripped.strip():
        name = stripped
    return _strip_decorations(name.strip()).strip()


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

    # ALL-CAPS names are a strong file convention: LICENSE, AUTHORS, PKG-INFO,
    # CODEOWNERS. Directories are conventionally lowercase.
    letters = [char for char in name if char.isalpha()]
    if letters and all(char.isupper() for char in letters):
        return False

    # Anything left is a bare lowercase word, far more often an empty folder
    # (assets, components) than an extensionless file.
    return True


# --------------------------------------------------------------------------
# Pre-processing
# --------------------------------------------------------------------------

def _unwrap(text: str) -> str:
    """Return the useful part of `text`.

    When the text contains a fenced code block -- the usual shape of a chat
    answer -- only the first block is kept, so the prose around it does not
    turn into folders. Footer lines from `tree` are dropped too.
    """
    lines = text.splitlines()
    fences = [index for index, line in enumerate(lines) if _FENCE.match(line)]
    if fences:
        start = fences[0] + 1
        end = fences[1] if len(fences) > 1 else len(lines)
        lines = lines[start:end]
    return "\n".join(line for line in lines if not _NOISE_LINES.match(line))


def _split_tree_line(line: str) -> Tuple[int, str, bool]:
    """Split a tree line into (column, rest, has_connector).

    The column is where the connector starts. Everything in front of it must
    be guide characters, otherwise the line has no connector at all -- that is
    what keeps names such as `a|--b` or `+page.svelte` intact.
    """
    index = 0
    while index < len(line):
        match = _CONNECTOR.match(line, index)
        if match:
            return index, line[match.end():], True
        if line[index] in _GUIDE_CHARS:
            index += 1
            continue
        break
    return index, line[index:], False


def _has_connector(line: str) -> bool:
    return _split_tree_line(line)[2]


def _path_like(line: str) -> bool:
    body = line.strip()
    if body.startswith("./"):
        body = body[2:]
    body = _strip_comment(body).strip().rstrip("/\\")
    return "/" in body or "\\" in body


# --------------------------------------------------------------------------
# Detection
# --------------------------------------------------------------------------

def detect_format(text: str) -> str:
    stripped = _unwrap(text).strip()
    if not stripped:
        raise ParseError("Nothing to parse.")

    if stripped[0] in "{[":
        return "json"

    lines = [line for line in stripped.splitlines() if line.strip()]
    if any(_has_connector(line) for line in lines):
        return "tree"

    bullets = [line for line in lines if re.match(r"^\s*[-*+]\s", line)]
    flat = all(not line[:1].isspace() for line in lines)
    if flat and not bullets and any(_path_like(line) for line in lines):
        return "paths"

    if any("**" in line or "`" in line for line in lines):
        return "markdown"
    if bullets:
        if any(re.search(r":\s*(\[\])?\s*$", _strip_comment(line)) for line in lines):
            return "yaml"
        return "markdown"
    if re.search(r":\s*$", _strip_comment(lines[0])):
        return "yaml"
    return "indented"


# --------------------------------------------------------------------------
# Per-format line readers -> (depth, name) pairs
# --------------------------------------------------------------------------

def _tree_pairs(lines: Sequence[str]) -> List[Tuple[int, str]]:
    """Read box-drawing trees of any guide width.

    Depth comes from the connector's column, compared against a stack of the
    columns seen so far, so `├──` with four-wide guides, `├─` with three-wide
    guides and the odd misaligned line all nest the way they look.
    """
    pairs: List[Tuple[int, str]] = []
    columns: List[int] = []
    for line in lines:
        column, rest, connected = _split_tree_line(line)
        name = _clean_name(rest)
        if not name:
            continue  # a guide-only spacer line such as "│"
        if not connected:
            if column == 0:
                # A bare line at the left edge is a root header. Windows
                # `tree` prints the drive (`C:.`) there, which is no name.
                if not _DRIVE_ROOT.match(name):
                    pairs.append((0, name))
                columns = []
                continue
            # Windows `tree /F` file line: guides only, one level deeper.
            column = max(0, column - _GUIDE_WIDTH)
        while columns and column < columns[-1]:
            columns.pop()
        if not columns or column > columns[-1]:
            columns.append(column)
        pairs.append((len(columns), name))
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
        column = len(line) - len(line.lstrip(" \t "))
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
    return [
        (depth, _clean_name(_strip_comment(body).strip().strip("*`").strip()))
        for depth, body in pairs
    ]


def _yaml_pairs(lines: Sequence[str]) -> List[Tuple[int, str]]:
    cleaned: List[Tuple[int, str]] = []
    for depth, body in _indent_pairs(lines, _YAML_ITEM):
        if body[:1] in ("'", '"'):
            # A quoted name may legitimately contain `#` or `:`, so only what
            # is inside the quotes counts.
            close = body.find(body[0], 1)
            if close != -1:
                cleaned.append((depth, _clean_name(body[1:close], comments=False)))
                continue
        body = _strip_comment(body)
        body = re.sub(r":\s*(\[\])?\s*$", "", body).strip()
        cleaned.append((depth, _clean_name(body)))
    return cleaned


# --------------------------------------------------------------------------
# Assembly
# --------------------------------------------------------------------------

def _finish(root: Node) -> Node:
    """Settle file/folder types, then unwrap a single top-level folder."""
    for node in root.walk():
        if node is root:
            continue
        node.is_dir = guess_is_dir(node.name + ("/" if node.is_dir else ""), bool(node.children))

    # A single top-level entry is the real root; several means the text held a
    # fragment, so keep the anonymous wrapper for build() to unpack.
    if len(root.children) == 1 and root.children[0].is_dir:
        return root.children[0]
    return root


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

    return _finish(root)


def _build_from_paths(lines: Sequence[str]) -> Node:
    """One path per line, as printed by `find`, `git ls-files` or `paths`."""
    root = Node(name="", is_dir=True)
    index: Dict[Tuple[str, ...], Node] = {(): root}

    for line in lines:
        text = _clean_name(line.strip())
        if "/" not in text:
            text = text.replace("\\", "/")
        if text in (".", "./"):
            continue
        if text.startswith("./"):
            text = text[2:]
        is_dir = text.endswith("/")
        parts = [part for part in text.split("/") if part and part != "."]
        if parts and parts[-1] == TRUNCATED_MARK:
            parts, is_dir = parts[:-1], True
        if not parts:
            continue

        parent, key = root, ()
        for position, part in enumerate(parts):
            key = key + (part,)
            last = position == len(parts) - 1
            node = index.get(key)
            if node is None:
                node = parent.add(Node(name=part, is_dir=is_dir or not last))
                index[key] = node
            elif is_dir or not last:
                node.is_dir = True
            parent = node

    if not root.children:
        raise ParseError("No entries found in the structure.")
    return _finish(root)


def _from_json(text: str) -> Node:
    try:
        data = json.loads(text)
    except ValueError as exc:
        raise ParseError(f"Invalid JSON: {exc}") from exc
    try:
        if isinstance(data, list):
            root = Node(name="", is_dir=True)
            for entry in data:
                root.add(Node.from_dict(entry))
            return root
        if not isinstance(data, dict):
            raise ParseError("JSON must be an object or a list of objects.")
        return Node.from_dict(data)
    except KeyError as exc:
        raise ParseError(f"Missing key in JSON structure: {exc}") from exc
    except (TypeError, AttributeError) as exc:
        raise ParseError("Every JSON entry must be an object with a \"name\".") from exc


def parse(text: str, fmt: str = "auto") -> Node:
    """Parse `text` into a Node tree. `fmt='auto'` detects the format."""
    if not text or not text.strip():
        raise ParseError("Nothing to parse.")

    text = _unwrap(text)
    if not text.strip():
        raise ParseError("Nothing to parse.")

    key = "auto" if (fmt or "auto").strip().lower() == "auto" else resolve_format(fmt)
    if key == "auto":
        key = detect_format(text)

    if key == "json":
        return _from_json(text)

    lines = [line for line in text.splitlines() if line.strip()]
    if key == "paths":
        return _build_from_paths(lines)
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
