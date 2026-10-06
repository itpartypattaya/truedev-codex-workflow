"""Gate integrity: the runner refuses to approve evidence that moved while a gate was open.

This is the check that still holds in the directory edition, which bundles no hooks,
and it also catches changes made through paths that never emit a hook event.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import truedev_workflow as workflow  # noqa: E402
from test_audit_round_5 import WorkflowFixture, git  # noqa: E402


class GateIntegrityTests(WorkflowFixture):
    def open_scope_gate(self) -> str:
        code, _, error = self.cli("lifecycle", "start", "--task", "t", "--base", "main")
        self.assertEqual(code, 0, error)
        code, _, error = self.cli("lifecycle", "finish", "--step", "CONTEXT_CHECK")
        self.assertEqual(code, 0, error)
        code, output, error = self.cli("lifecycle", "gate", "--step", "SCOPE")
        self.assertEqual(code, 0, error)
        return output

    def state(self) -> dict:
        state = workflow.load_state(self.root, "lifecycle")
        self.assertIsNotNone(state)
        return state

    def approve(self, *extra: str) -> tuple[int, str, str]:
        return self.cli("lifecycle", "approve", "--step", "SCOPE", "--user-confirmed", *extra)

    def test_untouched_tree_approves_and_clears_the_snapshot(self) -> None:
        output = self.open_scope_gate()
        self.assertIn("snapshot recorded", output)
        snapshot = self.state()["integrity"]
        self.assertEqual(snapshot["step"], "SCOPE")
        self.assertRegex(snapshot["tree"], r"^[0-9a-f]{40}$")
        _, status, _ = self.cli("lifecycle", "status")
        self.assertIn("integrity: intact since the gate opened", status)
        code, output, error = self.approve()
        self.assertEqual(code, 0, error)
        self.assertIn("integrity: intact", output)
        state = self.state()
        self.assertNotIn("integrity", state)
        self.assertEqual(state["steps"]["SCOPE"]["status"], "completed")

    def test_tracked_edit_during_gate_refuses_approval_until_the_user_accepts_it(self) -> None:
        self.open_scope_gate()
        (self.root / "README.md").write_text("changed while the gate was open\n", encoding="utf-8")
        _, status, _ = self.cli("lifecycle", "status")
        self.assertIn("integrity: CHANGED since the gate opened (1: README.md)", status)

        code, _, error = self.approve()
        self.assertEqual(code, 2)
        self.assertIn("changed while its gate was open", error)
        self.assertIn("README.md", error)
        self.assertEqual(self.state()["steps"]["SCOPE"]["status"], "awaiting_approval")

        code, output, error = self.approve("--accept-changes")
        self.assertEqual(code, 0, error)
        self.assertIn("accepted by the user", output)
        actions = [(entry["action"], entry["actor"]) for entry in self.state()["history"]]
        self.assertIn(("accept-changes", "user-explicit"), actions)
        self.assertLess(actions.index(("accept-changes", "user-explicit")), actions.index(("approve", "user-explicit")))

    def test_new_untracked_file_is_a_change(self) -> None:
        self.open_scope_gate()
        (self.root / "src").mkdir()
        (self.root / "src" / "new.py").write_text("print('x')\n", encoding="utf-8")
        code, _, error = self.approve()
        self.assertEqual(code, 2)
        self.assertIn("src/new.py", error)

    def test_ignored_files_are_outside_the_fingerprint(self) -> None:
        self.open_scope_gate()
        (self.root / ".truedev-workflow" / "scratch.txt").write_text("ignored\n", encoding="utf-8")
        code, _, error = self.approve()
        self.assertEqual(code, 0, error)

    def test_a_commit_during_the_gate_is_a_change(self) -> None:
        self.open_scope_gate()
        git(self.root, "commit", "--allow-empty", "-m", "sneaky")
        code, _, error = self.approve()
        self.assertEqual(code, 2)
        self.assertIn("HEAD moved", error)

    def test_index_trust_flags_do_not_hide_an_edit(self) -> None:
        # A copied index keeps these bits; without clearing them `git add -A` skips
        # the edited path and the gate reports intact evidence that has changed.
        for flag in ("--assume-unchanged", "--skip-worktree"):
            with self.subTest(flag=flag):
                self.tearDown()
                self.setUp()
                git(self.root, "update-index", flag, "README.md")
                self.open_scope_gate()
                (self.root / "README.md").write_text("edited behind the flag\n", encoding="utf-8")
                code, _, error = self.approve()
                self.assertEqual(code, 2, f"{flag} hid the edit")
                self.assertIn("README.md", error)
                listed = git(self.root, "ls-files", "-v", "README.md").stdout
                self.assertEqual(listed[:1], "h" if flag == "--assume-unchanged" else "S")

    def test_ignore_stat_config_does_not_hide_an_edit(self) -> None:
        git(self.root, "config", "core.ignoreStat", "true")
        self.open_scope_gate()
        (self.root / "README.md").write_text("edited under ignoreStat\n", encoding="utf-8")
        code, _, error = self.approve()
        self.assertEqual(code, 2)
        self.assertIn("README.md", error)

    def test_fingerprint_leaves_the_real_index_untouched(self) -> None:
        (self.root / "staged.txt").write_text("staged\n", encoding="utf-8")
        git(self.root, "add", "staged.txt")
        (self.root / "unstaged.txt").write_text("unstaged\n", encoding="utf-8")
        before = git(self.root, "status", "--porcelain=v1").stdout
        result = workflow.working_tree_fingerprint(self.root)
        self.assertRegex(result["tree"], r"^[0-9a-f]{40}$")
        self.assertEqual(git(self.root, "status", "--porcelain=v1").stdout, before)

    def test_unavailable_fingerprint_is_recorded_not_read_as_clean(self) -> None:
        broken = {"head": None, "tree": None, "error": "simulated failure"}
        with mock.patch.object(workflow, "working_tree_fingerprint", return_value=broken):
            output = self.open_scope_gate()
            self.assertIn("integrity: unavailable (simulated failure)", output)
            _, status, _ = self.cli("lifecycle", "status")
            self.assertIn("integrity: unavailable (simulated failure)", status)
            code, output, error = self.approve()
        self.assertEqual(code, 0, error)
        self.assertIn("not checked", output)
        actions = [entry["action"] for entry in self.state()["history"]]
        self.assertIn("integrity-unchecked", actions)

    def test_gate_opened_by_an_earlier_version_still_approves(self) -> None:
        self.open_scope_gate()
        path = workflow.state_path(self.root, "lifecycle")
        state = json.loads(path.read_text(encoding="utf-8"))
        del state["integrity"]
        path.write_text(json.dumps(state), encoding="utf-8")
        code, output, error = self.approve()
        self.assertEqual(code, 0, error)
        self.assertIn("not checked (this gate was opened without a snapshot)", output)

    def test_snapshot_must_belong_to_the_open_gate(self) -> None:
        self.open_scope_gate()
        state = self.state()
        state["integrity"]["step"] = "PLAN"
        with self.assertRaises(workflow.WorkflowError):
            workflow.validate_state(state, "lifecycle")
        state = self.state()
        state["integrity"]["extra"] = True
        with self.assertRaises(workflow.WorkflowError):
            workflow.validate_state(state, "lifecycle")

    def test_project_init_gates_are_checked_too(self) -> None:
        (self.root / "spec.md").write_text("# spec\n", encoding="utf-8")
        git(self.root, "add", "spec.md")
        git(self.root, "commit", "-m", "spec")
        code, _, error = self.cli("project-init", "start", "--project", "p", "--spec", "spec.md")
        self.assertEqual(code, 0, error)
        code, _, error = self.cli("project-init", "gate", "--phase", "INPUT_VALIDATION")
        self.assertEqual(code, 0, error)
        (self.root / "spec.md").write_text("# edited spec\n", encoding="utf-8")
        code, _, error = self.cli(
            "project-init", "approve", "--phase", "INPUT_VALIDATION", "--user-confirmed"
        )
        self.assertEqual(code, 2)
        self.assertIn("spec.md", error)


class EditionTests(WorkflowFixture):
    def test_repository_runner_ships_beside_its_hooks(self) -> None:
        self.assertTrue(workflow.hooks_bundled())

    def test_status_names_the_enforcement_actually_installed(self) -> None:
        self.cli("lifecycle", "start", "--task", "t", "--base", "main")
        _, status, _ = self.cli("lifecycle", "status")
        self.assertIn("enforcement: hooks + integrity check", status)
        with mock.patch.object(workflow, "hooks_bundled", return_value=False):
            _, status, _ = self.cli("lifecycle", "status")
        self.assertIn("enforcement: integrity check (this edition bundles no hooks)", status)

    def test_compact_checkpoint_is_the_normal_path_without_hooks(self) -> None:
        self.cli("lifecycle", "start", "--task", "t", "--base", "main")
        self.cli("lifecycle", "finish", "--step", "CONTEXT_CHECK")
        self.cli("lifecycle", "gate", "--step", "SCOPE")
        self.cli("lifecycle", "approve", "--step", "SCOPE", "--user-confirmed")
        self.cli("lifecycle", "finish", "--step", "PLAN")
        with mock.patch.object(workflow, "hooks_bundled", return_value=False):
            _, status, _ = self.cli("lifecycle", "status")
            self.assertIn(
                "next_action: ask the user to compact the session, then skip-compact --user-confirmed",
                status,
            )
            code, _, error = self.cli("lifecycle", "gate", "--step", "COMPONENTS")
            self.assertEqual(code, 2)
            self.assertIn("ask the user to compact", error)
            code, _, error = self.cli("lifecycle", "skip-compact", "--user-confirmed")
            self.assertEqual(code, 0, error)
            code, _, error = self.cli("lifecycle", "gate", "--step", "COMPONENTS")
            self.assertEqual(code, 0, error)

    def test_hook_allowlist_lets_an_accepted_approval_through(self) -> None:
        for command in (
            "python3 scripts/truedev_workflow.py lifecycle approve --step SCOPE --user-confirmed --accept-changes",
            "python3 scripts/truedev_workflow.py lifecycle complete --step SCOPE --accept-changes --user-confirmed",
            "python scripts/truedev_workflow.py project-init complete --phase PRD --user-confirmed --accept-changes",
        ):
            self.assertIsNotNone(workflow.SAFE_RUNNER_COMMAND.fullmatch(command), command)
        self.assertIsNone(
            workflow.SAFE_RUNNER_COMMAND.fullmatch(
                "python3 scripts/truedev_workflow.py lifecycle approve --step SCOPE --accept-changes"
            )
        )


if __name__ == "__main__":
    unittest.main()
