from __future__ import annotations

import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]


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
                    self.assertIn("$PLUGIN_ROOT", handler["command"])
                    self.assertIn("%PLUGIN_ROOT%", handler["commandWindows"])
                    self.assertTrue(handler["commandWindows"].startswith("python "))

    def test_skills_have_matching_names_and_stay_under_500_lines(self) -> None:
        for name in ("lifecycle", "project-init"):
            skill = ROOT / "skills" / name / "SKILL.md"
            text = skill.read_text(encoding="utf-8")
            self.assertIn(f"name: {name}", text.split("---", 2)[1])
            self.assertLess(len(text.splitlines()), 500)

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


if __name__ == "__main__":
    unittest.main()
