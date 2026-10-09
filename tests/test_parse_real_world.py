"""Structures as people actually paste them: from chat answers, the `tree`
command, Windows, `find`, `git ls-files`, hand-written READMEs."""

import unittest

from foltree.node import Node
from foltree.parse import ParseError, detect_format, parse
from foltree.render import render


def names(tree):
    """`render(tree)` without the guides: one `path` per entry, dirs with `/`."""
    out = []

    def walk(node, prefix):
        for child in node.children:
            path = prefix + child.name + ("/" if child.is_dir else "")
            out.append(path)
            if child.is_dir:
                walk(child, prefix + child.name + "/")

    walk(tree, (tree.name + "/") if tree.name else "")
    return out


class TestRealWorldInput(unittest.TestCase):
    def test_trailing_comments_are_dropped(self):
        tree = parse(
            "app/\n"
            "├── src/\n"
            "│   ├── index.ts        # entry point\n"
            "│   └── utils/          // helpers\n"
            "├── package.json  <- deps\n"
            "└── README.md      ← docs\n"
        )
        self.assertEqual(names(tree), [
            "app/src/", "app/src/index.ts", "app/src/utils/", "app/package.json", "app/README.md",
        ])

    def test_hash_inside_a_name_is_kept(self):
        tree = parse("notes/\n├── C#/\n└── issue#12.md\n")
        self.assertEqual(names(tree), ["notes/C#/", "notes/issue#12.md"])

    def test_short_connectors_and_three_wide_guides(self):
        tree = parse("p/\n├─ src/\n│  ├─ main.rs\n│  └─ lib/\n│     └─ a.rs\n└─ Cargo.toml\n")
        self.assertEqual(names(tree), [
            "p/src/", "p/src/main.rs", "p/src/lib/", "p/src/lib/a.rs", "p/Cargo.toml",
        ])

    def test_only_the_code_block_of_a_chat_answer_is_read(self):
        text = (
            "Sure! Here's a structure for your shop:\n\n"
            "```text\nshop/\n├── api/\n│   └── main.py\n└── web/\n    └── index.html\n```\n\n"
            "Let me know if you need anything else.\n"
        )
        self.assertEqual(names(parse(text)), [
            "shop/api/", "shop/api/main.py", "shop/web/", "shop/web/index.html",
        ])

    def test_gnu_tree_output_with_footer_and_nbsp(self):
        text = (
            "project\n├── src\n│\u00a0\u00a0 ├── a.py\n│\u00a0\u00a0 └── b\n"
            "│\u00a0\u00a0     └── c.py\n└── setup.py\n\n2 directories, 3 files\n"
        )
        self.assertEqual(names(parse(text)), [
            "project/src/", "project/src/a.py", "project/src/b/", "project/src/b/c.py",
            "project/setup.py",
        ])

    def test_windows_tree_f_output(self):
        text = (
            "Folder PATH listing\nVolume serial number is 1234-ABCD\nC:.\n"
            "│   a.txt\n│\n├───src\n│   │   main.c\n│   │\n│   └───util\n"
            "│           u.c\n│\n└───docs\n        d.md\n"
        )
        self.assertEqual(names(parse(text)), [
            "a.txt", "src/", "src/main.c", "src/util/", "src/util/u.c", "docs/", "docs/d.md",
        ])

    def test_windows_tree_a_output(self):
        text = "C:.\n+---src\n|   \\---util\n\\---docs\n"
        self.assertEqual(names(parse(text)), ["src/", "src/util/", "docs/"])

    def test_spacer_lines_made_of_guides_are_ignored(self):
        tree = parse("app/\n│\n├── src/\n│   └── x.py\n│\n└── y.txt\n")
        self.assertEqual(names(tree), ["app/src/", "app/src/x.py", "app/y.txt"])

    def test_folder_emoji_marks_a_directory(self):
        tree = parse("📁 app\n├── 📁 lib\n└── 📄 main.ts\n")
        self.assertEqual(names(tree), ["app/lib/", "app/main.ts"])

    def test_names_starting_with_plus_survive(self):
        tree = parse("routes/\n├── +page.svelte\n└── +layout.ts\n")
        self.assertEqual(names(tree), ["routes/+page.svelte", "routes/+layout.ts"])

    def test_markdown_and_yaml_comments(self):
        self.assertEqual(
            names(parse("- src/\n  - index.js  # main\n- package.json\n")),
            ["src/", "src/index.js", "package.json"],
        )
        self.assertEqual(
            names(parse("app/:\n  - main.py  # entry\n  - 'odd # name.txt'\n")),
            ["app/main.py", "app/odd # name.txt"],
        )


class TestPathLists(unittest.TestCase):
    def test_git_ls_files_output(self):
        text = "README.md\nsrc/index.ts\nsrc/utils/math.ts\n"
        self.assertEqual(detect_format(text), "paths")
        self.assertEqual(names(parse(text)), [
            "README.md", "src/", "src/index.ts", "src/utils/", "src/utils/math.ts",
        ])

    def test_find_output(self):
        text = ".\n./src\n./src/a.py\n./empty\n"
        self.assertEqual(names(parse(text)), ["src/", "src/a.py", "empty/"])

    def test_windows_backslash_paths(self):
        self.assertEqual(names(parse("src\\main.c\nsrc\\lib\\u.c\n")),
                         ["src/main.c", "src/lib/", "src/lib/u.c"])

    def test_a_flat_file_list_is_not_mistaken_for_paths(self):
        self.assertEqual(detect_format("a.txt\nb.txt\n"), "indented")


class TestFragmentsAndErrors(unittest.TestCase):
    FORMATS = ["indented", "tree", "ascii", "markdown", "json", "yaml", "paths"]

    def fragment(self):
        root = Node("", is_dir=True)
        root.add(Node("a.py"))
        root.add(Node("lib", is_dir=True)).add(Node("b.py"))
        root.add(Node("README.md"))
        return root

    def test_fragments_render_without_a_fake_root_line(self):
        text = render(self.fragment(), "tree")
        self.assertTrue(text.startswith("├── a.py"), text)

    def test_fragments_round_trip_in_every_format(self):
        for fmt in self.FORMATS:
            with self.subTest(format=fmt):
                self.assertEqual(parse(render(self.fragment(), fmt), "auto"), self.fragment())

    def test_parsed_folders_show_counts_but_no_made_up_size(self):
        text = render(parse("app/\n├── a.py\n└── b.py\n"), "tree", stats=True)
        self.assertEqual(text.splitlines()[0], "app/ (2 files)")

    def test_malformed_json_entries_raise_parse_error(self):
        for text in ("[1, 2]", '[{"type": "dir"}]', '{"children": []}'):
            with self.subTest(text=text):
                with self.assertRaises(ParseError):
                    parse(text)

    def test_only_a_fence_is_nothing_to_parse(self):
        with self.assertRaises(ParseError):
            parse("```\n```\n")


if __name__ == "__main__":
    unittest.main()
