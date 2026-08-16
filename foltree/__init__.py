"""Foltree - bidirectional conversion between folder structures and text.

The package is organised around a single intermediate representation, `Node`:

    filesystem --scan()--> Node --render()--> text
    text --parse()--> Node --build()--> filesystem

Keeping both directions on the same tree model is what makes round-tripping
reliable; the previous version parsed and rendered text directly, which is
where most of the format bugs came from.
"""

from .node import Node
from .ignore import IgnoreRules, load_gitignore, DEFAULT_IGNORE
from .scanner import scan, ScanError
from .render import render, FORMATS, format_size
from .parse import parse, detect_format, guess_is_dir, BARE_NAMES, ParseError
from .build import build, BuildError, plan

__version__ = "3.0.0"

__all__ = [
    "Node",
    "IgnoreRules",
    "load_gitignore",
    "DEFAULT_IGNORE",
    "scan",
    "ScanError",
    "render",
    "FORMATS",
    "format_size",
    "parse",
    "detect_format",
    "guess_is_dir",
    "BARE_NAMES",
    "ParseError",
    "build",
    "BuildError",
    "plan",
    "__version__",
]
