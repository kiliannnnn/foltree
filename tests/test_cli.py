import contextlib
import io
import os
import shutil
import sys
import tempfile
import unittest

from foltree.cli import main


class CliTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="foltree-cli-")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def run_cli(self, *argv, stdin=None):
        out, err = io.StringIO(), io.StringIO()
        old_stdin = sys.stdin
        if stdin is not None:
            sys.stdin = io.StringIO(stdin)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                try:
                    code = main(list(argv))
                except SystemExit as exc:  # argparse errors
                    code = exc.code
        finally:
            sys.stdin = old_stdin
        return code, out.getvalue(), err.getvalue()

    def write(self, name, text):
        path = os.path.join(self.tmp, name)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path


class TestScan(CliTestCase):
    def test_format_aliases_are_accepted(self):
        os.makedirs(os.path.join(self.tmp, "proj", "src"))
        code, out, _ = self.run_cli("scan", os.path.join(self.tmp, "proj"), "-f", "md")
        self.assertEqual(code, 0)
        self.assertIn("**src/**", out)

    def test_unknown_format_is_a_usage_error(self):
        code, _, err = self.run_cli("scan", self.tmp, "-f", "nope")
        self.assertEqual(code, 2)
        self.assertIn("Unknown format", err)


class TestBuild(CliTestCase):
    def test_entries_in_the_default_ignore_list_are_still_built(self):
        source = self.write("s.txt", "app/\n├── .env\n├── build/\n└── vendor/\n")
        out_dir = os.path.join(self.tmp, "out")
        code, _, _ = self.run_cli("build", "-i", source, "-o", out_dir)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(out_dir, "app", ".env")))
        self.assertTrue(os.path.isdir(os.path.join(out_dir, "app", "build")))
        self.assertTrue(os.path.isdir(os.path.join(out_dir, "app", "vendor")))

    def test_explicit_ignore_patterns_still_apply(self):
        source = self.write("s.txt", "app/\n├── keep.py\n└── skip.log\n")
        out_dir = os.path.join(self.tmp, "out")
        self.run_cli("build", "-i", source, "-o", out_dir, "--ignore", "*.log")
        self.assertTrue(os.path.exists(os.path.join(out_dir, "app", "keep.py")))
        self.assertFalse(os.path.exists(os.path.join(out_dir, "app", "skip.log")))

    def test_build_from_stdin_with_a_chat_answer(self):
        out_dir = os.path.join(self.tmp, "out")
        text = "Here you go:\n```\nweb/\n├── index.html  # page\n└── css/\n```\nEnjoy!\n"
        code, _, _ = self.run_cli("build", "-o", out_dir, stdin=text)
        self.assertEqual(code, 0)
        self.assertTrue(os.path.isfile(os.path.join(out_dir, "web", "index.html")))
        self.assertTrue(os.path.isdir(os.path.join(out_dir, "web", "css")))

    def test_readme_goes_inside_the_new_folder(self):
        source = self.write("s.txt", "app/\n└── main.py\n")
        out_dir = os.path.join(self.tmp, "out")
        self.run_cli("build", "-i", source, "-o", out_dir, "--readme")
        with open(os.path.join(out_dir, "app", "README.md"), encoding="utf-8") as handle:
            self.assertIn("└── main.py", handle.read())

    def test_readme_never_replaces_an_existing_one(self):
        source = self.write("s.txt", "a.txt\nb.txt\n")
        out_dir = os.path.join(self.tmp, "out")
        os.makedirs(out_dir)
        readme = os.path.join(out_dir, "README.md")
        with open(readme, "w", encoding="utf-8") as handle:
            handle.write("my real readme\n")
        code, _, err = self.run_cli("build", "-i", source, "-o", out_dir, "--readme")
        self.assertEqual(code, 0)
        self.assertIn("Kept the existing README.md", err)
        with open(readme, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "my real readme\n")


if __name__ == "__main__":
    unittest.main()
