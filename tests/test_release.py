from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
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


def load_eval_script(name: str):
    path = ROOT / "evals" / f"{name}.py"
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
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
        self.assertEqual(manifest["version"], "1.1.11")

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
            self.assertFalse(any("/evals/" in name for name in names))
            self.assertFalse(any(name.endswith((".pyc", ".zip")) for name in names))

    def test_default_package_name_tracks_manifest_version(self) -> None:
        package_module = load_script("package_plugin")
        self.assertEqual(package_module.default_output("9.8.7").name, "truedev-workflow-9.8.7.zip")

    def test_eval_selection_filters_before_limit(self) -> None:
        runner = load_eval_script("run_release_evals")
        items = [{"id": f"eval-{index}"} for index in range(5)]
        self.assertEqual(runner.select_evals(items, "eval-4", 2), [{"id": "eval-4"}])
        with self.assertRaisesRegex(ValueError, "unknown --eval-id"):
            runner.select_evals(items, "missing", 2)

    def test_eval_fixture_contains_runnable_go_surface(self) -> None:
        runner = load_eval_script("run_release_evals")
        with tempfile.TemporaryDirectory() as temp:
            fixture = runner.prepare_fixture(Path(temp))
            self.assertTrue((fixture / "go.mod").is_file())
            self.assertTrue((fixture / "src" / "billing.go").is_file())
            self.assertTrue((fixture / "src" / "billing.py").is_file())

    def test_empty_metrics_fail_with_a_controlled_error(self) -> None:
        grader = load_eval_script("grade_release_evals")
        with self.assertRaisesRegex(RuntimeError, "without completed runs"):
            grader.metric([])

    def test_eval_rerun_cannot_accept_a_stale_response(self) -> None:
        runner = load_eval_script("run_release_evals")
        item = {"id": "stale-output", "prompt": "fixture", "assertions": []}
        with tempfile.TemporaryDirectory() as temp:
            workspace = Path(temp) / "workspace"
            fixture = Path(temp) / "fixture"
            fixture.mkdir()
            response = workspace / item["id"] / "with_skill" / "outputs" / "response.md"
            response.parent.mkdir(parents=True)
            response.write_text("old response\n", encoding="utf-8")
            completed = runner.subprocess.CompletedProcess(["codex"], 0, stdout="", stderr="")
            def create_empty_output(*_args, **_kwargs):
                response.write_text("", encoding="utf-8")
                return completed

            with mock.patch.object(runner, "codex_command", return_value=["codex"]), mock.patch.object(
                runner.subprocess, "run", side_effect=create_empty_output
            ):
                with self.assertRaises(RuntimeError):
                    runner.run_one(item, "with_skill", fixture, workspace)
            self.assertFalse(response.exists())
            timing = json.loads((response.parents[1] / "timing.json").read_text(encoding="utf-8"))
            self.assertFalse(timing["completed"])
            self.assertFalse(timing["output_valid"])
            self.assertFalse(runner.completed_run(workspace, item["id"], "with_skill"))


if __name__ == "__main__":
    unittest.main()
