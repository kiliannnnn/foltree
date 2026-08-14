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
"""

from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import time
import traceback
from typing import Optional

import customtkinter as ctk
from tkinter import filedialog, messagebox

try:  # optional, the app works fine without it
    from CTkToolTip import CTkToolTip
except ImportError:  # pragma: no cover - depends on the environment
    CTkToolTip = None

from . import __version__
from .build import BuildError, build, plan
from .ignore import DEFAULT_IGNORE, IgnoreRules
from .node import Node
from .parse import ParseError, parse
from .render import FORMAT_LABELS, format_size, render
from .scanner import ScanError, scan

APP_NAME = "Foltree"
DEPTH_CHOICES = ["All", "1", "2", "3", "4", "5", "6", "8", "10"]


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


class FoltreeApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title(f"{APP_NAME} {__version__}")
        self.geometry("1040x700")
        self.minsize(820, 540)

        self.tree: Optional[Node] = None
        self.source_folder: Optional[str] = None
        self._results: "queue.Queue[tuple]" = queue.Queue()
        self._busy = False

        self._build_layout()
        self._bind_shortcuts()
        self._drain_job: Optional[str] = self.after(100, self._drain_results)

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
        bar.grid_columnconfigure(3, weight=1)

        select = ctk.CTkButton(bar, text="Select Folder", width=130, command=self.select_folder)
        select.grid(row=0, column=0, padx=(12, 6), pady=10)
        _tooltip(select, "Scan a folder and show its structure  (Ctrl+O)")

        self.rescan_button = ctk.CTkButton(
            bar, text="Rescan", width=90, command=self.rescan, state="disabled", **SECONDARY
        )
        self.rescan_button.grid(row=0, column=1, padx=6, pady=10)
        _tooltip(self.rescan_button, "Scan the same folder again with the current options  (F5)")

        ctk.CTkLabel(bar, text="Format").grid(row=0, column=2, padx=(18, 6))
        self.format_var = ctk.StringVar(value="Tree")
        format_menu = ctk.CTkOptionMenu(
            bar, variable=self.format_var, values=list(FORMAT_LABELS), width=140,
        )
        format_menu.grid(row=0, column=3, sticky="w")
        # trace('w', ...) is the deprecated Tk 8.5 spelling.
        self.format_var.trace_add("write", self._on_format_change)
        _tooltip(format_menu, "Switching format converts whatever is in the editor,\nso your edits are kept.")

        self.appearance_var = ctk.StringVar(value=ctk.get_appearance_mode())
        appearance = ctk.CTkOptionMenu(
            bar, variable=self.appearance_var, values=["System", "Light", "Dark"],
            width=100, command=lambda mode: ctk.set_appearance_mode(mode),
        )
        appearance.grid(row=0, column=4, padx=12, pady=10, sticky="e")

    def _build_sidebar(self) -> None:
        side = ctk.CTkFrame(self, corner_radius=0, width=250)
        side.grid(row=1, column=0, sticky="nsw")
        side.grid_propagate(False)
        side.grid_rowconfigure(9, weight=1)

        ctk.CTkLabel(side, text="Scan options", font=ctk.CTkFont(weight="bold")).grid(
            row=0, column=0, columnspan=2, padx=14, pady=(14, 8), sticky="w")

        ctk.CTkLabel(side, text="Max depth").grid(row=1, column=0, padx=(14, 6), pady=6, sticky="w")
        self.depth_var = ctk.StringVar(value="All")
        depth_menu = ctk.CTkOptionMenu(side, variable=self.depth_var, values=DEPTH_CHOICES, width=90)
        depth_menu.grid(row=1, column=1, padx=(0, 14), pady=6, sticky="e")
        _tooltip(depth_menu, "How many levels below the folder to show.\nDeeper levels are marked with '...'")

        self.sizes_var = ctk.BooleanVar(value=False)
        sizes = ctk.CTkSwitch(side, text="Show sizes & counts", variable=self.sizes_var)
        sizes.grid(row=2, column=0, columnspan=2, padx=14, pady=6, sticky="w")
        _tooltip(sizes, "Append file sizes, and per-folder file counts and totals.")

        self.gitignore_var = ctk.BooleanVar(value=False)
        gitignore = ctk.CTkSwitch(side, text="Respect .gitignore", variable=self.gitignore_var)
        gitignore.grid(row=3, column=0, columnspan=2, padx=14, pady=6, sticky="w")
        _tooltip(gitignore, "Also apply the scanned folder's own .gitignore rules,\non top of the patterns below.")

        self.symlink_var = ctk.BooleanVar(value=False)
        symlinks = ctk.CTkSwitch(side, text="Follow symlinks", variable=self.symlink_var)
        symlinks.grid(row=4, column=0, columnspan=2, padx=14, pady=6, sticky="w")
        _tooltip(symlinks, "Descend into symlinked folders. Loops are detected and stopped.")

        ctk.CTkLabel(side, text="Ignore patterns", font=ctk.CTkFont(weight="bold")).grid(
            row=5, column=0, columnspan=2, padx=14, pady=(16, 4), sticky="w")
        ctk.CTkLabel(side, text="One per line, gitignore syntax", text_color=("gray45", "gray60"),
                     font=ctk.CTkFont(size=11)).grid(row=6, column=0, columnspan=2, padx=14, sticky="w")

        self.ignore_box = ctk.CTkTextbox(side, height=190, wrap="none")
        self.ignore_box.grid(row=7, column=0, columnspan=2, padx=14, pady=(6, 6), sticky="ew")
        self.ignore_box.insert("1.0", "\n".join(DEFAULT_IGNORE) + "\n")

        reset = ctk.CTkButton(side, text="Reset patterns", height=28,
                              command=self._reset_patterns, **SECONDARY)
        reset.grid(row=8, column=0, columnspan=2, padx=14, pady=(0, 12), sticky="ew")

        self.output_folder_var = ctk.BooleanVar(value=True)
        auto_output = ctk.CTkCheckBox(side, text="Auto 'output' folder", variable=self.output_folder_var)
        auto_output.grid(row=10, column=0, columnspan=2, padx=14, pady=(6, 14), sticky="w")
        _tooltip(auto_output, "When creating folders, write into ./output/<timestamp>\ninstead of asking for a destination.")

    def _build_editor(self) -> None:
        wrapper = ctk.CTkFrame(self, fg_color="transparent")
        wrapper.grid(row=1, column=1, sticky="nsew", padx=(10, 12), pady=(10, 0))
        wrapper.grid_columnconfigure(0, weight=1)
        wrapper.grid_rowconfigure(0, weight=1)

        # wrap='none' keeps tree guides aligned; CTkTextbox supplies both
        # scrollbars itself, so no extra CTkScrollbar is packed beside it.
        self.text_box = ctk.CTkTextbox(wrapper, wrap="none", undo=True, font=_mono_font(13))
        self.text_box.grid(row=0, column=0, sticky="nsew")
        self.text_box.insert("1.0", self._placeholder())

        actions = ctk.CTkFrame(wrapper, fg_color="transparent")
        actions.grid(row=1, column=0, sticky="ew", pady=10)
        for column in range(4):
            actions.grid_columnconfigure(column, weight=1)

        copy = ctk.CTkButton(actions, text="Copy", command=self.copy_to_clipboard)
        copy.grid(row=0, column=0, padx=(0, 6), sticky="ew")
        _tooltip(copy, "Copy the structure to the clipboard  (Ctrl+Shift+C)")

        save = ctk.CTkButton(actions, text="Save as…", command=self.save_to_file)
        save.grid(row=0, column=1, padx=6, sticky="ew")
        _tooltip(save, "Write the structure to a file  (Ctrl+S)")

        clear = ctk.CTkButton(actions, text="Clear", command=self.clear_editor, **SECONDARY)
        clear.grid(row=0, column=2, padx=6, sticky="ew")

        self.create_button = ctk.CTkButton(actions, text="Create Folders", command=self.create_folders)
        self.create_button.grid(row=0, column=3, padx=(6, 0), sticky="ew")
        _tooltip(self.create_button, "Turn the text in the editor into real folders and files  (Ctrl+Enter)")

    def _build_statusbar(self) -> None:
        bar = ctk.CTkFrame(self, corner_radius=0, height=30)
        bar.grid(row=2, column=0, columnspan=2, sticky="ew")
        bar.grid_columnconfigure(0, weight=1)

        self.status_var = ctk.StringVar(value="Select a folder, or paste a structure and create it.")
        ctk.CTkLabel(bar, textvariable=self.status_var, anchor="w",
                     font=ctk.CTkFont(size=12)).grid(row=0, column=0, padx=14, pady=6, sticky="ew")

        self.progress = ctk.CTkProgressBar(bar, width=140, mode="indeterminate")
        self.progress.grid(row=0, column=1, padx=14, pady=6)
        self.progress.grid_remove()

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-o>", lambda _e: self.select_folder())
        self.bind("<F5>", lambda _e: self.rescan())
        self.bind("<Control-s>", lambda _e: self.save_to_file())
        self.bind("<Control-Shift-C>", lambda _e: self.copy_to_clipboard())
        self.bind("<Control-Return>", lambda _e: self.create_folders())

    @staticmethod
    def _placeholder() -> str:
        return (
            "Paste a folder structure here and press Create Folders,\n"
            "or click Select Folder to read one from disk.\n"
            "\n"
            "example/\n"
            "├── src/\n"
            "│   └── main.py\n"
            "├── assets/\n"
            "└── README.md\n"
        )

    # ------------------------------------------------------------------
    # Options
    # ------------------------------------------------------------------
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
        self.text_box.delete("1.0", "end")
        self.text_box.insert("1.0", text)

    def _reset_patterns(self) -> None:
        self.ignore_box.delete("1.0", "end")
        self.ignore_box.insert("1.0", "\n".join(DEFAULT_IGNORE) + "\n")
        self._status("Ignore patterns reset to defaults.")

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

    # ------------------------------------------------------------------
    # Scanning (threaded)
    # ------------------------------------------------------------------
    def select_folder(self) -> None:
        folder = filedialog.askdirectory(title="Select a folder to scan")
        if folder:
            self.source_folder = folder
            self.start_scan()

    def rescan(self) -> None:
        if self.source_folder:
            self.start_scan()

    def start_scan(self) -> None:
        if self._busy or not self.source_folder:
            return
        self._set_busy(True)
        self._status(f"Scanning {self.source_folder} …")

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
                self._results.put(("scan", tree, time.perf_counter() - started))
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
                    tree, elapsed = payload
                    self.tree = tree
                    self._set_editor(render(tree, self._current_format(), stats=self.sizes_var.get()))
                    self._status(
                        f"{tree.dir_count} folders, {tree.file_count} files"
                        + (f", {format_size(tree.total_size)}" if self.sizes_var.get() else "")
                        + f" — scanned in {elapsed:.2f}s"
                    )
                elif kind == "error":
                    title, detail = payload
                    messagebox.showerror(title, detail)
                    self._status(title)
                self._set_busy(False)
        except queue.Empty:
            pass
        self._drain_job = self.after(100, self._drain_results)

    def destroy(self) -> None:
        # Without this the repeating timer fires once more after the widgets
        # are gone and Tk reports "invalid command name".
        if self._drain_job is not None:
            try:
                self.after_cancel(self._drain_job)
            except Exception:
                pass
            self._drain_job = None
        super().destroy()

    # ------------------------------------------------------------------
    # Editor actions
    # ------------------------------------------------------------------
    def _on_format_change(self, *_args) -> None:
        """Re-render the editor contents in the newly selected format.

        The text is re-parsed rather than re-rendered from the last scan, so
        manual edits survive a format switch and the app doubles as a
        format converter for structures you paste in.
        """
        text = self._editor_text()
        if not text:
            return
        try:
            tree = parse(text, "auto")
        except ParseError:
            if self.tree is None:
                return
            tree = self.tree
        self._set_editor(render(tree, self._current_format(), stats=self.sizes_var.get()))

    def copy_to_clipboard(self) -> None:
        text = self._editor_text()
        if not text:
            self._status("Nothing to copy.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.update_idletasks()  # keep the clipboard alive after the app closes
        self._status(f"Copied {len(text.splitlines())} lines to the clipboard.")

    def save_to_file(self) -> None:
        text = self._editor_text()
        if not text:
            self._status("Nothing to save.")
            return
        fmt = self._current_format()
        extension = {"json": ".json", "yaml": ".yaml", "markdown": ".md"}.get(fmt, ".txt")
        path = filedialog.asksaveasfilename(
            title="Save structure",
            defaultextension=extension,
            initialfile=f"{(self.tree.name if self.tree else 'structure')}{extension}",
            filetypes=[("Text", "*.txt"), ("Markdown", "*.md"), ("JSON", "*.json"),
                       ("YAML", "*.yaml"), ("All files", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text + "\n")
        except OSError as exc:
            messagebox.showerror("Could not save file", str(exc))
            return
        self._status(f"Saved to {path}")

    def clear_editor(self) -> None:
        self.text_box.delete("1.0", "end")
        self.tree = None
        self._status("Editor cleared.")

    # ------------------------------------------------------------------
    # Building
    # ------------------------------------------------------------------
    def _destination(self) -> Optional[str]:
        if not self.output_folder_var.get():
            chosen = filedialog.askdirectory(title="Where should the structure be created?")
            return chosen or None

        base = os.path.join(os.getcwd(), "output")
        target = os.path.join(base, time.strftime("%Y%m%d-%H%M%S"))
        try:
            os.makedirs(target, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("Could not create output folder", str(exc))
            return None
        return target

    def create_folders(self) -> None:
        text = self._editor_text()
        if not text:
            self._status("Nothing to create — the editor is empty.")
            return

        try:
            tree = parse(text, "auto")
        except ParseError as exc:
            messagebox.showerror("Could not read the structure", str(exc))
            return

        destination = self._destination()
        if not destination:
            return

        try:
            entries = plan(tree, destination)
        except BuildError as exc:
            messagebox.showerror("Unsafe structure", str(exc))
            return

        folders = sum(1 for _, is_dir in entries if is_dir)
        files = len(entries) - folders
        confirm = messagebox.askokcancel(
            "Create structure",
            f"Create {folders} folders and {files} files in:\n{destination}\n\n"
            "Existing files will not be overwritten.",
        )
        if not confirm:
            return

        try:
            created = build(tree, destination)
        except BuildError as exc:
            messagebox.showerror("Could not create the structure", str(exc))
            return

        self._status(f"Created {len(created)} entries in {destination}")
        self._offer_to_open(destination)

    def _offer_to_open(self, path: str) -> None:
        """Reveal the new folder in the system file manager.

        Uses a subprocess argument list rather than a shell string so paths
        containing spaces or quotes cannot break the command.
        """
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(
                    ["xdg-open", path],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
        except Exception:
            pass  # opening a file manager is a nicety, never a failure


def main() -> None:
    ctk.set_appearance_mode("System")
    ctk.set_default_color_theme("blue")
    FoltreeApp().mainloop()


if __name__ == "__main__":
    main()
