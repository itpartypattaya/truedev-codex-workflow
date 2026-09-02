"""Ninth round: home boundary, next-slice, detection, project config, entry phase."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import truedev_workflow as workflow  # noqa: E402
from test_audit_round_5 import WorkflowFixture  # noqa: E402

RUNNER = ROOT / "scripts" / "truedev_workflow.py"


def write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


class HomeBoundaryTests(WorkflowFixture):
    def test_stale_state_above_home_cannot_gate_unrelated_directories(self) -> None:
        home = self.base / "home"
        victim = home / "projects" / "notes"
        victim.mkdir(parents=True)
        (home / workflow.STATE_DIR).mkdir()
        write(home / workflow.STATE_DIR / "lifecycle.json", "{}")
        with mock.patch.object(workflow, "_home_boundary", return_value=home.resolve()):
            self.assertIsNone(workflow.find_repo_root(victim))
            self.assertIsNone(workflow.find_repo_root(home))

    def test_lost_git_metadata_below_home_is_still_recovered(self) -> None:
        home = self.base / "home"
        project = home / "proj"
        project.mkdir(parents=True)
        (project / workflow.STATE_DIR).mkdir()
        with mock.patch.object(workflow, "_home_boundary", return_value=home.resolve()):
            self.assertEqual(workflow.find_repo_root(project / "src"), project)


class NextSliceTests(WorkflowFixture):
    def plan(self, **slices: tuple[str, str]) -> None:
        for name, (status, depends) in slices.items():
            write(
                self.root / "docs" / "plan" / f"{name}.md",
                f"# {name}\n\nStatus: {status}\nDepends on: {depends}\n",
            )

    def test_picks_the_lowest_pending_slice_whose_dependencies_are_done(self) -> None:
        self.plan(
            **{
                "slice-001-base": ("completed", "none"),
                "slice-002-api": ("pending", "slice-001"),
                "slice-003-ui": ("pending", "slice-002"),
            }
        )
        code, output, error = self.cli("project-init", "next-slice")
        self.assertEqual(code, 0, error)
        result = json.loads(output)
        self.assertEqual(result["next"]["id"], "slice-002")
        self.assertEqual(result["next"]["path"], "docs/plan/slice-002-api.md")
        self.assertEqual(result["blocked"], [
            {"id": "slice-003", "file": "slice-003-ui.md", "waiting_on": ["slice-002"]}
        ])

    def test_reports_why_nothing_can_start(self) -> None:
        self.plan(**{"slice-001-a": ("completed", "none"), "slice-002-b": ("completed", "slice-001")})
        code, output, _ = self.cli("project-init", "next-slice")
        self.assertEqual(code, 2)
        self.assertIn("every slice is completed", json.loads(output)["reason"])

        self.plan(**{"slice-003-c": ("in progress", "none")})
        code, output, _ = self.cli("project-init", "next-slice")
        self.assertEqual(code, 2)
        result = json.loads(output)
        self.assertEqual(result["unrecognized_status"], [{"id": "slice-003", "status": "in progress"}])
        self.assertIn("does not recognize", result["reason"])

    def test_structural_problems_block_selection(self) -> None:
        self.plan(**{"slice-001-a": ("pending", "slice-009")})
        code, output, _ = self.cli("project-init", "next-slice")
        self.assertEqual(code, 2)
        self.assertIn("missing dependency slice-009", json.loads(output)["problems"][0])

    def test_validate_slices_still_reports_the_same_shape(self) -> None:
        self.plan(**{"slice-001-a": ("pending", "none")})
        code, output, _ = self.cli("project-init", "validate-slices")
        self.assertEqual(code, 0)
        result = json.loads(output)
        self.assertTrue(result["ok"])
        self.assertEqual(result["slices"]["slice-001"]["status"], "pending")


class DetectTests(WorkflowFixture):
    def test_node_project_reports_only_scripts_that_exist(self) -> None:
        write(self.root / "package.json", json.dumps({
            "scripts": {"build": "tsc", "test": "vitest run"},
            "dependencies": {"react": "^18"},
            "devDependencies": {"grammy": "^1"},
        }))
        write(self.root / "pnpm-lock.yaml", "")
        result = workflow.detect_project(self.root)
        self.assertEqual(result["stack"], "node")
        self.assertEqual(result["package_manager"], "pnpm")
        self.assertEqual(result["commands"], {
            "build": "pnpm run build", "lint": None, "test": "pnpm run test", "e2e": None,
        })
        self.assertTrue(result["has_ui"])
        self.assertEqual(result["domain"], "telegram-bot")
        self.assertIsNone(result["test_setup"], "a project with tests gets no offer")

    def test_python_project_offers_a_runner_when_it_has_none(self) -> None:
        write(self.root / "pyproject.toml", "[tool.ruff]\nline-length = 100\n")
        write(self.root / "requirements.txt", "aiogram==3\n")
        result = workflow.detect_project(self.root)
        self.assertEqual(result["stack"], "python")
        self.assertEqual(result["commands"]["lint"], "ruff check .")
        self.assertIsNone(result["commands"]["test"])
        self.assertEqual(result["test_setup"]["runner"], "pytest")
        self.assertEqual(result["test_setup"]["integration"], "telethon")

    def test_makefile_fills_gaps_and_go_is_fixed(self) -> None:
        write(self.root / "go.mod", "module example\n")
        write(self.root / "Makefile", "e2e:\n\t@echo e2e\n")
        result = workflow.detect_project(self.root)
        self.assertEqual(result["commands"]["test"], "go test ./...")
        self.assertEqual(result["commands"]["e2e"], "make e2e")

    def test_existing_documents_choose_the_entry_phase(self) -> None:
        self.assertEqual(workflow.detect_project(self.root)["suggested_entry_phase"], "INPUT_VALIDATION")
        write(self.root / "docs" / "REQUIREMENTS.md", "# R\n")
        self.assertEqual(workflow.detect_project(self.root)["suggested_entry_phase"], "PRD")
        write(self.root / "docs" / "architecture.md", "# A\n")
        self.assertEqual(workflow.detect_project(self.root)["suggested_entry_phase"], "PLANNING")
        write(self.root / "docs" / "plan" / "phase-1.md", "# P\n")
        self.assertEqual(workflow.detect_project(self.root)["suggested_entry_phase"], "DECOMPOSITION")

    def test_plan_candidates_are_bounded_and_native_wins(self) -> None:
        write(self.root / "ROADMAP.md", "x")
        write(self.root / "docs" / "tasks" / "todo.md", "x")
        result = workflow.detect_project(self.root)
        self.assertFalse(result["plan"]["native"])
        self.assertEqual(sorted(result["plan"]["candidates"]), ["ROADMAP.md", "docs/tasks/todo.md"])
        write(self.root / "docs" / "plan" / "slice-001-a.md", "Status: pending\nDepends on: none\n")
        result = workflow.detect_project(self.root)
        self.assertTrue(result["plan"]["native"])
        self.assertEqual(result["plan"]["candidates"], [])

    def test_detect_never_fails_on_an_empty_repository(self) -> None:
        code, output, error = self.cli("detect")
        self.assertEqual(code, 0, error)
        result = json.loads(output)
        self.assertEqual(result["stack"], "unknown")
        self.assertFalse(result["project_config"])


class ProjectConfigTests(WorkflowFixture):
    def test_init_requires_confirmation_and_writes_a_validated_file(self) -> None:
        code, _, error = self.cli("project-config", "init", "--test", "pytest")
        self.assertEqual(code, 2)
        self.assertIn("--user-confirmed", error)

        code, _, error = self.cli(
            "project-config", "init", "--test", "pytest", "--lint", "ruff check .",
            "--plan-dir", "docs/plan", "--test-setup", "accepted:pytest", "--user-confirmed",
        )
        self.assertEqual(code, 0, error)
        value = workflow.load_project_config(self.root)
        self.assertEqual(value["commands"], {"build": None, "lint": "ruff check .", "test": "pytest", "e2e": None})
        self.assertEqual(value["plan_dir"], "docs/plan")

        code, _, error = self.cli("project-config", "init", "--test", "x", "--user-confirmed")
        self.assertEqual(code, 2)
        self.assertIn("--overwrite", error)

    def test_config_rejects_shell_control_and_traversal(self) -> None:
        for args, needle in (
            (("--test", "pytest && rm -rf /"), "shell control"),
            (("--plan-dir", "../outside"), "safe components"),
            (("--test-setup", "maybe"), "test_setup must be"),
        ):
            with self.subTest(args=args):
                code, _, error = self.cli("project-config", "init", *args, "--user-confirmed")
                self.assertEqual(code, 2)
                self.assertIn(needle, error)

    def test_show_reports_absence_with_a_problem_code(self) -> None:
        code, output, _ = self.cli("project-config", "show")
        self.assertEqual(code, 2)
        self.assertFalse(json.loads(output)["present"])

    def test_plan_directory_comes_from_the_project_file_when_no_flag_is_given(self) -> None:
        write(
            self.root / "planning" / "slice-001-base.md",
            "# slice-001-base\n\nStatus: pending\nDepends on: none\n",
        )
        code, output, _ = self.cli("project-init", "next-slice")
        self.assertEqual(code, 2, output)

        code, _, error = self.cli(
            "project-config", "init", "--plan-dir", "planning", "--user-confirmed"
        )
        self.assertEqual(code, 0, error)
        code, output, error = self.cli("project-init", "next-slice")
        self.assertEqual(code, 0, error)
        result = json.loads(output)
        self.assertEqual(result["plan_dir"], "planning")
        self.assertEqual(result["next"]["id"], "slice-001")
        self.assertEqual(result["next"]["path"], "planning/slice-001-base.md")

        code, output, error = self.cli("project-init", "validate-slices")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["plan_dir"], "planning")

        write(
            self.root / 'docs' / 'plan' / 'slice-009-other.md',
            '# slice-009-other' + chr(10) * 2 + 'Status: pending' + chr(10) + 'Depends on: none' + chr(10),
        )
        code, output, error = self.cli('project-init', 'next-slice', '--plan-dir', 'docs/plan')
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)['plan_dir'], 'docs/plan')
        self.assertEqual(json.loads(output)['next']['id'], 'slice-009')

    def test_a_hand_written_config_may_omit_the_timestamp(self) -> None:
        write(
            self.root / workflow.PROJECT_CONFIG_FILE,
            json.dumps(
                {"commands": {"build": None, "lint": None, "test": "pytest", "e2e": None}}
            )
            + "\n",
        )
        value = workflow.load_project_config(self.root)
        self.assertEqual(value["commands"]["test"], "pytest")
        self.assertIsNone(value.get("adopted_at"))

    def test_an_accepted_runner_must_name_something(self) -> None:
        code, _, error = self.cli(
            "project-config", "init", "--test-setup", "accepted:", "--user-confirmed"
        )
        self.assertEqual(code, 2)
        self.assertIn("test_setup must be", error)

    def test_config_file_is_not_treated_as_a_secret(self) -> None:
        self.assertFalse(workflow.is_sensitive_path(workflow.PROJECT_CONFIG_FILE))

    def test_read_only_commands_are_allowed_at_an_open_gate(self) -> None:
        self.open_gate(self.root)
        for tail in ("detect", "project-config show", "project-init next-slice --plan-dir docs/plan"):
            with self.subTest(tail=tail):
                _, output = self.hook("pre-tool", {
                    "cwd": str(self.root), "tool_name": "Bash",
                    "tool_input": {"command": 'python "%s" %s' % (RUNNER, tail)},
                })
                self.assertEqual(output.strip(), "", tail)
        _, output = self.hook("pre-tool", {
            "cwd": str(self.root), "tool_name": "Bash",
            "tool_input": {"command": 'python "%s" project-config init --test x --user-confirmed' % RUNNER},
        })
        self.assertNotEqual(output.strip(), "", "a config write must stay gated")


class EntryPhaseTests(WorkflowFixture):
    def test_entering_later_requires_confirmation_and_records_adoption(self) -> None:
        code, _, error = self.cli(
            "project-init", "start", "--project", "p", "--spec", "s", "--from", "ARCHITECTURE"
        )
        self.assertEqual(code, 2)
        self.assertIn("--user-confirmed", error)

        code, output, error = self.cli(
            "project-init", "start", "--project", "p", "--spec", "s",
            "--from", "ARCHITECTURE", "--user-confirmed",
        )
        self.assertEqual(code, 0, error)
        self.assertIn("adopted as pre-existing: INPUT_VALIDATION, PRD", output)
        state = workflow.load_state(self.root, "project-init")
        self.assertEqual(state["current_phase"], "ARCHITECTURE")
        for phase in ("INPUT_VALIDATION", "PRD"):
            self.assertEqual(state["steps"][phase]["outcome"], "pre_existing")
            self.assertIsNone(state["steps"][phase]["approved_at"])
        adoptions = [h for h in state["history"] if h["action"] == "adopt"]
        self.assertEqual([h["name"] for h in adoptions], ["INPUT_VALIDATION", "PRD"])
        self.assertTrue(all(h["actor"] == "user-explicit" for h in adoptions))

        code, output, _ = self.cli("project-init", "status")
        self.assertEqual(code, 0)
        self.assertIn("> ARCHITECTURE", output)

    def test_adopted_run_still_completes_and_archives(self) -> None:
        self.cli("project-init", "start", "--project", "p", "--spec", "s",
                 "--from", "DECOMPOSITION", "--user-confirmed")
        self.assertEqual(self.cli("project-init", "gate", "--phase", "DECOMPOSITION")[0], 0)
        self.assertEqual(
            self.cli("project-init", "approve", "--phase", "DECOMPOSITION", "--user-confirmed")[0], 0
        )
        self.assertEqual(self.cli("project-init", "finish", "--phase", "FINALIZE")[0], 0)
        code, _, error = self.cli("project-init", "archive")
        self.assertEqual(code, 0, error)

    def test_schema_rejects_misuse_of_pre_existing(self) -> None:
        self.cli("project-init", "start", "--project", "p", "--spec", "s",
                 "--from", "PRD", "--user-confirmed")
        state = workflow.load_state(self.root, "project-init")

        broken = json.loads(json.dumps(state))
        broken["steps"]["INPUT_VALIDATION"]["outcome"] = None
        broken["steps"]["INPUT_VALIDATION"]["approved_at"] = workflow.utc_now()
        with self.assertRaisesRegex(workflow.WorkflowError, "adoption receipt without"):
            workflow.validate_state(broken, "project-init")

        broken = json.loads(json.dumps(state))
        broken["history"] = [h for h in broken["history"] if h["action"] != "adopt"]
        with self.assertRaisesRegex(workflow.WorkflowError, "lacks exactly one adoption receipt"):
            workflow.validate_state(broken, "project-init")

        self.cli("lifecycle", "start", "--task", "x", "--base", "main")
        lifecycle = workflow.load_state(self.root, "lifecycle")
        lifecycle["steps"]["CONTEXT_CHECK"]["status"] = "completed"
        lifecycle["steps"]["CONTEXT_CHECK"]["outcome"] = "pre_existing"
        lifecycle["current_step"] = "SCOPE"
        lifecycle["steps"]["SCOPE"]["status"] = "in_progress"
        with self.assertRaisesRegex(workflow.WorkflowError, "cannot be recorded as pre-existing"):
            workflow.validate_state(lifecycle, "lifecycle")

    def test_finalize_cannot_be_an_entry_phase(self) -> None:
        with self.assertRaises(SystemExit):
            self.cli("project-init", "start", "--project", "p", "--spec", "s",
                     "--from", "FINALIZE", "--user-confirmed")


if __name__ == "__main__":
    unittest.main()
