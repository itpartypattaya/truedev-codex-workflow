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


class AdoptionDialogueTests(WorkflowFixture):
    def test_each_layer_is_its_own_recorded_answer(self) -> None:
        code, _, error = self.cli(
            "project-config", "init",
            "--test-setup", "accepted:vitest",
            "--e2e-setup", "declined:once",
            "--integration-test", "accepted:telethon",
            "--user-confirmed",
        )
        self.assertEqual(code, 0, error)
        value = workflow.load_project_config(self.root)
        self.assertEqual(value["test_setup"], "accepted:vitest")
        self.assertEqual(value["e2e_setup"], "declined:once")
        self.assertEqual(value["integration_test"], "accepted:telethon")

    def test_silence_records_nothing(self) -> None:
        code, _, error = self.cli("project-config", "init", "--user-confirmed")
        self.assertEqual(code, 0, error)
        value = workflow.load_project_config(self.root)
        for field in workflow.SETUP_FIELDS:
            with self.subTest(field=field):
                self.assertIsNone(value[field], "absent is not declined")

    def test_every_layer_shares_one_grammar(self) -> None:
        for flag in ("--test-setup", "--e2e-setup", "--integration-test"):
            for bad in ("maybe", "accepted:", "accepted:   "):
                with self.subTest(flag=flag, value=bad):
                    code, _, error = self.cli(
                        "project-config", "init", flag, bad, "--user-confirmed"
                    )
                    self.assertEqual(code, 2)
                    self.assertIn("must be", error)

    def test_adopted_from_only_accepts_the_documented_marker(self) -> None:
        code, _, error = self.cli(
            "project-config", "init", "--adopted-from", "empty", "--user-confirmed"
        )
        self.assertEqual(code, 0, error)
        self.assertEqual(workflow.load_project_config(self.root)["adopted_from"], "empty")

        write(
            self.root / workflow.PROJECT_CONFIG_FILE,
            '{"commands": {"build": null, "lint": null, "test": null, "e2e": null},'
            ' "adopted_from": "somewhere"}\n',
        )
        with self.assertRaises(workflow.WorkflowError):
            workflow.load_project_config(self.root)

    def test_an_empty_repository_is_marked_for_a_second_pass(self) -> None:
        self.assertEqual(workflow.detect_project(self.root)["adopted_from_hint"], "empty")

        write(self.root / "go.mod", "module example.invalid/x\n\ngo 1.22\n")
        result = workflow.detect_project(self.root)
        self.assertIsNone(result["adopted_from_hint"], "a manifest ends the empty case")
        self.assertEqual(result["stack"], "go")

    def test_a_config_written_before_this_release_still_loads(self) -> None:
        write(
            self.root / workflow.PROJECT_CONFIG_FILE,
            '{"commands": {"build": null, "lint": null, "test": "pytest", "e2e": null},'
            ' "test_setup": "declined:always"}\n',
        )
        value = workflow.load_project_config(self.root)
        self.assertEqual(value["test_setup"], "declined:always")
        self.assertIsNone(value.get("e2e_setup"))


class AdoptionDocumentationTests(unittest.TestCase):
    def test_the_dialogue_names_every_field_it_records(self) -> None:
        text = (
            ROOT / "skills" / "lifecycle" / "references" / "project-config.md"
        ).read_text(encoding="utf-8")
        dialogue = text.split("## The adoption dialogue", 1)
        self.assertEqual(len(dialogue), 2, "the dialogue section must exist")
        for needle in ("accepted:", "declined:once", "declined:always", "adopted_from_hint"):
            with self.subTest(needle=needle):
                self.assertIn(needle, dialogue[1])
        self.assertIn("Silence is not a decline", dialogue[1])
        self.assertIn("Never install anything during adoption", dialogue[1])

    def test_the_test_step_installs_an_accepted_layer(self) -> None:
        text = (ROOT / "skills" / "lifecycle" / "references" / "steps.md").read_text(
            encoding="utf-8"
        )
        test_section = text.split("## TEST", 1)[1].split("## VERIFY", 1)[0]
        for field in ("test_setup", "e2e_setup", "integration_test"):
            with self.subTest(field=field):
                self.assertIn(field, test_section)
        self.assertIn("credentials in the environment", test_section)


class SecondOpinionTests(WorkflowFixture):
    def test_a_reviewer_is_recorded_per_slot(self) -> None:
        code, _, error = self.cli(
            "project-config", "init",
            "--second-opinion-scope", "toxic-opinion",
            "--user-confirmed",
        )
        self.assertEqual(code, 0, error)
        value = workflow.load_project_config(self.root)
        self.assertEqual(value["second_opinion"]["scope"], "toxic-opinion")
        self.assertIsNone(value["second_opinion"]["review"], "an unset slot is not configured")

    def test_the_object_shape_is_fixed(self) -> None:
        write(
            self.root / workflow.PROJECT_CONFIG_FILE,
            '{"commands": {"build": null, "lint": null, "test": null, "e2e": null},'
            ' "second_opinion": {"scope": "x"}}\n',
        )
        with self.assertRaises(workflow.WorkflowError) as raised:
            workflow.load_project_config(self.root)
        self.assertIn("second_opinion must contain exactly", str(raised.exception))

    def test_a_reviewer_cannot_smuggle_a_shell_operator(self) -> None:
        code, _, error = self.cli(
            "project-config", "init",
            "--second-opinion-review", "reviewer && rm -rf /",
            "--user-confirmed",
        )
        self.assertEqual(code, 2)
        self.assertIn("shell control", error)

    def test_an_absent_layer_is_still_a_valid_config(self) -> None:
        code, _, error = self.cli("project-config", "init", "--user-confirmed")
        self.assertEqual(code, 0, error)
        value = workflow.load_project_config(self.root)
        self.assertEqual(
            value["second_opinion"], {"scope": None, "review": None}
        )


class SecondOpinionDocumentationTests(unittest.TestCase):
    def read(self, *parts: str) -> str:
        return (ROOT.joinpath(*parts)).read_text(encoding="utf-8")

    def test_both_gates_run_the_reviewer_before_the_gate_opens(self) -> None:
        steps = self.read("skills", "lifecycle", "references", "steps.md")
        scope = steps.split("## SCOPE", 1)[1].split("## PLAN", 1)[0]
        review = steps.split("## REVIEW", 1)[1].split("## DOCUMENT", 1)[0]
        for name, section in (("SCOPE", scope), ("REVIEW", review)):
            with self.subTest(section=name):
                self.assertIn("second_opinion", section)
                self.assertIn("not configured", section)
                self.assertIn("before `gate`", section)

    def test_an_unconfigured_layer_must_be_reported(self) -> None:
        config = self.read("skills", "lifecycle", "references", "project-config.md")
        self.assertIn("second opinion: not configured", config)
        self.assertIn("never taken rather than", config)

    def test_project_init_asks_once(self) -> None:
        phases = self.read("skills", "project-init", "references", "phases.md")
        intro = phases.split("## INPUT_VALIDATION", 1)[0]
        self.assertIn("Second opinion:", intro)
        self.assertIn("without asking\nagain", intro)

    def test_the_eval_suite_covers_the_absent_layer(self) -> None:
        import json

        data = json.loads(self.read("evals", "plugin", "evals.json"))
        case = [
            item for item in data["evals"] if item["id"] == "positive-lifecycle-second-opinion"
        ]
        self.assertEqual(len(case), 1)
        joined = " ".join(case[0]["assertions"]).lower()
        self.assertIn("second opinion", joined)
        self.assertIn("not configured", joined)


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
