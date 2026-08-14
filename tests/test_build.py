import os
import shutil
import tempfile
import unittest

from foltree.build import BuildError, build, plan
from foltree.ignore import IgnoreRules
from foltree.parse import parse
from foltree.render import render
from foltree.scanner import scan


class BuildTestCase(unittest.TestCase):
    def setUp(self):
        self.dest = tempfile.mkdtemp(prefix="foltree-out-")
        self.addCleanup(shutil.rmtree, self.dest, True)


class TestBuild(BuildTestCase):
    def test_creates_files_and_directories(self):
        tree = parse("project/\n├── src/\n│   └── main.py\n└── README.md\n")
        build(tree, self.dest)
        root = os.path.join(self.dest, "project")
        self.assertTrue(os.path.isdir(os.path.join(root, "src")))
        self.assertTrue(os.path.isfile(os.path.join(root, "src", "main.py")))
        self.assertTrue(os.path.isfile(os.path.join(root, "README.md")))

    def test_empty_directories_are_created_as_directories(self):
        tree = parse("p/\n└── assets/\n")
        build(tree, self.dest)
        self.assertTrue(os.path.isdir(os.path.join(self.dest, "p", "assets")))

    def test_extensionless_files_are_created_as_files(self):
        tree = parse("p/\n├── LICENSE\n└── Dockerfile\n")
        build(tree, self.dest)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "p", "LICENSE")))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "p", "Dockerfile")))

    def test_path_traversal_is_refused(self):
        tree = parse("p/\n└── ../../escaped.txt\n")
        # `..` is stripped to a safe component rather than escaping the folder.
        created = build(tree, self.dest)
        for path in created:
            self.assertTrue(os.path.abspath(path).startswith(os.path.abspath(self.dest)))
        self.assertFalse(os.path.exists(os.path.join(os.path.dirname(self.dest), "escaped.txt")))

    def test_absolute_paths_are_neutralised(self):
        from foltree.node import Node

        root = Node("p", is_dir=True)
        root.add(Node("/etc/passwd"))
        created = build(root, self.dest)
        for path in created:
            self.assertTrue(os.path.abspath(path).startswith(os.path.abspath(self.dest)))

    def test_existing_files_are_not_truncated(self):
        target = os.path.join(self.dest, "p", "keep.txt")
        os.makedirs(os.path.dirname(target))
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("important")

        build(parse("p/\n└── keep.txt\n"), self.dest)
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "important")

    def test_overwrite_flag_truncates(self):
        target = os.path.join(self.dest, "p", "keep.txt")
        os.makedirs(os.path.dirname(target))
        with open(target, "w", encoding="utf-8") as handle:
            handle.write("important")

        build(parse("p/\n└── keep.txt\n"), self.dest, overwrite=True)
        with open(target, encoding="utf-8") as handle:
            self.assertEqual(handle.read(), "")

    def test_dry_run_touches_nothing(self):
        tree = parse("p/\n└── a.txt\n")
        paths = build(tree, self.dest, dry_run=True)
        self.assertTrue(paths)
        self.assertFalse(os.path.exists(os.path.join(self.dest, "p")))

    def test_plan_matches_build(self):
        tree = parse("p/\n├── src/\n│   └── a.py\n└── b.txt\n")
        planned = [path for path, _ in plan(tree, self.dest)]
        self.assertEqual(planned, build(tree, self.dest))

    def test_ignore_rules_apply_when_building(self):
        tree = parse("p/\n├── keep.py\n└── skip.log\n")
        build(tree, self.dest, rules=IgnoreRules(["*.log"]))
        self.assertTrue(os.path.exists(os.path.join(self.dest, "p", "keep.py")))
        self.assertFalse(os.path.exists(os.path.join(self.dest, "p", "skip.log")))

    def test_fragment_builds_directly_into_dest(self):
        tree = parse("a.txt\nb.txt\n")
        build(tree, self.dest)
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "a.txt")))
        self.assertTrue(os.path.isfile(os.path.join(self.dest, "b.txt")))


class TestFullCycle(BuildTestCase):
    def test_scan_render_parse_build_reproduces_the_structure(self):
        source = tempfile.mkdtemp(prefix="foltree-src-")
        self.addCleanup(shutil.rmtree, source, True)
        os.makedirs(os.path.join(source, "src", "components"))
        os.makedirs(os.path.join(source, "assets"))
        for rel in ("src/main.py", "src/components/Button.tsx", "LICENSE", "README.md"):
            with open(os.path.join(source, rel), "w", encoding="utf-8") as handle:
                handle.write("x")

        original = scan(source)
        for fmt in ("indented", "tree", "ascii", "markdown", "json", "yaml"):
            with self.subTest(format=fmt):
                dest = tempfile.mkdtemp(prefix=f"foltree-{fmt}-")
                self.addCleanup(shutil.rmtree, dest, True)

                build(parse(render(original, fmt), fmt), dest)
                rebuilt = scan(os.path.join(dest, original.name))
                self.assertEqual(render(rebuilt, "tree"), render(original, "tree"))


if __name__ == "__main__":
    unittest.main()
