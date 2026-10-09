"""Smoke tests that drive the real widgets.

Skipped automatically when there is no display or customtkinter is missing, so
the suite still passes on a headless box without the GUI extras installed.
"""

import gc
import os
import shutil
import tempfile
import time
import unittest



def collect_garbage():
    """Collect leftovers of earlier test apps on the main thread.

    Tkinter fonts and variables call into Tcl from `__del__`. If the garbage
    collector happens to run in a scan worker thread, that call targets an
    interpreter whose main loop is gone and the worker hangs for good.
    """
    gc.collect()


# Never read or write the real settings file from the tests.
os.environ["FOLTREE_CONFIG_DIR"] = tempfile.mkdtemp(prefix="foltree-settings-")

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
    from foltree.gui import MOD, BuildDialog, FoltreeApp
    from foltree.parse import parse
    from foltree.render import FORMAT_LABELS


@unittest.skipUnless(GUI_AVAILABLE, GUI_SKIP_REASON)
class TestFoltreeApp(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="foltree-gui-")
        self.addCleanup(shutil.rmtree, self.workdir, True)
        settings_file = os.path.join(os.environ["FOLTREE_CONFIG_DIR"], "settings.json")
        if os.path.exists(settings_file):
            os.remove(settings_file)
        os.makedirs(os.path.join(self.workdir, "src", "components"))
        os.makedirs(os.path.join(self.workdir, "assets"))
        for rel in ("src/main.py", "src/components/Button.tsx", "LICENSE"):
            with open(os.path.join(self.workdir, rel), "w", encoding="utf-8") as handle:
                handle.write("x")

        collect_garbage()
        self.app = FoltreeApp()
        self.addCleanup(collect_garbage)
        self.addCleanup(lambda: self.app.destroy())
        self.app.source_folder = self.workdir

    def _pump(self, seconds=0.5):
        """Let `after` timers (debounces, the results drain) actually run."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.app.update()
            time.sleep(0.02)

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
        self.fail(f"scan did not finish (busy={self.app._busy}, tree={self.app.tree is not None}, "
                  f"status={self.app.status_var.get()!r})")

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
        self.app._ask_build_options = lambda tree: {
            "destination": destination, "readme": False, "open": False}

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


    # -- friction fixes ------------------------------------------------
    def test_editor_starts_empty_with_a_hint_over_it(self):
        self.assertEqual(self.app._editor_text(), "")
        self.assertTrue(self.app.placeholder.winfo_ismapped() or self.app.placeholder.place_info())
        self.app._set_editor("a.txt\n")
        self.assertEqual(self.app.placeholder.place_info(), {})

    def test_create_with_an_empty_editor_builds_nothing(self):
        self.app._ask_build_options = lambda tree: self.fail("should not ask")
        self.app.create_folders()
        self.assertIn("Nothing to create", self.app.status_var.get())

    def _press(self, sequence):
        widget = self.app.text_box._textbox
        widget.focus_force()
        self.app.update()
        widget.event_generate(sequence)
        self.app.update()

    def test_create_shortcut_does_not_type_a_newline(self):
        asked = []
        self.app._ask_build_options = lambda tree: asked.append(tree)  # returns None: cancelled
        self.app._set_editor("app/\n└── a.py")
        self.app.text_box.mark_set("insert", "1.2")
        self._press(f"<{MOD}-Return>")
        self.assertEqual(len(asked), 1)
        self.assertEqual(self.app._editor_text(), "app/\n└── a.py")

    def test_open_shortcut_does_not_type_a_newline(self):
        from tkinter import filedialog

        original = filedialog.askdirectory
        filedialog.askdirectory = lambda **kwargs: ""
        self.addCleanup(lambda: setattr(filedialog, "askdirectory", original))
        self.app._set_editor("app/\n└── a.py")
        self.app.text_box.mark_set("insert", "1.2")
        self._press(f"<{MOD}-o>")
        self.assertEqual(self.app._editor_text(), "app/\n└── a.py")

    def test_select_all_shortcut(self):
        self.app._set_editor("one\ntwo")
        self._press(f"<{MOD}-a>")
        self.assertEqual(self.app.text_box.get("sel.first", "sel.last"), "one\ntwo")

    def test_changing_an_option_rescans_an_untouched_scan(self):
        self._scan_and_wait()
        self.assertIn("main.py", self.app._editor_text())
        self.app.depth_var.set("1")
        self._pump(1.0)
        self.assertNotIn("main.py", self.app._editor_text())

    def test_changing_an_option_never_discards_edits(self):
        self._scan_and_wait()
        self.app._set_editor("mine/\n└── kept.txt")
        self.app.depth_var.set("1")
        self._pump(0.6)
        self.assertEqual(self.app._editor_text(), "mine/\n└── kept.txt")
        self.assertIn("F5", self.app.status_var.get())

    def test_format_switch_keeps_sizes_of_an_untouched_scan(self):
        self.app.sizes_var.set(True)
        self._scan_and_wait()
        self.app.format_var.set("Indented")
        self.app.update()
        self.assertIn(" B)", self.app._editor_text())

    def test_unconvertible_text_is_left_alone(self):
        self.app._set_editor("{not json")
        self.app.format_var.set("YAML")
        self.app.update()
        self.assertEqual(self.app._editor_text(), "{not json")

    def test_clear_can_be_undone(self):
        self._scan_and_wait()
        before = self.app._editor_text()
        self.app.clear_editor()
        self.assertEqual(self.app._editor_text(), "")
        self.app.text_box.edit_undo()
        self.assertEqual(self.app._editor_text(), before)

    def test_live_feedback_describes_pasted_text(self):
        self.app._set_editor("Here:\n```\nweb/\n├── index.html  # page\n└── css/\n```")
        self._pump(0.6)
        self.assertIn("1 folder, 1 file", self.app.info_var.get())

    def test_copy_for_readme_wraps_in_a_code_block(self):
        self._scan_and_wait()
        self.app.copy_for_readme()
        copied = self.app.clipboard_get()
        self.assertTrue(copied.startswith("```text\n"), copied[:20])
        self.assertTrue(copied.endswith("\n```"))

    def test_settings_survive_a_restart(self):
        self.app.format_var.set("Markdown")
        self.app.sizes_var.set(True)
        self.app.update()
        self.app.destroy()
        collect_garbage()
        self.app = FoltreeApp()
        self.assertEqual(self.app.format_var.get(), "Markdown")
        self.assertTrue(self.app.sizes_var.get())

    def test_create_writes_readme_and_remembers_destination(self):
        destination = os.path.join(self.workdir, "dest")
        self.app._set_editor("site/\n└── index.html")
        self.app._ask_build_options = lambda tree: {
            "destination": destination, "readme": True, "open": False}
        self.app.create_folders()
        self.assertTrue(os.path.isfile(os.path.join(destination, "site", "README.md")))
        self.assertEqual(self.app.settings["last_destination"], destination)


@unittest.skipUnless(GUI_AVAILABLE, GUI_SKIP_REASON)
class TestBuildDialog(unittest.TestCase):
    def setUp(self):
        self.workdir = tempfile.mkdtemp(prefix="foltree-dialog-")
        self.addCleanup(shutil.rmtree, self.workdir, True)
        collect_garbage()
        self.app = FoltreeApp()
        self.addCleanup(collect_garbage)
        self.addCleanup(self.app.destroy)

    def dialog(self, text, destination):
        dialog = BuildDialog(self.app, parse(text), destination)
        self.addCleanup(lambda: dialog.winfo_exists() and dialog.destroy())
        self.app.update()
        return dialog

    def test_confirm_returns_the_choices(self):
        dialog = self.dialog("app/\n└── a.py", self.workdir)
        dialog.readme_var.set(True)
        dialog._confirm()
        self.assertEqual(dialog.result["destination"], self.workdir)
        self.assertTrue(dialog.result["readme"])

    def test_fragment_warns_that_entries_go_straight_in(self):
        dialog = self.dialog("a.txt\nb.txt", self.workdir)
        self.assertIn("no single top folder", dialog.note_var.get())

    def test_existing_files_are_reported(self):
        os.makedirs(os.path.join(self.workdir, "app"))
        with open(os.path.join(self.workdir, "app", "a.py"), "w", encoding="utf-8"):
            pass
        dialog = self.dialog("app/\n└── a.py", self.workdir)
        self.assertIn("1 file already exists", dialog.note_var.get())

    def test_empty_destination_cannot_be_confirmed(self):
        dialog = self.dialog("app/\n└── a.py", self.workdir)
        dialog.dest_var.set("")
        dialog._confirm()
        self.assertIsNone(dialog.result)
        self.assertEqual(dialog.create_button.cget("state"), "disabled")


if __name__ == "__main__":
    unittest.main()
