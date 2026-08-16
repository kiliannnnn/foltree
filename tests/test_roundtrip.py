import unittest

from foltree.node import Node
from foltree.parse import detect_format, parse
from foltree.render import FORMATS, render, resolve_format

TEXT_FORMATS = ["indented", "tree", "clean", "ascii", "markdown", "json", "yaml"]

#: Formats whose rendered output auto-detects as something else, because they
#: share a shape with another format. Parsing is identical, so this is fine.
DETECTS_AS = {"clean": "tree", "ascii": "tree"}


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
                self.assertEqual(detect_format(text), DETECTS_AS.get(fmt, fmt))
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


class TestCleanTree(unittest.TestCase):
    def test_clean_tree_has_connectors_but_no_guide_bars(self):
        text = render(sample_tree(), "clean")
        self.assertIn("├── ", text)
        self.assertIn("└── ", text)
        self.assertNotIn("│", text)

    def test_clean_tree_is_distinct_from_tree(self):
        original = sample_tree()
        self.assertNotEqual(render(original, "clean"), render(original, "tree"))

    def test_clean_tree_round_trips_despite_missing_guides(self):
        # Depth comes from the connector's column, not from the guide glyphs,
        # so dropping the bars costs nothing structurally.
        original = sample_tree()
        self.assertEqual(parse(render(original, "clean"), "clean"), original)

    def test_legacy_clean_tree_names_resolve(self):
        for name in ("clean", "Clean Tree", "clean tree", "cleantree", "CLEAN"):
            with self.subTest(name=name):
                self.assertEqual(resolve_format(name), "clean")


class TestTrailingSlash(unittest.TestCase):
    SLASHED = ["indented", "tree", "clean", "ascii", "markdown", "yaml"]

    def test_directories_lose_the_slash_when_disabled(self):
        for fmt in self.SLASHED:
            with self.subTest(format=fmt):
                text = render(sample_tree(), fmt, dir_suffix=False)
                self.assertNotIn("src/", text)
                self.assertIn("src", text)

    def test_json_is_unaffected_and_still_lossless(self):
        original = sample_tree()
        self.assertEqual(render(original, "json", dir_suffix=False),
                         render(original, "json", dir_suffix=True))
        self.assertEqual(parse(render(original, "json", dir_suffix=False), "json"), original)

    def test_named_folders_survive_without_the_slash(self):
        # Folders that still have children are detected from the nesting.
        original = sample_tree()
        for fmt in self.SLASHED:
            with self.subTest(format=fmt):
                rebuilt = parse(render(original, fmt, dir_suffix=False), fmt)
                src = next(c for c in rebuilt.children if c.name == "src")
                self.assertTrue(src.is_dir)

    def test_empty_folder_is_the_documented_casualty(self):
        # This is the cost of turning the slash off: `assets` is empty, so
        # nothing in the text distinguishes it from an extensionless file and
        # the bare_names setting decides.
        text = render(sample_tree(), "tree", dir_suffix=False)
        as_folder = parse(text, "tree", bare_names="folder")
        as_file = parse(text, "tree", bare_names="file")
        self.assertTrue(next(c for c in as_folder.children if c.name == "assets").is_dir)
        self.assertFalse(next(c for c in as_file.children if c.name == "assets").is_dir)

    def test_slash_on_is_immune_to_the_bare_names_setting(self):
        # With the slash present there is no ambiguity left to resolve.
        text = render(sample_tree(), "tree", dir_suffix=True)
        self.assertEqual(parse(text, "tree", bare_names="folder"),
                         parse(text, "tree", bare_names="file"))


class TestBareNames(unittest.TestCase):
    def test_default_reads_bare_names_as_folders(self):
        tree = parse("p/\n├── assets\n└── components\n")
        self.assertTrue(all(c.is_dir for c in tree.children))

    def test_file_policy_reads_them_as_files(self):
        tree = parse("p/\n├── assets\n└── components\n", bare_names="file")
        self.assertFalse(any(c.is_dir for c in tree.children))

    def test_stronger_evidence_beats_the_policy(self):
        tree = parse(
            "p/\n├── src/\n│   └── main.py\n├── .github\n├── LICENSE\n└── notes.txt\n",
            bare_names="file",
        )
        by_name = {c.name: c for c in tree.children}
        self.assertTrue(by_name["src"].is_dir, "a trailing slash is decisive")
        self.assertTrue(by_name[".github"].is_dir, "a known directory name is decisive")
        self.assertFalse(by_name["LICENSE"].is_dir)
        self.assertFalse(by_name["notes.txt"].is_dir)

    def test_children_still_force_a_directory(self):
        tree = parse("p/\n└── weird\n    └── inside.txt\n", bare_names="file")
        self.assertTrue(tree.children[0].is_dir)

    def test_invalid_policy_is_rejected(self):
        with self.assertRaises(ValueError):
            parse("p/\n└── a\n", bare_names="whatever")


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
