"""Round 10: one command vocabulary, and a status that names the next action."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import truedev_workflow as workflow  # noqa: E402
from test_audit_round_5 import WorkflowFixture  # noqa: E402

RUNNER = ROOT / "scripts" / "truedev_workflow.py"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class CommandAliasTests(WorkflowFixture):
    def start_lifecycle(self) -> None:
        write(
            self.root / "docs" / "plan" / "slice-001-base.md",
            "# slice-001-base\n\nStatus: pending\nDepends on: none\n",
        )
        code, _, error = self.cli(
            "lifecycle", "start", "--task", "t",
            "--slice", "docs/plan/slice-001-base.md", "--base", "main",
        )
        self.assertEqual(code, 0, error)

    def test_complete_is_approve_and_records_the_same_receipt(self) -> None:
        self.start_lifecycle()
        code, _, error = self.cli("lifecycle", "finish", "--step", "CONTEXT_CHECK")
        self.assertEqual(code, 0, error)
        code, _, error = self.cli("lifecycle", "gate", "--step", "SCOPE")
        self.assertEqual(code, 0, error)
        code, _, error = self.cli(
            "lifecycle", "complete", "--step", "SCOPE", "--user-confirmed"
        )
        self.assertEqual(code, 0, error)

        state = json.loads(
            (self.root / ".truedev-workflow" / "lifecycle.json").read_text(encoding="utf-8")
        )
        self.assertEqual(state["steps"]["SCOPE"]["status"], "completed")
        approvals = [
            entry
            for entry in state["history"]
            if entry["action"] == "approve" and entry["name"] == "SCOPE"
        ]
        self.assertEqual(len(approvals), 1)
        self.assertEqual(approvals[0]["actor"], "user-explicit")

    def test_complete_still_requires_the_confirmation_flag(self) -> None:
        self.start_lifecycle()
        self.cli("lifecycle", "finish", "--step", "CONTEXT_CHECK")
        self.cli("lifecycle", "gate", "--step", "SCOPE")
        code, _, error = self.cli("lifecycle", "complete", "--step", "SCOPE")
        self.assertEqual(code, 2)
        self.assertIn("--user-confirmed", error)

    def test_skip_compact_is_release_compact(self) -> None:
        self.start_lifecycle()
        for step in ("CONTEXT_CHECK",):
            self.cli("lifecycle", "finish", "--step", step)
        self.cli("lifecycle", "gate", "--step", "SCOPE")
        self.cli("lifecycle", "complete", "--step", "SCOPE", "--user-confirmed")
        code, _, error = self.cli("lifecycle", "finish", "--step", "PLAN")
        self.assertEqual(code, 0, error)

        code, output, error = self.cli("lifecycle", "skip-compact", "--user-confirmed")
        self.assertEqual(code, 0, error)
        state = json.loads(
            (self.root / ".truedev-workflow" / "lifecycle.json").read_text(encoding="utf-8")
        )
        self.assertFalse(state["awaiting_compact"])
        receipts = [
            entry for entry in state["history"] if entry["action"] == "release-compact"
        ]
        self.assertEqual(len(receipts), 1, "one receipt, whichever spelling was typed")

    def test_project_init_complete_is_approve(self) -> None:
        code, _, error = self.cli("project-init", "start", "--project", "p", "--spec", "s")
        self.assertEqual(code, 0, error)
        self.cli("project-init", "gate", "--phase", "INPUT_VALIDATION")
        code, _, error = self.cli(
            "project-init", "complete", "--phase", "INPUT_VALIDATION", "--user-confirmed"
        )
        self.assertEqual(code, 0, error)
        state = json.loads(
            (self.root / ".truedev-workflow" / "project-init.json").read_text(encoding="utf-8")
        )
        self.assertEqual(state["steps"]["INPUT_VALIDATION"]["status"], "completed")

    def test_both_spellings_pass_the_gate_allowlist(self) -> None:
        self.open_gate(self.root)
        allowed = (
            "lifecycle approve --step SCOPE --user-confirmed",
            "lifecycle complete --step SCOPE --user-confirmed",
            "project-init complete --phase PRD --user-confirmed",
            "lifecycle release-compact --user-confirmed",
            "lifecycle skip-compact --user-confirmed",
        )
        for tail in allowed:
            with self.subTest(tail=tail):
                _, output = self.hook("pre-tool", {
                    "cwd": str(self.root), "tool_name": "Bash",
                    "tool_input": {"command": 'python "%s" %s' % (RUNNER, tail)},
                })
                self.assertEqual(output.strip(), "", tail)

    def test_a_confirmation_flag_is_still_required_by_the_allowlist(self) -> None:
        self.open_gate(self.root)
        for tail in ("lifecycle complete --step SCOPE", "lifecycle skip-compact"):
            with self.subTest(tail=tail):
                _, output = self.hook("pre-tool", {
                    "cwd": str(self.root), "tool_name": "Bash",
                    "tool_input": {"command": 'python "%s" %s' % (RUNNER, tail)},
                })
                self.assertNotEqual(output.strip(), "", tail)


class NextActionTests(WorkflowFixture):
    def status_fields(self, workflow_name: str = "lifecycle") -> dict[str, str]:
        code, output, error = self.cli(workflow_name, "status")
        self.assertEqual(code, 0, error)
        fields = {}
        for line in output.splitlines():
            if ": " in line and not line.startswith((" ", ">")):
                key, _, value = line.partition(": ")
                fields[key] = value
        return fields

    def start_lifecycle(self) -> None:
        write(
            self.root / "docs" / "plan" / "slice-001-base.md",
            "# slice-001-base\n\nStatus: pending\nDepends on: none\n",
        )
        code, _, error = self.cli(
            "lifecycle", "start", "--task", "t",
            "--slice", "docs/plan/slice-001-base.md", "--base", "main",
        )
        self.assertEqual(code, 0, error)

    def test_an_automatic_step_asks_to_be_finished(self) -> None:
        self.start_lifecycle()
        fields = self.status_fields()
        self.assertEqual(fields["open_gate"], "none")
        self.assertIn("finish CONTEXT_CHECK", fields["next_action"])

    def test_a_user_gate_asks_for_evidence_then_for_approval(self) -> None:
        self.start_lifecycle()
        self.cli("lifecycle", "finish", "--step", "CONTEXT_CHECK")
        fields = self.status_fields()
        self.assertEqual(fields["open_gate"], "none")
        self.assertIn("gate SCOPE", fields["next_action"])

        self.cli("lifecycle", "gate", "--step", "SCOPE")
        fields = self.status_fields()
        self.assertEqual(fields["open_gate"], "SCOPE")
        self.assertIn("complete SCOPE --user-confirmed", fields["next_action"])

    def test_the_compact_checkpoint_outranks_the_step_table(self) -> None:
        self.start_lifecycle()
        self.cli("lifecycle", "finish", "--step", "CONTEXT_CHECK")
        self.cli("lifecycle", "gate", "--step", "SCOPE")
        self.cli("lifecycle", "complete", "--step", "SCOPE", "--user-confirmed")
        self.cli("lifecycle", "finish", "--step", "PLAN")

        fields = self.status_fields()
        self.assertIn("compact", fields["next_action"])
        self.assertNotIn("compact_released", fields)

        self.cli("lifecycle", "skip-compact", "--user-confirmed")
        fields = self.status_fields()
        self.assertIn("compact_released", fields, "a deliberate bypass stays visible")
        # The checkpoint guards the step it blocks, which is the one after PLAN.
        self.assertTrue(
            fields["compact_released"].startswith("before COMPONENTS at "),
            fields["compact_released"],
        )
        self.assertNotIn("compact", fields["next_action"])

    def test_a_gate_is_marked_in_the_table(self) -> None:
        self.start_lifecycle()
        code, output, _ = self.cli("lifecycle", "status")
        self.assertEqual(code, 0)
        self.assertIn("[GATE]", output)
        self.assertNotIn("user-gate", output)

    def test_status_without_a_workflow_says_so(self) -> None:
        code, output, _ = self.cli("lifecycle", "status")
        self.assertEqual(code, 0)
        self.assertIn("No active lifecycle workflow", output)

    def test_project_init_status_names_its_next_action(self) -> None:
        code, _, error = self.cli("project-init", "start", "--project", "p", "--spec", "s")
        self.assertEqual(code, 0, error)
        fields = self.status_fields("project-init")
        self.assertEqual(fields["open_gate"], "none")
        self.assertIn("gate INPUT_VALIDATION", fields["next_action"])


class CommandDocumentationTests(unittest.TestCase):
    def test_every_documented_command_exists_in_the_runner(self) -> None:
        text = (ROOT / "skills" / "lifecycle" / "SKILL.md").read_text(encoding="utf-8")
        table = text.split("## Commands", 1)[1].split("## Transition commands", 1)[0]
        documented = set()
        for line in table.splitlines():
            if not line.startswith("| `"):
                continue
            command = line.split("`")[1].split()
            if command[0] in {"lifecycle", "project-init"} and len(command) > 1:
                documented.add((command[0], command[1]))
            elif command[0] in {"detect"}:
                documented.add((command[0],))
        self.assertIn(("lifecycle", "complete"), documented)
        self.assertIn(("lifecycle", "skip-compact"), documented)

        parser = workflow.build_parser()
        for command in sorted(documented):
            with self.subTest(command=command):
                args = list(command) + ["--help"]
                with self.assertRaises(SystemExit) as raised:
                    parser.parse_args(args)
                self.assertEqual(raised.exception.code, 0, command)

    def test_the_suggested_prompts_use_the_documented_vocabulary(self) -> None:
        manifest = json.loads(
            (ROOT / ".codex-plugin" / "plugin.json").read_text(encoding="utf-8")
        )
        prompts = manifest["interface"]["defaultPrompt"]
        self.assertTrue(all(isinstance(prompt, str) and prompt for prompt in prompts))
        joined = " ".join(prompts)
        self.assertIn("$lifecycle", joined)
        self.assertIn("$project-init", joined)

    def test_the_old_spelling_is_gone_from_user_facing_text(self) -> None:
        for name in ("README.md", "README.ru.md"):
            with self.subTest(name=name):
                text = (ROOT / name).read_text(encoding="utf-8")
                body = text.split("## Commands", 1)[1] if "## Commands" in text else text
                self.assertNotIn("release-compact --user-confirmed`\n", body.split("`approve`")[0])


if __name__ == "__main__":
    unittest.main()
