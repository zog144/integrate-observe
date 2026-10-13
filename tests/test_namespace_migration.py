import importlib.util
from pathlib import Path
import unittest

import zog.integrate_observe
from zog.integrate_observe.cli import main


class NamespaceMigrationTests(unittest.TestCase):
    def test_canonical_namespace_and_entry_point(self):
        self.assertEqual(zog.integrate_observe.__version__, "0.4.2")
        self.assertTrue(callable(main))
        legacy = "integrate_" + "observe"
        self.assertIsNone(importlib.util.find_spec(legacy))

    def test_component_does_not_own_top_level_zog_initializer(self):
        root = Path(__file__).resolve().parents[1]
        self.assertFalse((root / "src" / "zog" / "__init__.py").exists())
        self.assertTrue((root / "src" / "zog" / "integrate_observe" / "__init__.py").is_file())

    def test_no_stale_absolute_module_paths(self):
        root = Path(__file__).resolve().parents[1]
        component = "integrate_" + "observe"
        trace = "build_" + "trace"
        needles = [
            "from " + component + " import",
            "import " + component,
            "from " + trace + " import",
            "import " + trace,
            "python -m " + component,
            "python3 -m " + component,
            'integrate-observe = "' + component + ".",
            "integrate-observe = '" + component + ".",
            'import_module("' + component,
            "import_module('" + component,
            'import_module("' + trace,
            "import_module('" + trace,
            'patch("' + component,
            "patch('" + component,
            'patch("' + trace,
            "patch('" + trace,
        ]
        suffixes = {".py", ".toml", ".yml", ".yaml", ".md", ".json", ".ini", ".cfg", ".service"}
        excluded = {Path(__file__).resolve()}
        stale = []
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix not in suffixes or path.resolve() in excluded:
                continue
            if any(part in {".git", "build", "dist", ".venv"} or part.endswith(".egg-info")
                   for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8")
            for needle in needles:
                if needle in text:
                    stale.append((str(path.relative_to(root)), needle))
        self.assertEqual(stale, [])


if __name__ == "__main__":
    unittest.main()
