import os
import shutil
import tempfile
import unittest

from foltree.ignore import IgnoreRules
from foltree.scanner import ScanError, scan


def make_tree(root, spec):
    """spec: {'dir/': {...}, 'file.txt': 'contents'}"""
    for name, value in spec.items():
        path = os.path.join(root, name.rstrip("/"))
        if isinstance(value, dict):
            os.makedirs(path, exist_ok=True)
            make_tree(path, value)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(value)


class ScannerTestCase(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.mkdtemp(prefix="foltree-")
        self.addCleanup(shutil.rmtree, self.root, True)


class TestScan(ScannerTestCase):
    def test_basic_structure(self):
        make_tree(self.root, {
            "src": {"main.py": "x", "util.py": "y"},
            "README.md": "hi",
        })
        tree = scan(self.root)
        self.assertTrue(tree.is_dir)
        self.assertEqual([c.name for c in tree.children], ["src", "README.md"])
        self.assertEqual([c.name for c in tree.children[0].children], ["main.py", "util.py"])

    def test_directories_sort_before_files(self):
        make_tree(self.root, {"zeta": {"a": ""}, "alpha.txt": ""})
        tree = scan(self.root)
        self.assertEqual([c.name for c in tree.children], ["zeta", "alpha.txt"])

    def test_ignored_directory_prunes_its_children(self):
        make_tree(self.root, {
            "node_modules": {"react": {"index.js": ""}},
            "app.js": "",
        })
        tree = scan(self.root, IgnoreRules(["node_modules"]))
        names = [n.name for n in tree.walk()]
        self.assertNotIn("node_modules", names)
        # The old version skipped the folder but still walked into it.
        self.assertNotIn("index.js", names)
        self.assertIn("app.js", names)

    def test_gitignore_is_opt_in(self):
        make_tree(self.root, {".gitignore": "secret/\n", "secret": {"key.txt": ""}})
        with_ignore = scan(self.root, use_gitignore=True)
        without = scan(self.root, use_gitignore=False)
        self.assertNotIn("secret", [n.name for n in with_ignore.walk()])
        self.assertIn("secret", [n.name for n in without.walk()])

    def test_max_depth_truncates_and_marks(self):
        make_tree(self.root, {"a": {"b": {"c": {"deep.txt": ""}}}})
        tree = scan(self.root, max_depth=2)
        first = tree.children[0]
        self.assertEqual(first.name, "a")
        self.assertEqual([c.name for c in first.children], ["b"])
        self.assertEqual(first.children[0].children, [])
        self.assertTrue(first.children[0].truncated)

    def test_max_depth_one_lists_direct_children_only(self):
        make_tree(self.root, {"a": {"b.txt": ""}, "c.txt": ""})
        tree = scan(self.root, max_depth=1)
        self.assertEqual([c.name for c in tree.children], ["a", "c.txt"])
        self.assertEqual(tree.children[0].children, [])

    def test_sizes_are_collected_and_summed(self):
        make_tree(self.root, {"a": {"x.txt": "12345"}, "y.txt": "123"})
        tree = scan(self.root, include_sizes=True)
        self.assertEqual(tree.total_size, 8)
        self.assertEqual(tree.file_count, 2)
        self.assertEqual(tree.dir_count, 1)

    def test_sizes_are_absent_by_default(self):
        make_tree(self.root, {"x.txt": "12345"})
        tree = scan(self.root)
        self.assertIsNone(tree.children[0].size)

    def test_missing_directory_raises(self):
        with self.assertRaises(ScanError):
            scan(os.path.join(self.root, "nope"))

    def test_scanning_a_file_raises(self):
        make_tree(self.root, {"a.txt": ""})
        with self.assertRaises(ScanError):
            scan(os.path.join(self.root, "a.txt"))

    @unittest.skipUnless(hasattr(os, "symlink"), "symlinks unsupported")
    def test_symlink_loop_does_not_hang(self):
        make_tree(self.root, {"a": {"b.txt": ""}})
        try:
            os.symlink(self.root, os.path.join(self.root, "a", "loop"))
        except (OSError, NotImplementedError):
            self.skipTest("cannot create symlinks here")
        tree = scan(self.root, follow_symlinks=True)
        self.assertIn("a", [n.name for n in tree.walk()])


if __name__ == "__main__":
    unittest.main()
