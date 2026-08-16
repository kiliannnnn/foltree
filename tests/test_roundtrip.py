import unittest

from foltree.node import Node
from foltree.parse import detect_format, parse
from foltree.render import FORMATS, render

TEXT_FORMATS = ["indented", "tree", "ascii", "markdown", "json", "yaml"]


def sample_tree():
    root = Node("project", is_dir=True)
    src = root.add(Node("src", is_dir=True))
    src.add(Node("main.py"))
    src.add(Node("utils.py"))
    components = src.add(Node("components", is_dir=True))
    components.add(Node("Button.tsx"))
    root.add(Node(".github", is_dir=True)).add(Node("workflows", is_dir=True)).add(Node("ci.yml"))
    root.add(Node("assets", is_dir=True))  # empty directory
    root.add(Node("Dockerfile"))
    root.add(Node("LICENSE"))
    root.add(Node("README.md"))
    return root


class TestRoundTrip(unittest.TestCase):
    def test_every_format_round_trips(self):
        original = sample_tree()
        for fmt in TEXT_FORMATS:
            with self.subTest(format=fmt):
                text = render(original, fmt)
                self.assertEqual(parse(text, fmt), original)

    def test_auto_detection_round_trips(self):
        original = sample_tree()
        for fmt in TEXT_FORMATS:
            with self.subTest(format=fmt):
                text = render(original, fmt)
                self.assertEqual(detect_format(text), "tree" if fmt == "ascii" else fmt)
                self.assertEqual(parse(text, "auto"), original)

    def test_round_trip_with_stats_enabled(self):
        original = sample_tree()
        for node in original.walk():
            if not node.is_dir:
                node.size = 1234
        for fmt in TEXT_FORMATS:
            with self.subTest(format=fmt):
                text = render(original, fmt, stats=True)
                self.assertEqual(parse(text, fmt), original)

    def test_all_registered_formats_are_covered(self):
        self.assertEqual(set(FORMATS), set(TEXT_FORMATS))


class TestRenderShape(unittest.TestCase):
    def test_tree_uses_last_connector_for_final_entry(self):
        text = render(sample_tree(), "tree")
        lines = text.splitlines()
        self.assertEqual(lines[0], "project/")
        self.assertTrue(lines[-1].startswith("└── "), lines[-1])
        # The old renderer emitted "├──" for every single entry.
        self.assertIn("└── ", text)
        self.assertIn("│   ", text)

    def test_directories_keep_a_trailing_slash(self):
        text = render(sample_tree(), "tree")
        self.assertIn("assets/", text)
        self.assertIn("src/", text)
        self.assertNotIn("README.md/", text)

    def test_indented_format_nesting(self):
        text = render(sample_tree(), "indented")
        self.assertIn("project/", text)
        self.assertIn("    src/", text)
        self.assertIn("        main.py", text)

    def test_ascii_format_has_no_unicode(self):
        text = render(sample_tree(), "ascii")
        self.assertTrue(text.isascii())

    def test_stats_are_rendered_when_requested(self):
        root = Node("p", is_dir=True)
        root.add(Node("a.txt", size=2048))
        self.assertIn("2.0 KB", render(root, "tree", stats=True))
        self.assertNotIn("2.0 KB", render(root, "tree", stats=False))


class TestParseEdgeCases(unittest.TestCase):
    def test_extensionless_names_are_files_not_folders(self):
        # The old heuristic (`'.' not in name`) made all of these directories.
        tree = parse("project/\n├── LICENSE\n├── Dockerfile\n└── Makefile\n")
        for child in tree.children:
            self.assertFalse(child.is_dir, f"{child.name} should be a file")

    def test_all_caps_names_are_files(self):
        # PKG-INFO, AUTHORS and friends have no extension and are not in the
        # known-names list, but ALL-CAPS is a reliable file convention.
        tree = parse("p/\n├── PKG-INFO\n├── AUTHORS\n└── CODEOWNERS\n")
        for child in tree.children:
            self.assertFalse(child.is_dir, f"{child.name} should be a file")

    def test_bare_lowercase_names_are_directories(self):
        tree = parse("p/\n├── assets\n└── components\n")
        for child in tree.children:
            self.assertTrue(child.is_dir, f"{child.name} should be a directory")

    def test_dot_directories_stay_directories(self):
        tree = parse("p/\n└── .github/\n    └── workflows/\n        └── ci.yml\n")
        github = tree.children[0]
        self.assertTrue(github.is_dir)
        self.assertTrue(github.children[0].is_dir)
        self.assertFalse(github.children[0].children[0].is_dir)

    def test_dotfiles_are_files(self):
        tree = parse("p/\n├── .gitignore\n└── .env.local\n")
        self.assertFalse(any(c.is_dir for c in tree.children))

    def test_anything_with_children_is_a_directory(self):
        tree = parse("p/\n└── weird.name\n    └── inside.txt\n")
        self.assertTrue(tree.children[0].is_dir)

    def test_depth_survives_a_closing_branch(self):
        """The bug that broke Clean Tree round-trips.

        After a `└──` the guide column becomes blank, and the old parser
        counted those blanks as extra indentation, so everything following a
        closed branch landed at the wrong depth.
        """
        text = (
            "root/\n"
            "├── a/\n"
            "│   └── deep.txt\n"
            "└── b/\n"
            "    └── other.txt\n"
        )
        tree = parse(text)
        self.assertEqual([c.name for c in tree.children], ["a", "b"])
        self.assertEqual([c.name for c in tree.children[0].children], ["deep.txt"])
        self.assertEqual([c.name for c in tree.children[1].children], ["other.txt"])

    def test_fragment_without_a_single_root_is_wrapped(self):
        tree = parse("a.txt\nb.txt\n")
        self.assertEqual(tree.name, "")
        self.assertEqual([c.name for c in tree.children], ["a.txt", "b.txt"])

    def test_truncation_markers_are_dropped(self):
        tree = parse("root/\n├── a/\n│   └── ...\n└── b.txt\n")
        self.assertEqual([c.name for c in tree.children], ["a", "b.txt"])
        self.assertEqual(tree.children[0].children, [])

    def test_ascii_tree_parses(self):
        tree = parse("root/\n|-- a/\n|   `-- x.txt\n`-- b.txt\n")
        self.assertEqual([c.name for c in tree.children], ["a", "b.txt"])
        self.assertEqual([c.name for c in tree.children[0].children], ["x.txt"])

    def test_two_space_indentation_is_accepted(self):
        tree = parse("root/\n  src/\n    main.py\n  README.md\n", "indented")
        self.assertEqual([c.name for c in tree.children], ["src", "README.md"])
        self.assertEqual([c.name for c in tree.children[0].children], ["main.py"])

    def test_blank_lines_are_ignored(self):
        tree = parse("root/\n\n├── a.txt\n\n└── b.txt\n")
        self.assertEqual([c.name for c in tree.children], ["a.txt", "b.txt"])

    def test_empty_input_raises(self):
        from foltree.parse import ParseError

        with self.assertRaises(ParseError):
            parse("   \n\n")


if __name__ == "__main__":
    unittest.main()
