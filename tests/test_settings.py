import json
import os
import shutil
import tempfile
import unittest

from foltree import settings


class TestSettings(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="foltree-settings-")
        self.addCleanup(shutil.rmtree, self.dir, True)
        previous = os.environ.get("FOLTREE_CONFIG_DIR")
        os.environ["FOLTREE_CONFIG_DIR"] = self.dir
        self.addCleanup(
            lambda: os.environ.__setitem__("FOLTREE_CONFIG_DIR", previous)
            if previous is not None else os.environ.pop("FOLTREE_CONFIG_DIR", None)
        )

    def test_defaults_when_there_is_no_file(self):
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_save_then_load(self):
        data = settings.load()
        data.update(format="Markdown", sizes=True, last_folder="/somewhere")
        settings.save(data)
        loaded = settings.load()
        self.assertEqual(loaded["format"], "Markdown")
        self.assertTrue(loaded["sizes"])
        self.assertEqual(loaded["last_folder"], "/somewhere")

    def test_corrupt_file_falls_back_to_defaults(self):
        with open(settings.settings_path(), "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertEqual(settings.load(), settings.DEFAULTS)

    def test_values_of_the_wrong_type_are_ignored(self):
        with open(settings.settings_path(), "w", encoding="utf-8") as handle:
            json.dump({"sizes": "yes", "format": 3, "depth": "2", "unknown": 1}, handle)
        loaded = settings.load()
        self.assertFalse(loaded["sizes"])
        self.assertEqual(loaded["format"], "Tree")
        self.assertEqual(loaded["depth"], "2")
        self.assertNotIn("unknown", loaded)

    def test_save_into_a_missing_folder_creates_it(self):
        nested = os.path.join(self.dir, "a", "b")
        os.environ["FOLTREE_CONFIG_DIR"] = nested
        settings.save(settings.load())
        self.assertTrue(os.path.isfile(os.path.join(nested, "settings.json")))


if __name__ == "__main__":
    unittest.main()
