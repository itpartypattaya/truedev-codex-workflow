"""Regressions for the fifth review round: links, sibling checkouts, output safety."""

from __future__ import annotations

from contextlib import contextmanager, redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import truedev_workflow as workflow  # noqa: E402

RUNNER = ROOT / "scripts" / "truedev_workflow.py"
EMOJI = "\U0001f600"


@contextmanager
def pushd(path: Path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def make_link(link: Path, target: Path) -> bool:
    """Directory link that does not need elevation: junction on Windows, symlink elsewhere."""
    if os.name == "nt":
        return subprocess.run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            capture_output=True,
        ).returncode == 0
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        return False
    return True


class WorkflowFixture(unittest.TestCase):
    """Shared fixture; holds no tests of its own."""

    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.root = self.make_repo("repo")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def make_repo(self, name: str) -> Path:
        root = self.base / name
        root.mkdir(parents=True, exist_ok=True)
        git(root, "init", "-b", "main")
        git(root, "config", "user.email", "test@example.invalid")
        git(root, "config", "user.name", "TrueDev Test")
        (root / "README.md").write_text("fixture\n", encoding="utf-8")
        (root / ".gitignore").write_text(".truedev-workflow/\n", encoding="utf-8")
        git(root, "add", "README.md", ".gitignore")
        git(root, "commit", "-m", "fixture")
        return root

    def cli(self, *args: str, cwd: Path | None = None) -> tuple[int, str, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        with pushd(cwd or self.root), redirect_stdout(stdout), redirect_stderr(stderr):
            result = workflow.main(list(args))
        return result, stdout.getvalue(), stderr.getvalue()

    def hook(self, kind: str, payload: dict) -> tuple[int, str]:
        stdout, stderr = io.StringIO(), io.StringIO()
        old_stdin = sys.stdin
        try:
            sys.stdin = io.StringIO(json.dumps(payload))
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = {
                    "pre-tool": workflow.hook_pre_tool,
                    "stop": workflow.hook_stop,
                }[kind]()
        finally:
            sys.stdin = old_stdin
        return result, stdout.getvalue()

    def mutation_verdict(self, cwd: Path) -> str:
        code, output = self.hook(
            "pre-tool",
            {"cwd": str(cwd), "tool_name": "Bash", "tool_input": {"command": "rm -rf README.md"}},
        )
        return "DENY" if output.strip() else "ALLOW"

    def open_gate(self, root: Path) -> None:
        self.assertEqual(
            self.cli("lifecycle", "start", "--task", "gate", "--base", "main", cwd=root)[0], 0
        )
        self.cli("lifecycle", "finish", "--step", "CONTEXT_CHECK", cwd=root)
        self.cli("lifecycle", "gate", "--step", "SCOPE", cwd=root)


class AuditRoundFiveTests(WorkflowFixture):
    """Fifth review round: links, sibling checkouts, output safety."""

    # 1. state directory redirected by a link or junction
    def test_linked_state_directory_is_refused_for_reads_and_writes(self) -> None:
        self.cli("lifecycle", "start", "--task", "x", "--base", "main")
        state_dir = self.root / workflow.STATE_DIR
        outside = self.base / "elsewhere"
        state_dir.rename(outside)
        if not make_link(state_dir, outside):
            self.skipTest("directory links are unavailable in this environment")
        code, _, error = self.cli("lifecycle", "status")
        self.assertEqual(code, 2)
        self.assertIn("links or junctions", error)
        code, _, error = self.cli("lifecycle", "finish", "--step", "CONTEXT_CHECK")
        self.assertEqual(code, 2)
        self.assertEqual(self.mutation_verdict(self.root), "DENY")

    # 7. a linked .git must not be accepted as a repository marker
    def test_linked_git_marker_is_not_a_valid_repository_root(self) -> None:
        victim = self.base / "victim"
        victim.mkdir()
        if not make_link(victim / ".git", self.root / ".git"):
            self.skipTest("directory links are unavailable in this environment")
        self.assertFalse(workflow._has_valid_git_marker(victim))

    # 2. sibling and enclosing checkouts
    def test_open_gate_covers_a_linked_worktree(self) -> None:
        self.open_gate(self.root)
        linked = self.base / "linked"
        git(self.root, "worktree", "add", str(linked), "-b", "feature")
        self.assertEqual(self.mutation_verdict(self.root), "DENY")
        self.assertEqual(self.mutation_verdict(linked), "DENY")

    def test_open_gate_covers_a_nested_checkout(self) -> None:
        nested = self.root / "vendor" / "dep"
        nested.parent.mkdir(parents=True)
        self.make_repo(str(Path("repo") / "vendor" / "dep"))
        self.open_gate(self.root)
        self.assertEqual(workflow.find_repo_root(nested), nested)
        self.assertEqual(self.mutation_verdict(nested), "DENY")

    def test_unrelated_repository_is_not_affected_by_an_open_gate(self) -> None:
        self.open_gate(self.root)
        other = self.make_repo("unrelated")
        self.assertEqual(self.mutation_verdict(other), "ALLOW")

    def test_single_checkout_does_not_spawn_git_for_worktree_discovery(self) -> None:
        self.assertFalse(workflow._may_have_linked_worktrees(self.root))
        self.assertEqual(workflow.related_roots(self.root), [])

    # 3. output must survive characters outside the console code page
    def test_emitters_survive_a_narrow_output_encoding(self) -> None:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "cp1252"
        self.cli("lifecycle", "start", "--task", "release", "--base", "main")
        git(self.root, "checkout", "-q", "-b", "feature-" + EMOJI)
        git(self.root, "checkout", "-q", "main")
        (self.root / (EMOJI + ".txt")).write_text("x\n", encoding="utf-8")
        for args, expected in (
            (["lifecycle", "status"], (0,)),
            (["git-preflight"], (0, 2)),
        ):
            with self.subTest(command=args[0]):
                done = subprocess.run(
                    [sys.executable, str(RUNNER), *args], cwd=self.root, env=env,
                    capture_output=True, text=True, encoding="utf-8", errors="replace",
                )
                self.assertIn(done.returncode, expected, done.stderr)
                self.assertNotIn("UnicodeEncodeError", done.stderr)

        payload = json.dumps({
            "cwd": str(self.root), "tool_name": "Bash",
            "tool_input": {"command": "rm -rf README.md"},
        })
        git(self.root, "checkout", "-q", "feature-" + EMOJI)
        done = subprocess.run(
            [sys.executable, str(RUNNER), "hook", "pre-tool"], cwd=self.root, env=env,
            input=payload, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("permissionDecision", done.stdout)

    # 4. line breaks must not forge status lines
    def test_line_breaks_are_rejected_in_stored_text(self) -> None:
        for probe in ("two\nlines", "carriage\rreturn"):
            with self.subTest(probe=probe):
                code, _, error = self.cli(
                    "lifecycle", "start", "--task", probe, "--base", "main"
                )
                self.assertEqual(code, 2)
                self.assertIn("control characters", error)
        self.assertEqual(workflow._one_line("a\nb\rc"), "a b c")

    # 5. commit drift under an unchanged branch name is visible
    def test_status_reports_head_drift_under_an_unchanged_branch(self) -> None:
        self.cli("lifecycle", "start", "--task", "x", "--base", "main")
        started = workflow.load_state(self.root, "lifecycle")["head_sha"]
        self.assertIsNotNone(started)
        _, output, _ = self.cli("lifecycle", "status")
        self.assertIn("head: %s" % started, output)
        self.assertNotIn("MOVED", output)

        git(self.root, "checkout", "-q", "-b", "side")
        (self.root / "README.md").write_text("rewritten\n", encoding="utf-8")
        git(self.root, "add", "-A")
        git(self.root, "commit", "-m", "unrelated")
        git(self.root, "checkout", "-q", "main")
        git(self.root, "reset", "--hard", "side")

        _, output, _ = self.cli("lifecycle", "status")
        self.assertIn("branch: main", output)
        self.assertIn("MOVED", output)

    def test_head_sha_is_validated_when_present(self) -> None:
        self.cli("lifecycle", "start", "--task", "x", "--base", "main")
        state = workflow.load_state(self.root, "lifecycle")
        state["head_sha"] = "not-a-sha"
        with self.assertRaisesRegex(workflow.WorkflowError, "hexadecimal commit id"):
            workflow.validate_state(state, "lifecycle")

    # 6. the Stop hook must not block a turn forever
    def test_stop_hook_releases_a_turn_it_already_continued(self) -> None:
        self.cli("lifecycle", "start", "--task", "x", "--base", "main")
        with pushd(self.root):
            # Already continued once: re-validating a payload the host keeps sending
            # would block the turn forever.
            code, output = self.hook("stop", {"cwd": 17, "stop_hook_active": True})
            self.assertEqual(code, 0)
            self.assertEqual(output.strip(), "")
            # The same payload without the flag still fails closed.
            with self.assertRaises(workflow.WorkflowError):
                self.hook("stop", {"cwd": 17})

    # low-severity hardening
    def test_env_suffix_and_nul_runner_path(self) -> None:
        for path in ("-.env", "config/prod.env", ".env"):
            self.assertTrue(workflow.is_sensitive_path(path), path)
        for path in (".env.example", "src/environment.ts"):
            self.assertFalse(workflow.is_sensitive_path(path), path)
        runner = str(RUNNER).replace("scripts", "scr\x00ipts", 1)
        self.assertFalse(
            workflow._is_safe_gate_command({
                "tool_name": "Bash", "cwd": str(self.root),
                "tool_input": {"command": 'python "%s" lifecycle status' % runner},
            })
        )


if __name__ == "__main__":
    unittest.main()


class ReviewRoundSixTests(WorkflowFixture):
    """Follow-up review: Windows launcher spelling, streamed index scan, review docs."""

    def test_windows_py_launcher_is_accepted_without_an_explicit_version(self) -> None:
        runner = str(RUNNER)
        for launcher in ("py", "py -3", "py -3.11", "python", "python3", "python3.11"):
            with self.subTest(launcher=launcher):
                self.assertIsNotNone(
                    workflow.SAFE_RUNNER_COMMAND.fullmatch(
                        '%s "%s" inspect git-status' % (launcher, runner)
                    ),
                    launcher,
                )
        for rejected in ("pyt", "py -2", "py3", "pypy"):
            with self.subTest(rejected=rejected):
                self.assertIsNone(
                    workflow.SAFE_RUNNER_COMMAND.fullmatch(
                        '%s "%s" inspect git-status' % (rejected, runner)
                    ),
                    rejected,
                )

    def test_py_launcher_still_only_reaches_allowlisted_subcommands(self) -> None:
        self.open_gate(self.root)
        for command, allowed in (
            ('py "%s" inspect git-status' % RUNNER, True),
            ('py "%s" lifecycle finish --step PLAN' % RUNNER, False),
            ('py "%s" inspect git-status && rm -rf x' % RUNNER, False),
        ):
            with self.subTest(command=command.split('" ', 1)[-1]):
                _, output = self.hook(
                    "pre-tool",
                    {"cwd": str(self.root), "tool_name": "Bash",
                     "tool_input": {"command": command}},
                )
                self.assertEqual(output.strip() == "", allowed)

    def test_tracked_scan_streams_and_keeps_non_utf8_names_testable(self) -> None:
        (self.root / "keep.txt").write_text("x\n", encoding="utf-8")
        git(self.root, "add", "keep.txt")
        git(self.root, "commit", "-m", "tracked file")
        self.assertIn("keep.txt", list(workflow.iter_tracked_paths(self.root)))

        # The stream must not decode a path with a replacement character, which would
        # hide the very suffix the credential check relies on.
        raw = b"deploy/id_rsa\0weird\xff.key\0"
        decoded = []
        pending = b""
        for start in range(0, len(raw), 3):  # arbitrary chunk boundaries
            pending += raw[start:start + 3]
            *complete, pending = pending.split(b"\0")
            decoded.extend(r.decode("utf-8", "surrogateescape") for r in complete if r)
        self.assertEqual(len(decoded), 2)
        self.assertTrue(all(workflow.is_sensitive_path(path) for path in decoded), decoded)
        self.assertNotIn("�", "".join(decoded))

    def test_tracked_scan_reports_git_failure_instead_of_returning_nothing(self) -> None:
        broken = self.base / "not-a-repo"
        broken.mkdir()
        with self.assertRaises(workflow.WorkflowError):
            list(workflow.iter_tracked_paths(broken))

    def test_review_step_tells_the_agent_to_act_on_omitted_paths(self) -> None:
        steps = (ROOT / "skills" / "lifecycle" / "references" / "steps.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("TrueDev omitted N sensitive path(s)", steps)
        self.assertIn("unreviewed change rather than an absent one", steps)
