"""Node -> text, in every supported output format."""

from __future__ import annotations

import json
from typing import Callable, Dict, List, Optional

from .node import Node

# Connector glyphs per style: (branch, last-branch, guide, blank)
_UNICODE = ("├── ", "└── ", "│   ", "    ")
_ASCII = ("|-- ", "`-- ", "|   ", "    ")

TRUNCATED_MARK = "..."


def format_size(num_bytes: Optional[int]) -> str:
    """Human readable byte count. 1 KB == 1024 B."""
    if num_bytes is None:
        return ""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} B"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _label(node: Node, stats: bool) -> str:
    """The display name, with a trailing `/` on directories.

    The trailing slash is what makes the text formats round-trip: without it a
    parser cannot tell an empty directory from an extensionless file.
    """
    name = node.name + "/" if node.is_dir else node.name
    if not stats:
        return name

    if node.is_dir:
        files = node.file_count
        if not files:
            return name
        return f"{name} ({files} files, {format_size(node.total_size)})"
    if node.size is None:
        return name
    return f"{name} ({format_size(node.size)})"


def _annotate(node: Node) -> str:
    return f"  [{node.error}]" if node.error else ""


# --------------------------------------------------------------------------
# Plain indentation
# --------------------------------------------------------------------------

def render_indented(root: Node, stats: bool = False, indent: int = 4) -> str:
    lines: List[str] = []
    pad = " " * indent

    def emit(node: Node, depth: int) -> None:
        lines.append(pad * depth + _label(node, stats) + _annotate(node))
        for child in node.children:
            emit(child, depth + 1)
        if node.truncated:
            lines.append(pad * (depth + 1) + TRUNCATED_MARK)

    emit(root, 0)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# Box-drawing trees
# --------------------------------------------------------------------------

def _render_tree(root: Node, glyphs, stats: bool) -> str:
    branch, last_branch, guide, blank = glyphs
    lines = [_label(root, stats) + _annotate(root)]

    def emit(node: Node, prefix: str) -> None:
        entries: List[Optional[Node]] = list(node.children)
        if node.truncated:
            entries.append(None)  # placeholder for the "..." line

        for index, child in enumerate(entries):
            is_last = index == len(entries) - 1
            connector = last_branch if is_last else branch
            if child is None:
                lines.append(prefix + connector + TRUNCATED_MARK)
                continue
            lines.append(prefix + connector + _label(child, stats) + _annotate(child))
            if child.is_dir:
                emit(child, prefix + (blank if is_last else guide))

    emit(root, "")
    return "\n".join(lines)


def render_tree(root: Node, stats: bool = False) -> str:
    return _render_tree(root, _UNICODE, stats)


def render_ascii(root: Node, stats: bool = False) -> str:
    return _render_tree(root, _ASCII, stats)


# --------------------------------------------------------------------------
# Markdown
# --------------------------------------------------------------------------

def render_markdown(root: Node, stats: bool = False) -> str:
    lines: List[str] = []

    def emit(node: Node, depth: int) -> None:
        pad = "  " * depth
        if node.is_dir:
            text = f"**{_label(node, stats)}**"
        else:
            text = f"`{_label(node, stats)}`"
        lines.append(f"{pad}- {text}")
        for child in node.children:
            emit(child, depth + 1)
        if node.truncated:
            lines.append(f"{'  ' * (depth + 1)}- {TRUNCATED_MARK}")

    emit(root, 0)
    return "\n".join(lines)


# --------------------------------------------------------------------------
# JSON / YAML
# --------------------------------------------------------------------------

def render_json(root: Node, stats: bool = False) -> str:
    data = root.to_dict()
    if not stats:
        def strip(entry: dict) -> dict:
            entry.pop("size", None)
            for child in entry.get("children", []):
                strip(child)
            return entry

        strip(data)
    return json.dumps(data, indent=2, ensure_ascii=False)


def render_yaml(root: Node, stats: bool = False) -> str:
    """A deliberately small YAML dialect that stays readable in a README.

    Directories become mapping keys ending in `/:`, files become plain scalars.
    `parse.py` reads this dialect back; it is valid YAML for any parser too.
    """
    lines: List[str] = []

    def emit_children(node: Node, indent: int) -> None:
        pad = " " * indent
        for child in node.children:
            if child.is_dir:
                if child.children or child.truncated:
                    lines.append(f"{pad}- {_yaml_key(child, stats)}:")
                    emit_children(child, indent + 4)
                else:
                    lines.append(f"{pad}- {_yaml_key(child, stats)}: []")
            else:
                lines.append(f"{pad}- {_yaml_scalar(child, stats)}")
        if node.truncated:
            lines.append(f"{pad}- '{TRUNCATED_MARK}'")

    if root.children or root.truncated:
        lines.append(f"{_yaml_key(root, stats)}:")
        emit_children(root, 2)
    else:
        lines.append(f"{_yaml_key(root, stats)}: []")
    return "\n".join(lines)


def _needs_quotes(text: str) -> bool:
    return any(ch in text for ch in ":#{}[]&*!|>'\"%@`,") or text != text.strip()


def _yaml_key(node: Node, stats: bool) -> str:
    label = _label(node, stats)
    return f"'{label}'" if _needs_quotes(label) else label


def _yaml_scalar(node: Node, stats: bool) -> str:
    label = _label(node, stats)
    return f"'{label}'" if _needs_quotes(label) else label


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

FORMATS: Dict[str, Callable[..., str]] = {
    "indented": render_indented,
    "tree": render_tree,
    "ascii": render_ascii,
    "markdown": render_markdown,
    "json": render_json,
    "yaml": render_yaml,
}

# Human-facing labels used by the GUI, in menu order.
FORMAT_LABELS = {
    "Indented": "indented",
    "Tree": "tree",
    "ASCII Tree": "ascii",
    "Markdown": "markdown",
    "JSON": "json",
    "YAML": "yaml",
}

# Names accepted from older versions / the CLI, mapped onto current formats.
ALIASES = {
    "clean tree": "tree",
    "clean": "tree",
    "cleantree": "tree",
    "md": "markdown",
    "yml": "yaml",
    "txt": "indented",
}


def resolve_format(name: str) -> str:
    """Map a user-supplied format name onto a key in FORMATS."""
    key = (name or "").strip().lower()
    if key in FORMATS:
        return key
    if key in ALIASES:
        return ALIASES[key]
    if name in FORMAT_LABELS:
        return FORMAT_LABELS[name]
    for label, fmt in FORMAT_LABELS.items():
        if label.lower() == key:
            return fmt
    raise ValueError(
        f"Unknown format {name!r}. Choose one of: {', '.join(sorted(FORMATS))}"
    )


def render(root: Node, fmt: str = "tree", stats: bool = False) -> str:
    return FORMATS[resolve_format(fmt)](root, stats=stats)
