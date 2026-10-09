"""Command line interface: `foltree scan` and `foltree build`."""

from __future__ import annotations

import argparse
import os
import sys
from typing import List, Optional, Sequence

from . import __version__
from .build import BuildError, build, write_readme
from .ignore import DEFAULT_IGNORE, IgnoreRules
from .parse import ParseError, parse
from .render import FORMATS, format_size, render, resolve_format
from .scanner import ScanError, scan

def _format_arg(value: str) -> str:
    """argparse type: accept aliases such as `md` or `yml`, not only keys."""
    if value.strip().lower() == "auto":
        return "auto"
    try:
        return resolve_format(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc


def _collect_rules(args: argparse.Namespace) -> IgnoreRules:
    patterns: List[str] = []
    if not args.no_default_ignore:
        patterns.extend(DEFAULT_IGNORE)
    patterns.extend(args.ignore or [])
    return IgnoreRules(patterns)


def _write_out(text: str, destination: Optional[str]) -> None:
    if not destination:
        sys.stdout.write(text + "\n")
        return
    with open(destination, "w", encoding="utf-8") as handle:
        handle.write(text + "\n")
    print(f"Wrote {destination}", file=sys.stderr)


def cmd_scan(args: argparse.Namespace) -> int:
    try:
        tree = scan(
            args.path,
            rules=_collect_rules(args),
            max_depth=args.max_depth,
            include_sizes=args.sizes,
            use_gitignore=args.gitignore,
            follow_symlinks=args.follow_symlinks,
        )
    except ScanError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    _write_out(render(tree, args.format, stats=args.sizes), args.output)
    if args.summary:
        print(
            f"{tree.dir_count} directories, {tree.file_count} files"
            + (f", {format_size(tree.total_size)}" if args.sizes else ""),
            file=sys.stderr,
        )
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    if args.input:
        try:
            with open(args.input, "r", encoding="utf-8") as handle:
                text = handle.read()
        except OSError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
    else:
        if sys.stdin.isatty():
            print("error: pass a structure with --input FILE or on stdin", file=sys.stderr)
            return 2
        text = sys.stdin.read()

    try:
        tree = parse(text, args.format)
    except ParseError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    try:
        created = build(
            tree,
            args.output,
            dry_run=args.dry_run,
            overwrite=args.overwrite,
            # Only explicit patterns: the default list is for scanning, and a
            # structure that names `.env` or `build/` means to create them.
            rules=IgnoreRules(args.ignore) if args.ignore else None,
        )
    except BuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        for path in created:
            print(path)
        print(f"{len(created)} entries would be created", file=sys.stderr)
        return 0

    if args.readme:
        readme = write_readme(tree, args.output, args.format if args.format != "auto" else "tree")
        if readme is None:
            print("Kept the existing README.md", file=sys.stderr)

    print(f"Created {len(created)} entries in {os.path.abspath(args.output)}", file=sys.stderr)
    return 0


def cmd_gui(_args: argparse.Namespace) -> int:
    try:
        from .gui import main as gui_main
    except ImportError as exc:
        print(
            f"error: the GUI needs customtkinter and tkinter ({exc}).\n"
            "Install with: pip install -r requirements.txt",
            file=sys.stderr,
        )
        return 1
    gui_main()
    return 0


def _add_ignore_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("-i", "--ignore", action="append", metavar="PATTERN",
                        help="gitignore-style pattern to skip (repeatable)")
    parser.add_argument("--no-default-ignore", action="store_true",
                        help=f"do not apply the built-in list ({', '.join(DEFAULT_IGNORE[:4])}, ...)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="foltree",
        description="Turn folders into text and text back into folders.",
    )
    parser.add_argument("--version", action="version", version=f"foltree {__version__}")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="print a folder's structure as text")
    scan_parser.add_argument("path", nargs="?", default=".", help="folder to scan (default: .)")
    scan_parser.add_argument("-f", "--format", default="tree", type=_format_arg, metavar="FORMAT",
                             help=f"{', '.join(FORMATS)} (default: tree)")
    scan_parser.add_argument("-o", "--output", metavar="FILE", help="write to FILE instead of stdout")
    scan_parser.add_argument("-d", "--max-depth", type=int, metavar="N", help="stop after N levels")
    scan_parser.add_argument("-s", "--sizes", action="store_true", help="include file sizes and counts")
    scan_parser.add_argument("--gitignore", action="store_true", help="also apply the folder's .gitignore")
    scan_parser.add_argument("--follow-symlinks", action="store_true", help="descend into symlinked folders")
    scan_parser.add_argument("--summary", action="store_true", help="print a totals line to stderr")
    _add_ignore_options(scan_parser)
    scan_parser.set_defaults(func=cmd_scan)

    build_parser_ = subparsers.add_parser("build", help="create folders from a text structure")
    build_parser_.add_argument("-i", "--input", metavar="FILE", help="structure file (default: stdin)")
    build_parser_.add_argument("-o", "--output", default="output", metavar="DIR",
                               help="destination folder (default: ./output)")
    build_parser_.add_argument("-f", "--format", default="auto", type=_format_arg, metavar="FORMAT",
                               help="input format (default: auto-detect)")
    build_parser_.add_argument("--dry-run", action="store_true", help="list what would be created")
    build_parser_.add_argument("--overwrite", action="store_true", help="truncate files that already exist")
    build_parser_.add_argument("--readme", action="store_true", help="write a README.md describing the structure")
    build_parser_.add_argument("--ignore", action="append", metavar="PATTERN",
                               help="gitignore-style pattern to skip (repeatable)")
    # Kept so existing scripts do not break; building never applies the
    # default list any more, so there is nothing for it to turn off.
    build_parser_.add_argument("--no-default-ignore", action="store_true", help=argparse.SUPPRESS)
    build_parser_.set_defaults(func=cmd_build)

    gui_parser = subparsers.add_parser("gui", help="launch the desktop app")
    gui_parser.set_defaults(func=cmd_gui)

    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        # Bare `foltree` opens the app -- that is what most people want.
        return cmd_gui(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
