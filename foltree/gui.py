"""The Foltree desktop app.

Layout notes, since the old window had a few structural problems:

* the text area used `wrap='word'`, which folded long tree lines and made the
  guides unreadable -- it is `wrap='none'` with a horizontal scrollbar now
* a second CTkScrollbar was packed next to a CTkTextbox that already has its
  own, so the window showed two
* scanning ran on the UI thread, freezing the app on any large folder; it runs
  on a worker thread and reports back through a queue
* the grid had weights on rows that could not grow, so resizing did nothing
  useful; only the text area stretches now

And the friction fixes that came after:

* the editor starts empty with a hint drawn *over* it, instead of example
  text you had to delete before pasting (and could accidentally build)
* scan options apply immediately while the editor still shows the scan
* the status bar says how the editor's text is understood as you type
* "Create Folders" opens one dialog: destination, a preview showing which
  names became folders, and the README/open-when-done choices
* shortcuts no longer leak into the editor (Tk's Text widget turned Ctrl+O
  and Ctrl+Enter into newlines), Ctrl+A selects all, macOS uses Cmd
* settings, the last folder and the last destination are remembered
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import traceback
from typing import Any, Callable, Dict, Optional

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox

try:  # optional, the app works fine without it
    from CTkToolTip import CTkToolTip
except ImportError:  # pragma: no cover - depends on the environment
    CTkToolTip = None

from . import __version__, settings as prefs
from .build import BuildError, build, plan, write_readme
from .ignore import DEFAULT_IGNORE, IgnoreRules
from .node import Node
from .parse import ParseError, detect_format, parse
from .render import FORMAT_LABELS, format_size, render
from .scanner import ScanError, scan

APP_NAME = "Foltree"
DEPTH_CHOICES = ["All", "1", "2", "3", "4", "5", "6", "8", "10"]
FORMAT_NAMES = {key: label for label, key in FORMAT_LABELS.items()}

IS_MAC = sys.platform == "darwin"
#: Tk modifier for app shortcuts: Cmd on macOS, Ctrl everywhere else.
MOD = "Command" if IS_MAC else "Control"

#: Monospace families to try, best first. Box-drawing guides only line up in a
#: fixed-width font, and "Courier New" does not exist on most Linux systems.
MONO_FAMILIES = (
    "Cascadia Mono", "Consolas", "SF Mono", "Menlo", "JetBrains Mono",
    "DejaVu Sans Mono", "Liberation Mono", "Ubuntu Mono", "Courier New", "Courier",
)

#: Explicit colours for outline buttons. The default CTkButton text colour is
#: light in both appearance modes because buttons normally have a blue fill;
#: on a transparent fill that made them unreadable in light mode.
SECONDARY = dict(
    fg_color="transparent",
    border_width=1,
    text_color=("gray20", "gray90"),
    border_color=("gray65", "gray40"),
    hover_color=("gray88", "gray28"),
)
MUTED = ("gray45", "gray60")

PLACEHOLDER = (
    "Paste a folder structure here, then press Create Folders.\n"
    "It can come from a README, the `tree` command, a list of paths,\n"
    "or a whole chat answer -- comments and prose are ignored.\n"
    "\n"
    "Or press Select Folder to turn a folder on disk into text.\n"
    "\n"
    "example/\n"
    "├── src/\n"
    "│   └── main.py       # comments like this are fine\n"
    "├── assets/\n"
    "└── README.md\n"
)


def _key(combo: str) -> str:
    """Shortcut label for tooltips: `Ctrl+O` here, `⌘O` on a Mac."""
    if IS_MAC:
        return "⌘" + combo.replace("Shift+", "⇧").replace("Enter", "↩")
    return "Ctrl+" + combo


def _tooltip(widget, message: str) -> None:
    if CTkToolTip is not None:
        CTkToolTip(widget, message=message, alpha=0.92, delay=0.4)


def _mono_font(size: int = 13) -> ctk.CTkFont:
    """Pick the first monospace family the system actually has."""
    from tkinter import font as tkfont

    try:
        available = set(tkfont.families())
    except Exception:  # pragma: no cover - no display
        available = set()
    for family in MONO_FAMILIES:
        if family in available:
            return ctk.CTkFont(family=family, size=size)
    return ctk.CTkFont(family="TkFixedFont", size=size)


def _display_path(path: str) -> str:
    """Shorten the home folder to `~` for status messages."""
    home = os.path.expanduser("~")
    if path == home or path.startswith(home + os.sep):
        return "~" + path[len(home):]
    return path


def _counts(tree: Node) -> str:
    folders, files = tree.dir_count, tree.file_count
    return (f"{folders} folder{'' if folders == 1 else 's'}, "
            f"{files} file{'' if files == 1 else 's'}")


def reveal(path: str) -> None:
    """Open `path` in the system file manager.

    Uses a subprocess argument list rather than a shell string so paths
    containing spaces or quotes cannot break the command.
    """
    try:
        if sys.platform == "win32":
            os.startfile(path)  # type: ignore[attr-defined]
        elif IS_MAC:
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass  # opening a file manager is a nicety, never a failure


class BuildDialog(ctk.CTkToplevel):
    """Ask where to create a structure, showing exactly what will be made.

    The preview is the parsed tree, not the editor text: names come back with
    a trailing `/` when they will become folders, which is the one thing a
    guess about `bin` or `LICENSE` can get wrong.
    """

    def __init__(self, master, tree: Node, destination: str,
                 write_readme: bool = False, open_after: bool = True) -> None:
        super().__init__(master)
        self.title("Create folders")
        self.transient(master)
        self.geometry("580x560")
        self.minsize(480, 440)
        self.result: Optional[Dict[str, Any]] = None
        self._tree = tree

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(3, weight=1)

        # Counted from the tree rather than the destination, which may not be
        # valid yet; a named root is created too, so it counts as a folder.
        folders = tree.dir_count + (1 if tree.name else 0)
        files = tree.file_count
        ctk.CTkLabel(
            self, text=(f"Create {folders} folder{'' if folders == 1 else 's'} and "
                        f"{files} file{'' if files == 1 else 's'}"),
            font=getattr(master, "title_font", None) or ctk.CTkFont(size=16, weight="bold"),
        ).grid(row=0, column=0, padx=18, pady=(16, 8), sticky="w")

        row = ctk.CTkFrame(self, fg_color="transparent")
        row.grid(row=1, column=0, padx=18, sticky="ew")
        row.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(row, text="In").grid(row=0, column=0, padx=(0, 8))
        self.dest_var = ctk.StringVar(value=destination)
        self.dest_entry = ctk.CTkEntry(row, textvariable=self.dest_var)
        self.dest_entry.grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(row, text="Browse…", width=90, command=self._browse,
                      **SECONDARY).grid(row=0, column=2, padx=(8, 0))

        self.note_var = ctk.StringVar()
        ctk.CTkLabel(self, textvariable=self.note_var, justify="left", anchor="w",
                     text_color=MUTED, wraplength=530).grid(
            row=2, column=0, padx=18, pady=(8, 6), sticky="ew")

        preview = ctk.CTkTextbox(self, wrap="none", font=getattr(master, "mono_small_font", None)
                                 or _mono_font(12))
        preview.grid(row=3, column=0, padx=18, sticky="nsew")
        preview.insert("1.0", render(tree, "tree"))
        preview.configure(state="disabled")

        options = ctk.CTkFrame(self, fg_color="transparent")
        options.grid(row=4, column=0, padx=18, pady=(10, 0), sticky="ew")
        self.readme_var = ctk.BooleanVar(value=write_readme)
        ctk.CTkCheckBox(options, text="Also write a README.md showing the structure",
                        variable=self.readme_var).grid(row=0, column=0, pady=3, sticky="w")
        self.open_var = ctk.BooleanVar(value=open_after)
        ctk.CTkCheckBox(options, text="Open the folder when done",
                        variable=self.open_var).grid(row=1, column=0, pady=3, sticky="w")

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.grid(row=5, column=0, padx=18, pady=16, sticky="e")
        ctk.CTkButton(buttons, text="Cancel", width=100, command=self._cancel,
                      **SECONDARY).grid(row=0, column=0, padx=(0, 8))
        self.create_button = ctk.CTkButton(buttons, text="Create", width=120, command=self._confirm)
        self.create_button.grid(row=0, column=1)

        self.dest_var.trace_add("write", lambda *_: self._refresh())
        self.bind("<Return>", lambda _e: self._confirm())
        self.bind("<KP_Enter>", lambda _e: self._confirm())
        self.bind("<Escape>", lambda _e: self._cancel())
        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self._refresh()

    def _browse(self) -> None:
        current = os.path.expanduser(self.dest_var.get().strip())
        chosen = filedialog.askdirectory(
            parent=self, title="Where should the structure be created?",
            initialdir=current if os.path.isdir(current) else os.path.expanduser("~"),
        )
        if chosen:
            self.dest_var.set(chosen)

    def _destination(self) -> str:
        return os.path.abspath(os.path.expanduser(self.dest_var.get().strip()))

    def _refresh(self) -> bool:
        """Describe what the current destination means. False if unusable."""
        if not self.dest_var.get().strip():
            self.note_var.set("Choose a folder to create the structure in.")
            self.create_button.configure(state="disabled")
            return False

        dest = self._destination()
        try:
            entries = plan(self._tree, dest)
        except BuildError as exc:
            self.note_var.set(str(exc))
            self.create_button.configure(state="disabled")
            return False

        notes = []
        if self._tree.name:
            top = entries[0][0] if entries else dest
            if os.path.isdir(top):
                notes.append(f"“{os.path.basename(top)}” already exists there; "
                             "missing folders and files are added to it.")
            else:
                notes.append(f"A new folder “{os.path.basename(top)}” is created inside it.")
        else:
            notes.append("There is no single top folder, so the entries go straight into this folder.")
        if not os.path.isdir(dest):
            notes.append("The destination does not exist yet and will be created.")
        existing = sum(1 for path, is_dir in entries if not is_dir and os.path.exists(path))
        if existing:
            notes.append(f"{existing} file{'' if existing == 1 else 's'} already exist"
                         f"{'s' if existing == 1 else ''} and will be left untouched.")
        self.note_var.set(" ".join(notes))
        self.create_button.configure(state="normal")
        return True

    def _confirm(self) -> None:
        if not self._refresh():
            return
        self.result = {
            "destination": self._destination(),
            "readme": self.readme_var.get(),
            "open": self.open_var.get(),
        }
        self.destroy()

    def _cancel(self) -> None:
        self.result = None
        self.destroy()

    def _center_on(self, parent) -> None:
        try:
            self.update_idletasks()
            x = parent.winfo_rootx() + (parent.winfo_width() - self.winfo_width()) // 2
            y = parent.winfo_rooty() + (parent.winfo_height() - self.winfo_height()) // 3
            self.geometry(f"+{max(0, x)}+{max(0, y)}")
        except tk.TclError:
            pass

    def ask(self) -> Optional[Dict[str, Any]]:
        """Show modally and return the choices, or None when cancelled."""
        self._center_on(self.master)
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:
            pass  # some window managers refuse a grab; the dialog still works
        self.dest_entry.focus_set()
        self.wait_window()
        return self.result


class FoltreeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.settings: Dict[str, Any] = prefs.load()
        ctk.set_appearance_mode(self.settings["appearance"])

        # Created once and shared, dialogs included: every font made per
        # dialog would be garbage later, and its `__del__` calls into Tcl.
        self.mono_font = _mono_font(13)
        self.mono_small_font = _mono_font(12)
        self.title_font = ctk.CTkFont(size=16, weight="bold")

        self.title(APP_NAME)
        geometry = str(self.settings["geometry"])
        self.geometry(geometry if _valid_size(geometry) else prefs.DEFAULTS["geometry"])
        self.minsize(860, 560)

        self.tree: Optional[Node] = None
        self.source_folder: Optional[str] = None
        self._results: "queue.Queue[tuple]" = queue.Queue()
        self._busy = False
        self._rescan_pending = False
        self._last_rendered = ""
        self._jobs: Dict[str, str] = {}

        self._build_layout()
        self._bind_shortcuts()
        self._watch_options()
        self._restore_last_folder()
        self._drain_job: Optional[str] = self.after(100, self._drain_results)
        # Some window managers (notably macOS) paint nothing until the first
        # idle pass; force one and raise the window so it is not left blank.
        self.update_idletasks()
        self.lift()
        self.text_box.focus_set()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self._build_toolbar()
        self._build_sidebar()
        self._build_editor()
        self._build_statusbar()

    def _build_toolbar(self) -> None:
        bar = ctk.CTkFrame(self, corner_radius=0)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(4, weight=1)

        select = ctk.CTkButton(bar, text="Select Folder…", width=130, command=self.select_folder)
        select.grid(row=0, column=0, padx=(12, 6), pady=10)
        _tooltip(select, f"Scan a folder and show its structure  ({_key('O')})")

        self.rescan_button = ctk.CTkButton(
            bar, text="Rescan", width=90, command=self.rescan, state="disabled", **SECONDARY
        )
        self.rescan_button.grid(row=0, column=1, padx=6, pady=10)
        _tooltip(self.rescan_button, f"Scan the same folder again  (F5 or {_key('R')})")

        ctk.CTkLabel(bar, text="Format").grid(row=0, column=2, padx=(18, 6))
        label = self.settings["format"]
        self.format_var = ctk.StringVar(value=label if label in FORMAT_LABELS else "Tree")
        format_menu = ctk.CTkOptionMenu(
            bar, variable=self.format_var, values=list(FORMAT_LABELS), width=140,
        )
        format_menu.grid(row=0, column=3, sticky="w")
        # trace('w', ...) is the deprecated Tk 8.5 spelling.
        self.format_var.trace_add("write", self._on_format_change)
        _tooltip(format_menu, "Switching format converts whatever is in the editor,\nso your edits are kept.")

        mode = self.settings["appearance"]
        self.appearance_var = ctk.StringVar(value=mode if mode in ("System", "Light", "Dark") else "System")
        appearance = ctk.CTkOptionMenu(
            bar, variable=self.appearance_var, values=["System", "Light", "Dark"],
            width=100, command=self._set_appearance,
        )
        appearance.grid(row=0, column=5, padx=12, pady=10, sticky="e")

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, corner_radius=0, width=250)
        side.grid(row=1, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_columnconfigure(0, weight=1)
        side.grid_rowconfigure(9, weight=1)

        ctk.CTkLabel(side, text="Scan options", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=14, pady=(14, 8), sticky="w")

        ctk.CTkLabel(side, text="Max depth").grid(row=1, column=0, padx=(14, 6), pady=6, sticky="w")
        depth = self.settings["depth"]
        self.depth_var = ctk.StringVar(value=depth if depth in DEPTH_CHOICES else "All")
        depth_menu = ctk.CTkOptionMenu(side, variable=self.depth_var, values=DEPTH_CHOICES, width=90)
        depth_menu.grid(row=1, column=1, padx=(0, 14), pady=6, sticky="e")
        _tooltip(depth_menu, "How many levels below the folder to show.\nDeeper levels are marked with '...'")

        self.sizes_var = ctk.BooleanVar(value=self.settings["sizes"])
        sizes = ctk.CTkSwitch(side, text="Show sizes & counts", variable=self.sizes_var)
        sizes.grid(row=2, column=0, columnspan=2, padx=14, pady=6, sticky="w")
        _tooltip(sizes, "Append file sizes, and per-folder file counts and totals.")

        self.gitignore_var = ctk.BooleanVar(value=self.settings["gitignore"])
        gitignore = ctk.CTkSwitch(side, text="Respect .gitignore", variable=self.gitignore_var)
        gitignore.grid(row=3, column=0, columnspan=2, padx=14, pady=6, sticky="w")
        _tooltip(gitignore, "Also apply the scanned folder's own .gitignore rules,\non top of the patterns below.")

        self.symlink_var = ctk.BooleanVar(value=self.settings["symlinks"])
        symlinks = ctk.CTkSwitch(side, text="Follow symlinks", variable=self.symlink_var)
        symlinks.grid(row=4, column=0, columnspan=2, padx=14, pady=6, sticky="w")
        _tooltip(symlinks, "Descend into symlinked folders. Loops are detected and stopped.")

        ctk.CTkLabel(side, text="Ignore patterns", font=ctk.CTkFont(weight="bold")).grid(
            row=5, column=0, columnspan=2, padx=14, pady=(16, 4), sticky="w")
        ctk.CTkLabel(side, text="One per line, gitignore syntax", text_color=MUTED,
                     font=ctk.CTkFont(size=11)).grid(row=6, column=0, columnspan=2, padx=14, sticky="w")

        self.ignore_box = ctk.CTkTextbox(side, height=220, wrap="none", undo=True)
        self.ignore_box.grid(row=7, column=0, columnspan=2, padx=14, pady=(6, 6), sticky="ew")
        self.ignore_box.insert("1.0", self.settings["ignore_patterns"])
        self.ignore_box.edit_reset()
        self.ignore_box.edit_modified(False)

        reset = ctk.CTkButton(side, text="Reset patterns", height=28,
                              command=self._reset_patterns, **SECONDARY)
        reset.grid(row=8, column=0, columnspan=2, padx=14, pady=(0, 12), sticky="ew")

        ctk.CTkLabel(side, text=f"Changes apply as you make them.\n{APP_NAME} {__version__}",
                     text_color=MUTED, font=ctk.CTkFont(size=11), justify="left").grid(
            row=10, column=0, columnspan=2, padx=14, pady=(6, 12), sticky="sw")

    def _build_editor(self) -> None:
        wrapper = ctk.CTkFrame(self, fg_color="transparent")
        wrapper.grid(row=1, column=1, sticky="nsew", padx=(10, 12), pady=(10, 0))
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(0, weight=1)

        # wrap='none' keeps tree guides aligned; CTkTextbox supplies both
        # scrollbars itself, so no extra CTkScrollbar is packed beside it.
        font = self.mono_font
        self.text_box = ctk.CTkTextbox(wrapper, wrap="none", undo=True, font=font)
        self.text_box.grid(row=0, column=0, sticky="nsew")

        # A hint drawn over the empty editor rather than text inside it, so
        # there is nothing to delete before pasting and nothing to build by
        # accident.
        self.placeholder = ctk.CTkLabel(
            self.text_box, text=PLACEHOLDER, font=font, justify="left", anchor="nw",
            text_color=("gray55", "gray50"),
        )
        self.placeholder.place(x=8, y=6)
        self.placeholder.bind("<Button-1>", lambda _e: self.text_box.focus_set())

        actions = ctk.CTkFrame(wrapper, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", pady=10)
        for column in range(5):
            actions.grid_columnconfigure(column, weight=1)

        copy = ctk.CTkButton(actions, text="Copy", command=self.copy_to_clipboard)
        copy.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        _tooltip(copy, f"Copy the structure to the clipboard  ({_key('Shift+C')})")

        copy_md = ctk.CTkButton(actions, text="Copy for README", command=self.copy_for_readme)
        copy_md.grid(row=0, column=1, padx=6, sticky="ew")
        _tooltip(copy_md, "Copy it wrapped in a ``` code block, ready to paste into Markdown")

        save = ctk.CTkButton(actions, text="Save as…", command=self.save_to_file)
        save.grid(row=0, column=2, padx=6, sticky="ew")
        _tooltip(save, f"Write the structure to a file  ({_key('S')})")

        clear = ctk.CTkButton(actions, text="Clear", command=self.clear_editor, **SECONDARY)
        clear.grid(row=0, column=3, padx=6, sticky="ew")
        _tooltip(clear, f"Empty the editor  ({_key('Z')} brings it back)")

        self.create_button = ctk.CTkButton(actions, text="Create Folders…", command=self.create_folders)
        self.create_button.grid(row=0, column=4, padx=(6, 0), sticky="ew")
        _tooltip(self.create_button,
                 f"Turn the text in the editor into real folders and files  ({_key('Enter')})")

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(self, corner_radius=0, height=30)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        self.status_var = ctk.StringVar(value="Select a folder, or paste a structure and create it.")
        ctk.CTkLabel(bar, textvariable=self.status_var, anchor="w",
                     font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=14, pady=6, sticky="ew")

        # How the editor's text is understood, refreshed as you type.
        self.info_var = ctk.StringVar(value="")
        ctk.CTkLabel(bar, textvariable=self.info_var, anchor="e", text_color=MUTED,
                     font=ctk.CTkFont(size=12)).grid(row=0, column=1, padx=14, pady=6, sticky="e")

        self.progress = ctk.CTkProgressBar(bar, width=140, mode="indeterminate")
        self.progress.grid(row=0, column=2, padx=14, pady=6)
        self.progress.grid_remove()

    def _bind_shortcuts(self) -> None:
        shortcuts = [
            (f"<{MOD}-o>", self.select_folder),
            ("<F5>", self.rescan),
            (f"<{MOD}-r>", self.rescan),
            (f"<{MOD}-s>", self.save_to_file),
            (f"<{MOD}-Shift-C>", self.copy_to_clipboard),
            (f"<{MOD}-Return>", self.create_folders),
            (f"<{MOD}-KP_Enter>", self.create_folders),
        ]
        for sequence, action in shortcuts:
            # Bound on the text boxes too, returning "break": Tk's Text class
            # bindings run before the window's, and some of them (Ctrl+O
            # opens a line, Ctrl+Enter inserts one) would edit the text first.
            handler = self._shortcut(action)
            self.bind(sequence, handler)
            for box in (self.text_box, self.ignore_box):
                box.bind(sequence, handler)

        for box in (self.text_box, self.ignore_box):
            # On X11 Tk binds Ctrl+A to "start of line", not select-all.
            box.bind(f"<{MOD}-a>", lambda _e, box=box: self._select_all(box))

    @staticmethod
    def _shortcut(action: Callable[[], None]) -> Callable[[Any], str]:
        def handler(_event=None) -> str:
            action()
            return "break"
        return handler

    @staticmethod
    def _select_all(box: ctk.CTkTextbox) -> str:
        box.tag_add("sel", "1.0", "end-1c")
        box.mark_set("insert", "end-1c")
        return "break"

    def _watch_options(self) -> None:
        for var in (self.depth_var, self.sizes_var, self.gitignore_var, self.symlink_var):
            var.trace_add("write", lambda *_: self._options_changed())
        self.ignore_box.bind("<<Modified>>", self._on_patterns_modified)
        self.text_box.bind("<<Modified>>", self._on_editor_modified)

    def _restore_last_folder(self) -> None:
        last = self.settings["last_folder"]
        if last and os.path.isdir(last):
            self.source_folder = last
            self.rescan_button.configure(state="normal")
            self._status(f"Last folder: {_display_path(last)}. Press F5 to scan it again.")

    # ------------------------------------------------------------------
    # Small helpers
    # ------------------------------------------------------------------
    def _debounce(self, key: str, delay_ms: int, func: Callable[[], None]) -> None:
        """Run `func` once, `delay_ms` after the last call with this key."""
        job = self._jobs.pop(key, None)
        if job is not None:
            self.after_cancel(job)

        def run() -> None:
            self._jobs.pop(key, None)
            func()

        self._jobs[key] = self.after(delay_ms, run)

    def _current_rules(self) -> IgnoreRules:
        return IgnoreRules.from_text(self.ignore_box.get("1.0", "end"))

    def _current_depth(self) -> Optional[int]:
        value = self.depth_var.get()
        return None if value == "All" else int(value)

    def _current_format(self) -> str:
        return FORMAT_LABELS[self.format_var.get()]

    def _editor_text(self) -> str:
        return self.text_box.get("1.0", "end").strip()

    def _set_editor(self, text: str) -> None:
        """Replace the editor contents as one undoable step."""
        self.text_box.configure(autoseparators=False)
        try:
            self.text_box.edit_separator()
            self.text_box.delete("1.0", "end")
            self.text_box.insert("1.0", text)
            self.text_box.edit_separator()
        finally:
            self.text_box.configure(autoseparators=True)
        self._update_placeholder()

    def _show_tree(self, tree: Node) -> None:
        """Render a scanned tree into the editor and remember it as pristine."""
        self._last_rendered = render(tree, self._current_format(), stats=self.sizes_var.get())
        self._set_editor(self._last_rendered)

    def _editor_is_pristine(self) -> bool:
        """True while the editor still shows the last scan, unedited."""
        return self.tree is not None and self._editor_text() == self._last_rendered.strip()

    def _update_placeholder(self) -> None:
        if self.text_box.get("1.0", "end-1c"):
            self.placeholder.place_forget()
        else:
            self.placeholder.place(x=8, y=6)

    def _status(self, message: str) -> None:
        self.status_var.set(message)

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        if busy:
            self.progress.grid()
            self.progress.start()
        else:
            self.progress.stop()
            self.progress.grid_remove()
        state = "disabled" if busy else "normal"
        self.create_button.configure(state=state)
        self.rescan_button.configure(state="normal" if (not busy and self.source_folder) else "disabled")

    def _set_appearance(self, mode: str) -> None:
        ctk.set_appearance_mode(mode)
        self._save_settings()

    def _reset_patterns(self) -> None:
        self.ignore_box.delete("1.0", "end")
        self.ignore_box.insert("1.0", "\n".join(DEFAULT_IGNORE) + "\n")
        self._status("Ignore patterns reset to defaults.")

    def _save_settings(self) -> None:
        self.settings.update(
            format=self.format_var.get(),
            depth=self.depth_var.get(),
            sizes=bool(self.sizes_var.get()),
            gitignore=bool(self.gitignore_var.get()),
            symlinks=bool(self.symlink_var.get()),
            ignore_patterns=self.ignore_box.get("1.0", "end-1c"),
            appearance=self.appearance_var.get(),
            last_folder=self.source_folder or self.settings["last_folder"],
        )
        try:
            if self.state() == "normal":
                size = self.geometry().split("+", 1)[0]
                if _valid_size(size):
                    self.settings["geometry"] = size
        except tk.TclError:
            pass
        prefs.save(self.settings)

    # ------------------------------------------------------------------
    # Reacting to edits and option changes
    # ------------------------------------------------------------------
    def _on_editor_modified(self, _event=None) -> None:
        if not self.text_box.edit_modified():
            return  # the reset below fires <<Modified>> as well
        self.text_box.edit_modified(False)
        self._update_placeholder()
        self._debounce("info", 300, self._refresh_info)

    def _on_patterns_modified(self, _event=None) -> None:
        if not self.ignore_box.edit_modified():
            return
        self.ignore_box.edit_modified(False)
        self._debounce("patterns", 600, self._options_changed)

    def _options_changed(self) -> None:
        """Re-scan with the new options, unless that would discard edits."""
        self._save_settings()
        if self.tree is None or not self.source_folder:
            return
        if self._editor_is_pristine():
            self._debounce("rescan", 150, self.start_scan)
        else:
            self._status(f"Options changed. Press F5 to rescan; that replaces your edits ({_key('Z')} undoes it).")

    def _refresh_info(self) -> None:
        """Show how the editor's text will be understood."""
        if self._editor_is_pristine():
            self.info_var.set("")  # the status bar already describes the scan
            return
        text = self._editor_text()
        if not text:
            self.info_var.set("")
            return
        try:
            tree = parse(text, "auto")
            fmt = detect_format(text)
        except ParseError:
            self.info_var.set("Not a structure yet")
            return
        self.info_var.set(f"Reads as {FORMAT_NAMES.get(fmt, fmt)}: {_counts(tree)}")

    # ------------------------------------------------------------------
    # Scanning (threaded)
    # ------------------------------------------------------------------
    def select_folder(self) -> None:
        last = self.source_folder or self.settings["last_folder"]
        initial = os.path.dirname(last) if last and os.path.isdir(last) else os.path.expanduser("~")
        folder = filedialog.askdirectory(title="Select a folder to scan", initialdir=initial, mustexist=True)
        if folder:
            self.source_folder = folder
            self.start_scan()

    def rescan(self) -> None:
        if self.source_folder:
            self.start_scan()

    def start_scan(self) -> None:
        if not self.source_folder:
            return
        if self._busy:
            # Options changed mid-scan: run once more when this one is done.
            self._rescan_pending = True
            return
        self._set_busy(True)
        self._status(f"Scanning {_display_path(self.source_folder)} …")

        options = dict(
            rules=self._current_rules(),
            max_depth=self._current_depth(),
            include_sizes=self.sizes_var.get(),
            use_gitignore=self.gitignore_var.get(),
            follow_symlinks=self.symlink_var.get(),
        )
        folder = self.source_folder

        def worker() -> None:
            # Only ever touches the queue -- Tk widgets are not thread-safe.
            try:
                started = time.perf_counter()
                tree = scan(folder, **options)
                self._results.put(("scan", folder, tree, time.perf_counter() - started))
            except ScanError as exc:
                self._results.put(("error", "Could not scan folder", str(exc)))
            except Exception:  # pragma: no cover - defensive
                self._results.put(("error", "Unexpected error while scanning", traceback.format_exc()))

        threading.Thread(target=worker, daemon=True).start()

    def _drain_results(self) -> None:
        try:
            while True:
                kind, *payload = self._results.get_nowait()
                if kind == "scan":
                    folder, tree, elapsed = payload
                    self.tree = tree
                    self._show_tree(tree)
                    self.title(f"{tree.name} — {APP_NAME}")
                    self.info_var.set("")
                    self._status(
                        f"{_display_path(folder)}: {_counts(tree)}"
                        + (f", {format_size(tree.total_size)}" if self.sizes_var.get() else "")
                        + f" · scanned in {elapsed:.2f}s"
                    )
                    self._save_settings()
                elif kind == "error":
                    title, detail = payload
                    messagebox.showerror(title, detail, parent=self)
                    self._status(title)
                self._set_busy(False)
                if self._rescan_pending:
                    self._rescan_pending = False
                    self.start_scan()
        except queue.Empty:
            pass
        self._drain_job = self.after(100, self._drain_results)

    def report_callback_exception(self, exc, val, tb) -> None:
        # While the window is closing, customtkinter widgets still receive
        # <Configure> events after their canvases are gone; those TclErrors
        # are harmless noise, so only report errors that happen while running.
        if getattr(self, "_closing", False) and isinstance(val, tk.TclError):
            return
        super().report_callback_exception(exc, val, tb)

    def destroy(self) -> None:
        if not getattr(self, "_closing", False):
            try:
                self._save_settings()
            except Exception:
                pass
        self._closing = True
        # Without this the repeating timers fire once more after the widgets
        # are gone and Tk reports "invalid command name".
        jobs = list(getattr(self, "_jobs", {}).values())
        if getattr(self, "_drain_job", None) is not None:
            jobs.append(self._drain_job)
            self._drain_job = None
        for job in jobs:
            try:
                self.after_cancel(job)
            except Exception:
                pass
        self._jobs = {}
        super().destroy()

    # ------------------------------------------------------------------
    # Editor actions
    # ------------------------------------------------------------------
    def _on_format_change(self, *_args) -> None:
        """Re-render the editor contents in the newly selected format.

        An untouched scan is re-rendered from the scanned tree, so sizes and
        `...` markers survive. Anything else is re-parsed, so manual edits
        survive a format switch and the app doubles as a format converter.
        Text that cannot be parsed is left exactly as it is.
        """
        self._save_settings()
        text = self._editor_text()
        if not text:
            return
        if self._editor_is_pristine():
            self._show_tree(self.tree)
            return
        try:
            tree = parse(text, "auto")
        except ParseError as exc:
            self._status(f"Left the text as it is; it could not be converted: {exc}")
            return
        self._set_editor(render(tree, self._current_format(), stats=self.sizes_var.get()))

    def copy_to_clipboard(self) -> None:
        self._copy(self._editor_text(), "")

    def copy_for_readme(self) -> None:
        """Copy wrapped in a fenced code block, ready for a README."""
        text = self._editor_text()
        if not text:
            self._copy(text, "")
            return
        try:
            fmt = detect_format(text)
        except ParseError:
            fmt = self._current_format()
        if fmt == "markdown":
            self._copy(text, " as a Markdown list")  # already renders as a list
            return
        lang = {"json": "json", "yaml": "yaml"}.get(fmt, "text")
        self._copy(f"```{lang}\n{text}\n```", " as a code block")

    def _copy(self, text: str, how: str) -> None:
        if not text:
            self._status("Nothing to copy.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()  # keep the clipboard alive after the app closes
        self._status(f"Copied {len(text.splitlines())} lines{how} to the clipboard.")

    def save_to_file(self) -> None:
        text = self._editor_text()
        if not text:
            self._status("Nothing to save.")
            return
        fmt = self._current_format()
        extension = {"json": ".json", "yaml": ".yaml", "markdown": ".md"}.get(fmt, ".txt")
        types = [("Text", "*.txt"), ("Markdown", "*.md"), ("JSON", "*.json"), ("YAML", "*.yaml")]
        # The matching type goes first: some platforms preselect the first.
        types.sort(key=lambda item: item[1] != "*" + extension)
        name = self.tree.name if self.tree is not None and self.tree.name else "structure"
        last = self.settings["last_destination"]
        path = filedialog.asksaveasfilename(
            title="Save structure",
            defaultextension=extension,
            initialfile=f"{name}{extension}",
            initialdir=last if last and os.path.isdir(last) else os.path.expanduser("~"),
            filetypes=types + [("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError as exc:
            messagebox.showerror("Could not save file", str(exc), parent=self)
            return
        self._status(f"Saved to {_display_path(path)}")

    def clear_editor(self) -> None:
        if not self._editor_text():
            return
        self._set_editor("")
        self.tree = None
        self.info_var.set("")
        self._status(f"Editor cleared. {_key('Z')} brings it back.")

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------
    def _ask_build_options(self, tree: Node) -> Optional[Dict[str, Any]]:
        last = self.settings["last_destination"]
        destination = last if last and os.path.isdir(last) else os.path.expanduser("~")
        dialog = BuildDialog(
            self, tree, destination,
            write_readme=self.settings["write_readme"],
            open_after=self.settings["open_after_build"],
        )
        return dialog.ask()

    def create_folders(self) -> None:
        if self._busy:
            return
        text = self._editor_text()
        if not text:
            self._status("Nothing to create. Paste a structure or select a folder first.")
            return

        try:
            tree = parse(text, "auto")
        except ParseError as exc:
            messagebox.showerror("Could not read the structure", str(exc), parent=self)
            return

        options = self._ask_build_options(tree)
        if not options:
            self._status("Nothing was created.")
            return
        destination = options["destination"]

        try:
            entries = plan(tree, destination)
            created = build(tree, destination)
            readme = write_readme(tree, destination) if options["readme"] else None
        except (BuildError, OSError) as exc:
            messagebox.showerror("Could not create the structure", str(exc), parent=self)
            return

        self.settings.update(
            last_destination=destination,
            write_readme=bool(options["readme"]),
            open_after_build=bool(options["open"]),
        )
        self._save_settings()

        skipped = sum(1 for _, is_dir in entries if not is_dir) - sum(
            1 for path in created if os.path.isfile(path))
        message = f"Created {len(created)} entries in {_display_path(destination)}"
        if readme:
            message += ", plus README.md"
        if skipped > 0:
            message += f"; kept {skipped} existing file{'' if skipped == 1 else 's'}"
        self._status(message + ".")

        if options["open"]:
            # Open the new top folder itself when there is one.
            target = entries[0][0] if tree.name and entries else destination
            self._offer_to_open(target)

    def _offer_to_open(self, path: str) -> None:
        reveal(path)


def _valid_size(geometry: str) -> bool:
    """`WIDTHxHEIGHT` within sane bounds, so a bad value cannot hide the window."""
    try:
        width, height = (int(part) for part in geometry.split("x"))
    except ValueError:
        return False
    return 400 <= width <= 8000 and 300 <= height <= 8000


def _check_tk() -> None:
    """Refuse to open a window Tk cannot draw.

    Tk 8.5 -- what Apple's bundled Python links against -- opens CustomTkinter
    windows as a solid black rectangle with no error, so say what is wrong
    instead of leaving a blank window.
    """
    import tkinter

    if tkinter.TkVersion < 8.6:
        raise SystemExit(
            f"Foltree needs Tk 8.6 or newer, but this Python uses Tk {tkinter.TkVersion}.\n"
            "That version shows a black window. Install Python from python.org "
            "(or `brew install python-tk`) and run again with PYTHON=/path/to/python3 ./run.sh"
        )


def main() -> None:
    _check_tk()
    ctk.set_default_color_theme("blue")
    FoltreeApp().mainloop()


if __name__ == "__main__":
    main()
