from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
DECOY = "import pathlib\npathlib.Path('decoy-was-executed').write_text('x')\n"


def _python3_is_usable() -> bool:
    """`python3` on PATH can be a stub (for example the Windows Store alias)."""
    executable = shutil.which("python3")
    if executable is None:
        return False
    try:
        probe = subprocess.run([executable, "-c", "pass"], capture_output=True, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return probe.returncode == 0


def plant_decoy(directory: Path) -> Path:
    """Create the file an empty PLUGIN_ROOT would resolve to from the session cwd."""
    script = directory / "scripts" / "truedev_workflow.py"
    script.parent.mkdir(parents=True, exist_ok=True)
    script.write_text(DECOY, encoding="utf-8")
    return directory / "decoy-was-executed"


class PluginLayoutTests(unittest.TestCase):
    def test_manifest_is_codex_native(self) -> None:
        manifest = json.loads((ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["name"], "truedev-workflow")
        self.assertEqual(manifest["skills"], "./skills/")
        self.assertNotIn("hooks", manifest)  # default hooks/hooks.json discovery
        legacy_plugin_dir = ROOT / (".cl" + "aude-plugin")
        self.assertFalse((legacy_plugin_dir / "plugin.json").exists())
        interface = manifest["interface"]
        self.assertLessEqual(len(interface["shortDescription"]), 30)
        self.assertNotIn("screenshots", interface)
        for field in ("composerIcon", "logo", "logoDark"):
            self.assertTrue((ROOT / interface[field][2:]).is_file())

    def test_hook_config_uses_codex_events_and_cross_platform_commands(self) -> None:
        config = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        hooks = config["hooks"]
        self.assertEqual(set(hooks), {"SessionStart", "PreToolUse", "Stop"})
        matcher = hooks["PreToolUse"][0]["matcher"]
        for tool in ("Bash", "apply_patch", "Agent", "mcp__example__write"):
            self.assertRegex(tool, re.compile(matcher))
        for event in hooks.values():
            for group in event:
                for handler in group["hooks"]:
                    self.assertTrue(handler["command"].startswith('python3 -c "'))
                    self.assertTrue(handler["commandWindows"].startswith('python -c "'))
                    for launcher in (handler["command"], handler["commandWindows"]):
                        self.assertIn("os.environ.get('PLUGIN_ROOT','')", launcher)
                        # An empty or relative PLUGIN_ROOT must never resolve against the
                        # session working directory, which is the repository under review.
                        self.assertIn("os.path.isabs(p) and os.path.isfile(p) else 0", launcher)
                        self.assertNotIn("$env:", launcher)
                        self.assertNotIn("%PLUGIN_ROOT%", launcher)
                        self.assertNotIn("$PLUGIN_ROOT", launcher)

    def test_hook_launcher_never_executes_a_repository_script(self) -> None:
        """An unusable PLUGIN_ROOT must be inert, not resolve against the session cwd."""
        config = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        handler = config["hooks"]["PreToolUse"][0]["hooks"][0]
        payload = json.dumps(
            {"cwd": str(ROOT), "tool_name": "Bash", "tool_input": {"command": "echo hi"}}
        )
        for launcher in (handler["command"], handler["commandWindows"]):
            body = shlex.split(launcher, posix=True)[2]
            for label, plugin_root in (
                ("unset", None),
                ("empty", ""),
                ("relative", "."),
                ("relative-nested", os.path.join(".", "nested")),
            ):
                with self.subTest(launcher=launcher.split()[0], plugin_root=label):
                    with tempfile.TemporaryDirectory() as temp_dir:
                        temp = Path(temp_dir)
                        marker = plant_decoy(temp)
                        env = os.environ.copy()
                        env.pop("PLUGIN_ROOT", None)
                        if plugin_root is not None:
                            env["PLUGIN_ROOT"] = plugin_root
                        result = subprocess.run(
                            [sys.executable, "-c", body],
                            cwd=temp,
                            env=env,
                            input=payload,
                            capture_output=True,
                            text=True,
                            encoding="utf-8",
                            timeout=30,
                        )
                        self.assertEqual(result.returncode, 0, result.stderr)
                        self.assertEqual(result.stdout, "")
                        self.assertFalse(marker.exists(), "hook executed a repository script")

    def test_hook_launcher_runs_the_installed_runner_in_every_shell(self) -> None:
        config = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
        handler = config["hooks"]["PreToolUse"][0]["hooks"][0]
        payload = json.dumps(
            {"cwd": str(ROOT), "tool_name": "Bash", "tool_input": {"command": "echo hi"}}
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            temp = Path(temp_dir)
            marker = plant_decoy(temp)
            shells: list[tuple[str, list[str]]] = []
            if os.name == "nt":
                command_file = temp / "hook.cmd"
                powershell_file = temp / "hook.ps1"
                command_file.write_text("@echo off\r\n" + handler["commandWindows"] + "\r\n")
                powershell_file.write_text(handler["commandWindows"] + "\n", encoding="utf-8")
                shells.append(("cmd", ["cmd.exe", "/d", "/c", str(command_file)]))
                if shutil.which("powershell.exe"):
                    shells.append(
                        (
                            "powershell",
                            [
                                "powershell.exe",
                                "-NoProfile",
                                "-ExecutionPolicy",
                                "Bypass",
                                "-File",
                                str(powershell_file),
                            ],
                        )
                    )
            posix_shell = shutil.which("sh")
            if posix_shell and _python3_is_usable():
                shells.append(("sh", [posix_shell, "-c", handler["command"]]))
            if not shells:
                self.skipTest("no supported command shell available")
            env = os.environ.copy()
            env["PLUGIN_ROOT"] = str(ROOT)
            for name, shell in shells:
                with self.subTest(shell=name):
                    result = subprocess.run(
                        shell,
                        cwd=temp,
                        env=env,
                        input=payload,
                        capture_output=True,
                        text=True,
                        encoding="utf-8",
                        timeout=30,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertFalse(marker.exists(), "hook executed a repository script")

    def test_skills_have_matching_names_and_stay_under_500_lines(self) -> None:
        for name in ("lifecycle", "project-init"):
            skill = ROOT / "skills" / name / "SKILL.md"
            text = skill.read_text(encoding="utf-8")
            frontmatter = text.split("---", 2)[1]
            self.assertIn(f"name: {name}", frontmatter)
            self.assertNotIn("compatibility:", frontmatter)
            self.assertLess(len(text.splitlines()), 500)
            openai_yaml = (skill.parent / "agents" / "openai.yaml").read_text(encoding="utf-8")
            self.assertIn(f"${name}", openai_yaml)
            self.assertIn('icon_small: "./assets/icon.svg"', openai_yaml)
            self.assertIn('icon_large: "./assets/logo.svg"', openai_yaml)
            self.assertTrue((skill.parent / "assets" / "icon.svg").is_file())
            self.assertTrue((skill.parent / "assets" / "logo.svg").is_file())

    def test_internal_eval_files_exist(self) -> None:
        for name in ("lifecycle", "project-init"):
            skill_root = ROOT / "skills" / name
            data = json.loads((skill_root / "evals" / "evals.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(data["evals"]), 5)
            for item in data["evals"]:
                for relative in item["files"]:
                    self.assertTrue((skill_root / relative).is_file(), f"missing eval file: {relative}")

    def test_review_requires_acceptance_evidence_matrix(self) -> None:
        steps = (ROOT / "skills" / "lifecycle" / "references" / "steps.md").read_text(encoding="utf-8")
        self.assertIn("| Criterion | Evidence | Gap |", steps)
        self.assertIn("Map every approved acceptance criterion", steps)
        self.assertIn("do not treat the matrix itself as evidence", steps)

    def test_marketplace_points_to_root_plugin(self) -> None:
        marketplace = json.loads(
            (ROOT / ".agents" / "plugins" / "marketplace.json").read_text(encoding="utf-8")
        )
        entry = marketplace["plugins"][0]
        self.assertEqual(entry["name"], "truedev-workflow")
        self.assertEqual(entry["source"]["source"], "local")
        self.assertEqual(entry["source"]["path"], "./")
        self.assertEqual(entry["policy"]["installation"], "AVAILABLE")
        self.assertEqual(entry["policy"]["authentication"], "ON_INSTALL")
        self.assertEqual(entry["policy"]["products"], ["CODEX"])

    def test_ci_dependencies_are_immutably_pinned(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
        action_refs = re.findall(r"uses:\s*[^@\s]+@([^\s#]+)", workflow)
        self.assertTrue(action_refs)
        self.assertTrue(all(re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs))
        requirements = (ROOT / "requirements-ci.txt").read_text(encoding="utf-8")
        self.assertIn("ruff==0.15.16", requirements)
        self.assertGreaterEqual(requirements.count("--hash=sha256:"), 4)
        self.assertIn("--require-hashes", workflow)


if __name__ == "__main__":
    unittest.main()
