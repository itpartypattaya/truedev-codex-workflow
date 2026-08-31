from __future__ import annotations

import hashlib
import importlib.util
from pathlib import Path
import tempfile
import unittest
import zipfile


ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseTests(unittest.TestCase):
    def test_release_contract(self) -> None:
        validator = load_script("validate_release")
        manifest = validator.validate()
        self.assertEqual(manifest["version"], "1.0.0")

    def test_package_is_deterministic_and_minimal(self) -> None:
        package_module = load_script("package_plugin")
        with tempfile.TemporaryDirectory() as temp:
            first = Path(temp) / "first.zip"
            second = Path(temp) / "second.zip"
            package_module.build(first)
            package_module.build(second)
            self.assertEqual(hashlib.sha256(first.read_bytes()).digest(), hashlib.sha256(second.read_bytes()).digest())
            with zipfile.ZipFile(first) as archive:
                names = set(archive.namelist())
            self.assertIn(".codex-plugin/plugin.json", names)
            self.assertIn("hooks/hooks.json", names)
            self.assertIn("skills/lifecycle/SKILL.md", names)
            self.assertIn("skills/project-init/SKILL.md", names)
            self.assertFalse(any(name.startswith((".git/", ".agents/", "docs/", "tests/", "evals/")) for name in names))
            self.assertFalse(any(name.endswith((".pyc", ".zip")) for name in names))


if __name__ == "__main__":
    unittest.main()
