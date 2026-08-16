"""Smoke tests that drive the real widgets.

Skipped automatically when there is no display or customtkinter is missing, so
the suite still passes on a headless box without the GUI extras installed.
"""

import os
import shutil
import tempfile
import time
import unittest

try:
    import customtkinter  # noqa: F401
    import tkinter

    _root = tkinter.Tk()
    _root.destroy()
    GUI_AVAILABLE = True
    GUI_SKIP_REASON = ""
except Exception as exc:  # pragma: no cover - environment dependent
    GUI_AVAILABLE = False
    GUI_SKIP_REASON = f"no usable Tk display ({exc})"

if GUI_AVAILABLE:
    from foltree.gui import FoltreeApp
    from foltree.parse import parse
    from foltree.render import FORMAT_LABELS


@unittest.skipUnless(GUI_AVAILABLE, GUI_SKIP_REASON)
class TestFoltreeApp(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="foltree-gui-")
        self.addCleanup(shutil.rmtree, self.workdir, True)
        os.makedirs(os.path.join(self.workdir, "src", "components"))
        os.makedirs(os.path.join(self.workdir, "assets"))
        for rel in ("src/main.py", "src/components/Button.tsx", "LICENSE"):
            with open(os.path.join(self.workdir, rel), "w", encoding="utf-8") as handle:
                handle.write("x")

        self.app = FoltreeApp()
        self.addCleanup(self.app.destroy)
        self.app.source_folder = self.workdir

    def _scan_and_wait(self, timeout=10.0):
        self.app.tree = None
        self.app.start_scan()
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            # The app drains worker results from an `after(100, ...)` timer, so
            # the loop has to actually let wall-clock time pass.
            self.app.update()
            if self.app.tree is not None and not self.app._busy:
                return
            time.sleep(0.02)
        self.fail("scan did not finish")

    def test_scan_populates_the_editor(self):
        self._scan_and_wait()
        text = self.app._editor_text()
        self.assertIn("src/", text)
        self.assertIn("main.py", text)
        self.assertIn("assets/", text)
        self.assertIn("files", self.app.status_var.get())

    def test_switching_format_preserves_the_structure(self):
        self._scan_and_wait()
        baseline = parse(self.app._editor_text(), "auto")
        for label in FORMAT_LABELS:
            with self.subTest(format=label):
                self.app.format_var.set(label)
                self.app.update()
                text = self.app._editor_text()
                self.assertTrue(text, f"{label} produced an empty editor")
                self.assertEqual(parse(text, "auto"), baseline)

    def test_manual_edits_survive_a_format_switch(self):
        self._scan_and_wait()
        self.app.format_var.set("Indented")
        self.app.update()
        self.app._set_editor("custom/\n    kept.txt\n")
        self.app.format_var.set("Tree")
        self.app.update()
        self.assertIn("kept.txt", self.app._editor_text())
        self.assertIn("custom/", self.app._editor_text())

    def test_create_folders_writes_the_edited_text(self):
        destination = os.path.join(self.workdir, "built")
        os.makedirs(destination)
        self.app._set_editor("newproj/\n├── api/\n│   └── app.py\n└── LICENSE\n")
        self.app._destination = lambda: destination

        from tkinter import messagebox

        original = messagebox.askokcancel
        messagebox.askokcancel = lambda *a, **k: True
        self.addCleanup(lambda: setattr(messagebox, "askokcancel", original))
        self.app._offer_to_open = lambda path: None

        self.app.create_folders()
        self.assertTrue(os.path.isfile(os.path.join(destination, "newproj", "api", "app.py")))
        self.assertTrue(os.path.isfile(os.path.join(destination, "newproj", "LICENSE")))

    def test_sizes_toggle_changes_the_output(self):
        self.app.sizes_var.set(True)
        self._scan_and_wait()
        self.assertIn(" B)", self.app._editor_text())

    def test_depth_limit_is_applied(self):
        self.app.depth_var.set("1")
        self._scan_and_wait()
        text = self.app._editor_text()
        self.assertIn("src/", text)
        self.assertNotIn("main.py", text)
        self.assertIn("...", text)

    def test_gitignore_toggle(self):
        with open(os.path.join(self.workdir, ".gitignore"), "w", encoding="utf-8") as handle:
            handle.write("assets/\n")
        self.app.gitignore_var.set(True)
        self._scan_and_wait()
        self.assertNotIn("assets/", self.app._editor_text())

    def test_copy_puts_text_on_the_clipboard(self):
        self._scan_and_wait()
        self.app.copy_to_clipboard()
        self.assertIn("main.py", self.app.clipboard_get())

    def test_clear_empties_the_editor(self):
        self._scan_and_wait()
        self.app.clear_editor()
        self.assertEqual(self.app._editor_text(), "")

    def test_clean_tree_is_offered_and_renders_without_guides(self):
        self._scan_and_wait()
        self.assertIn("Clean Tree", FORMAT_LABELS)
        self.app.format_var.set("Clean Tree")
        self.app.update()
        text = self.app._editor_text()
        self.assertIn("└── ", text)
        self.assertNotIn("│", text)

    def test_trailing_slash_toggle_updates_the_editor(self):
        self._scan_and_wait()
        self.assertIn("src/", self.app._editor_text())

        self.app.dir_suffix_var.set(False)
        self.app._refresh_editor()
        self.app.update()
        self.assertNotIn("src/", self.app._editor_text())
        self.assertIn("src", self.app._editor_text())

        self.app.dir_suffix_var.set(True)
        self.app._refresh_editor()
        self.app.update()
        self.assertIn("src/", self.app._editor_text())

    def test_bare_names_setting_reaches_the_parser(self):
        self.app._set_editor("proj/\n├── assets\n└── main.py\n")

        self.app.bare_names_var.set("Folders")
        self.assertTrue(self.app._parse(self.app._editor_text()).children[0].is_dir)

        self.app.bare_names_var.set("Files")
        self.assertFalse(self.app._parse(self.app._editor_text()).children[0].is_dir)

    def test_bare_names_setting_changes_what_gets_built(self):
        destination = os.path.join(self.workdir, "bare")
        os.makedirs(destination)
        self.app._set_editor("proj/\n└── assets\n")
        self.app._destination = lambda: destination
        self.app._offer_to_open = lambda path: None

        from tkinter import messagebox

        original = messagebox.askokcancel
        messagebox.askokcancel = lambda *a, **k: True
        self.addCleanup(lambda: setattr(messagebox, "askokcancel", original))

        self.app.bare_names_var.set("Files")
        self.app.create_folders()
        self.assertTrue(os.path.isfile(os.path.join(destination, "proj", "assets")))


@unittest.skipUnless(GUI_AVAILABLE, GUI_SKIP_REASON)
class TestTeardown(unittest.TestCase):
    def test_destroy_cancels_every_pending_timer(self):
        """Guards the "invalid command name ...<lambda>" noise on shutdown.

        CTkTextbox re-arms a scrollbar check every few milliseconds and
        ScalingTracker polls for DPI changes, so something is always pending.
        Cancelling only our own drain timer left theirs to fire into destroyed
        widgets, so destroy() has to clear the whole `after info` list.
        """
        app = FoltreeApp()
        app.update()

        self.assertTrue(app.tk.eval("after info").split(),
                        "expected customtkinter to have timers pending")
        app._cancel_pending_timers()
        self.assertEqual(app.tk.eval("after info").split(), [],
                         "a timer survived and will fire into destroyed widgets")
        app.destroy()

    def test_destroy_is_clean_after_a_scan(self):
        # Cancelling must not break teardown: Misc.after_cancel would also
        # delete the callback's Tcl command, making the owning widget fail to
        # destroy itself.
        app = FoltreeApp()
        app.update()
        app._set_editor("p/\n└── a.txt\n")
        app.update()
        app.destroy()  # must not raise


if __name__ == "__main__":
    unittest.main()
