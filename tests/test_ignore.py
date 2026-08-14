import unittest

from foltree.ignore import IgnoreRules


class TestIgnoreRules(unittest.TestCase):
    def test_plain_name_matches_whole_segment_only(self):
        rules = IgnoreRules([".git", "dist"])
        self.assertTrue(rules.match(".git", is_dir=True))
        self.assertTrue(rules.match("src/.git", is_dir=True))
        self.assertTrue(rules.match("dist", is_dir=True))
        # The old substring matcher wrongly caught both of these.
        self.assertFalse(rules.match(".gitignore"))
        self.assertFalse(rules.match("distribution", is_dir=True))

    def test_descendants_of_an_ignored_directory_are_ignored(self):
        rules = IgnoreRules(["node_modules"])
        self.assertTrue(rules.match("node_modules/react/index.js"))
        self.assertTrue(rules.match("app/node_modules/react/index.js"))

    def test_glob_patterns(self):
        rules = IgnoreRules(["*.pyc", "test_*.py"])
        self.assertTrue(rules.match("main.pyc"))
        self.assertTrue(rules.match("pkg/sub/main.pyc"))
        self.assertTrue(rules.match("test_thing.py"))
        self.assertFalse(rules.match("main.py"))

    def test_anchored_patterns(self):
        rules = IgnoreRules(["/build"])
        self.assertTrue(rules.match("build", is_dir=True))
        self.assertFalse(rules.match("src/build", is_dir=True))

    def test_directory_only_patterns(self):
        rules = IgnoreRules(["build/"])
        self.assertTrue(rules.match("build", is_dir=True))
        self.assertFalse(rules.match("build", is_dir=False))
        self.assertTrue(rules.match("build/out.js"))

    def test_negation_reincludes(self):
        rules = IgnoreRules(["*.log", "!keep.log"])
        self.assertTrue(rules.match("debug.log"))
        self.assertFalse(rules.match("keep.log"))

    def test_comments_and_blank_lines_are_skipped(self):
        rules = IgnoreRules(["# a comment", "", "   ", "dist"])
        self.assertEqual(len(rules), 1)
        self.assertTrue(rules.match("dist", is_dir=True))

    def test_double_star(self):
        rules = IgnoreRules(["**/tmp"])
        self.assertTrue(rules.match("tmp", is_dir=True))
        self.assertTrue(rules.match("a/b/tmp", is_dir=True))

    def test_empty_ruleset_matches_nothing(self):
        self.assertFalse(IgnoreRules().match("anything"))


if __name__ == "__main__":
    unittest.main()
