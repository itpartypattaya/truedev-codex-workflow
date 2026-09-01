#!/usr/bin/env python3
"""Deterministic state and safety guard for the TrueDev Workflow plugin.

The script intentionally uses only the Python standard library. It is called both
by Codex hooks and by the bundled skills. Hooks are guardrails, not a security
boundary: Codex hosts may have tool paths that do not emit hook events.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import datetime as dt
from functools import wraps
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import time
from typing import Any, Iterable, Iterator, Mapping, Sequence


SCHEMA_VERSION = 4
MAX_STATE_BYTES = 1024 * 1024
MAX_HOOK_BYTES = 1024 * 1024
MAX_INSPECT_FILE_BYTES = 1024 * 1024
LOCK_TIMEOUT_SECONDS = 5.0
DETACHED_HEAD = "(detached)"
GIT_UNAVAILABLE = "(git-unavailable)"
BRANCH_SENTINELS = frozenset({DETACHED_HEAD, GIT_UNAVAILABLE})
STATE_DIR = ".truedev-workflow"
LIFECYCLE_FILE = "lifecycle.json"
PROJECT_INIT_FILE = "project-init.json"

LIFECYCLE_STEPS = (
    "CONTEXT_CHECK",
    "SCOPE",
    "PLAN",
    "COMPONENTS",
    "IMPLEMENT",
    "TEST",
    "VERIFY",
    "REVIEW",
    "DOCUMENT",
    "CLOSE",
)
LIFECYCLE_USER_GATES = frozenset({"SCOPE", "COMPONENTS", "VERIFY", "REVIEW", "CLOSE"})

PROJECT_PHASES = (
    "INPUT_VALIDATION",
    "PRD",
    "ARCHITECTURE",
    "PLANNING",
    "DECOMPOSITION",
    "FINALIZE",
)
PROJECT_USER_GATES = frozenset(PROJECT_PHASES[:-1])

VALID_STATUSES = frozenset({"pending", "in_progress", "awaiting_approval", "completed"})
# Line breaks are rejected with the other control characters: stored text is echoed
# into single-line status output that the model is told to trust.
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0a-\x1f\x7f]")
HEX_SHA = re.compile(r"[0-9a-f]{40}(?:[0-9a-f]{24})?")
SAFE_PATH_COMPONENT = re.compile(r"[A-Za-z0-9._-]+")
SHELL_CONTROL = re.compile(r"(?:\r|\n|;|&&|\|\||(?<!\|)\|(?!\|)|`|\$\(|[<>])")
SAFE_RUNNER_COMMAND = re.compile(
    r"^\s*(?:python(?:3(?:\.\d+)?)?|py(?:\s+-3(?:\.\d+)?)?)\s+"
    r"(?P<runner>\"[^\"]*truedev_workflow\.py\"|'[^']*truedev_workflow\.py'|\S*truedev_workflow\.py)\s+"
    r"(?:(?:lifecycle|project-init)\s+(?:status|validate)|"
    r"project-init\s+validate-slices(?:\s+--plan-dir\s+(?:\"[^\"]+\"|'[^']+'|[^\s]+))?|"
    r"git-preflight(?:\s+(?:--require-clean|--expected-branch\s+(?:\"[^\"]+\"|'[^']+'|[^\s]+)))*|"
    r"inspect\s+(?:git-status|git-diff(?:\s+(?:--staged|--stat|--check|--name-only|--name-status))*|"
    r"file\s+--path\s+(?:\"[^\"]+\"|'[^']+'|[^\s]+))|"
    r"(?:lifecycle|project-init)\s+abandon\s+--user-confirmed|"
    r"lifecycle\s+recover\s+--accept-current-branch\s+--user-confirmed|"
    r"lifecycle\s+release-compact\s+--user-confirmed|"
    r"(?:lifecycle|project-init)\s+approve\s+(?:--(?:step|phase)\s+)?[A-Z_]+\s+--user-confirmed)\s*$"
)
class WorkflowError(RuntimeError):
    """A user-actionable workflow validation error."""


class BranchMismatchError(WorkflowError):
    """A valid lifecycle state is attached to a different Git branch."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _git_env() -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_OPTIONAL_LOCKS"] = "0"
    for name in ("GIT_EXTERNAL_DIFF", "GIT_PAGER", "PAGER"):
        env.pop(name, None)
    return env


def iter_tracked_paths(root: Path) -> Iterator[str]:
    """Stream tracked paths instead of buffering the whole index listing.

    A large monorepo produces tens of megabytes here and the scan runs on every
    preflight, so peak memory stays flat. `surrogateescape` also keeps a path that
    is not valid UTF-8 testable instead of replacing the bytes that identify it.
    """
    command = ["git", "-C", str(root), "-c", "core.fsmonitor=false", "ls-files", "-z"]
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=_git_env()
        )
    except OSError as exc:
        raise WorkflowError(f"git ls-files failed: {exc}") from exc
    pending = b""
    stderr = b""
    try:
        for chunk in iter(lambda: process.stdout.read(65536), b""):
            pending += chunk
            *complete, pending = pending.split(b"\0")
            for record in complete:
                if record:
                    yield record.decode("utf-8", "surrogateescape")
        if pending:
            yield pending.decode("utf-8", "surrogateescape")
        stderr = process.stderr.read()
    finally:
        process.stdout.close()
        process.stderr.close()
        returncode = process.wait()
    if returncode != 0:
        raise WorkflowError(stderr.decode("utf-8", "replace").strip() or "git ls-files failed")


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = _git_env()
    command = ["git", "-C", str(root), "-c", "core.fsmonitor=false", *args]
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))


def _run_safe_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = _git_env()
    command = [
            "git",
            "-C",
            str(root),
            "--no-pager",
            "-c",
            "core.pager=cat",
            "-c",
            "core.fsmonitor=false",
            "-c",
            "pager.diff=false",
            "-c",
            "diff.external=",
            *args,
        ]
    try:
        return subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=env,
        )
    except OSError as exc:
        return subprocess.CompletedProcess(command, 127, "", str(exc))


def _read_first_line(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8").splitlines()[0]
    except (OSError, UnicodeError, IndexError):
        return None


def _has_valid_git_head(git_dir: Path) -> bool:
    head = _read_first_line(git_dir / "HEAD")
    if head is None:
        return False
    if re.fullmatch(r"[0-9A-Fa-f]{40}(?:[0-9A-Fa-f]{24})?", head):
        return True
    if not head.startswith("ref: refs/"):
        return False
    ref = head.removeprefix("ref: ")
    parts = ref.split("/")
    return (
        all(part not in {"", ".", ".."} for part in parts)
        and not CONTROL_CHARS.search(ref)
        and not any(char.isspace() or char in "~^:?*[\\" for char in ref)
        and "@{" not in ref
    )


def _is_reparse_point(path: Path) -> bool:
    """A Windows junction redirects the path without being a symlink to Python."""
    try:
        return bool(getattr(os.lstat(path), "st_reparse_tag", 0))
    except OSError:
        return False


def _is_link(path: Path) -> bool:
    return path.is_symlink() or _is_reparse_point(path)


def _has_valid_git_dir(git_dir: Path) -> bool:
    if not git_dir.is_dir() or _is_link(git_dir) or not _has_valid_git_head(git_dir):
        return False
    common_dir = git_dir
    commondir = _read_first_line(git_dir / "commondir")
    if commondir is not None:
        common_dir = Path(commondir)
        if not common_dir.is_absolute():
            common_dir = git_dir / common_dir
        try:
            common_dir = common_dir.resolve()
        except OSError:
            return False
    return (
        common_dir.is_dir()
        and not _is_link(common_dir)
        and (common_dir / "config").is_file()
        and (common_dir / "objects").is_dir()
        and (common_dir / "refs").is_dir()
    )


def _has_valid_git_marker(root: Path) -> bool:
    marker = root / ".git"
    if _is_link(marker):
        return False
    if marker.is_dir():
        return _has_valid_git_dir(marker)
    if not marker.is_file():
        return False
    first_line = _read_first_line(marker)
    if first_line is None:
        return False
    if not first_line.lower().startswith("gitdir:"):
        return False
    target = Path(first_line.split(":", 1)[1].strip())
    if not target.is_absolute():
        target = root / target
    return _has_valid_git_dir(target)


def find_repo_root(start: Path | str) -> Path | None:
    """Find a repo/state root even when Codex starts in a nested directory."""
    try:
        current = Path(start).resolve()
    except (OSError, TypeError, ValueError) as exc:
        raise WorkflowError(f"invalid working directory: {exc}") from exc
    if current.is_file():
        current = current.parent
    candidates = (current, *current.parents)
    for candidate in candidates:
        if _has_valid_git_marker(candidate):
            return candidate.resolve()
    result = _run_git(current, "rev-parse", "--show-toplevel")
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    for candidate in candidates:
        state_dir = candidate / STATE_DIR
        if state_dir.is_dir() and not _is_link(state_dir):
            return candidate
    return None


def state_path(root: Path, workflow: str) -> Path:
    filename = LIFECYCLE_FILE if workflow == "lifecycle" else PROJECT_INIT_FILE
    return root / STATE_DIR / filename


def require_contained_state(root: Path, target: Path) -> Path:
    """Refuse a state path that a link or junction redirects outside the repository.

    Only the state file itself was checked before, so a linked `.truedev-workflow`
    directory silently moved every read and write outside the repository.
    """
    base = root.resolve()
    try:
        relative = target.relative_to(root)
    except ValueError as exc:
        raise WorkflowError(f"workflow state path escapes the repository: {target}") from exc
    expected = base
    for part in relative.parts:
        expected = expected / part
        if not expected.exists():
            break
        if _is_link(expected):
            raise WorkflowError(
                f"workflow state path must not contain links or junctions: {expected}"
            )
        try:
            resolved = expected.resolve(strict=True)
        except OSError as exc:
            raise WorkflowError(f"cannot resolve workflow state path {expected}: {exc}") from exc
        if resolved != expected:
            raise WorkflowError(
                f"workflow state path must stay inside the repository: "
                f"{expected} resolves to {resolved}"
            )
    return target


@contextmanager
def workflow_lock(root: Path, workflow: str):
    """Serialize state transitions with an OS advisory lock in Git metadata."""
    git_dir_result = _run_git(root, "rev-parse", "--absolute-git-dir")
    if git_dir_result.returncode != 0 or not git_dir_result.stdout.strip():
        # Emergency operations must remain available if an export loses .git.
        # Atomic state writes still prevent torn JSON; cross-process serialization
        # is unavailable until Git metadata is restored.
        yield
        return
    git_dir = Path(git_dir_result.stdout.strip()).resolve()
    lock_path = git_dir / "truedev-workflow-locks" / f"{workflow}.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        deadline = time.monotonic() + LOCK_TIMEOUT_SECONDS
        while True:
            try:
                handle.seek(0)
                if os.name == "nt":
                    import msvcrt

                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError as exc:
                if time.monotonic() >= deadline:
                    raise WorkflowError(f"timed out waiting for the {workflow} state lock") from exc
                time.sleep(0.05)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    if _is_link(path) or not path.is_file():
        raise WorkflowError(f"invalid workflow state {path}: expected a regular file")
    try:
        raw = path.read_bytes()
        if len(raw) > MAX_STATE_BYTES:
            raise WorkflowError(f"invalid workflow state {path}: exceeds {MAX_STATE_BYTES} bytes")
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise WorkflowError(f"invalid workflow state {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise WorkflowError(f"invalid workflow state {path}: root must be an object")
    return value


def _atomic_write(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        try:
            os.chmod(temp_name, 0o600)
        except OSError:
            pass
        os.replace(temp_name, path)
        _fsync_directory(path.parent)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


def _fsync_directory(path: Path) -> None:
    flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _validate_text(value: Any, field: str, *, maximum: int = 5000, allow_empty: bool = False) -> str:
    if not isinstance(value, str):
        raise WorkflowError(f"{field} must be a string")
    if not allow_empty and not value.strip():
        raise WorkflowError(f"{field} must not be empty")
    if len(value) > maximum:
        raise WorkflowError(f"{field} exceeds {maximum} characters")
    if CONTROL_CHARS.search(value):
        raise WorkflowError(f"{field} contains control characters")
    return value


def _validate_timestamp(value: Any, field: str) -> str:
    text = _validate_text(value, field, maximum=64)
    try:
        parsed = dt.datetime.fromisoformat(text)
    except ValueError as exc:
        raise WorkflowError(f"{field} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != dt.timedelta(0):
        raise WorkflowError(f"{field} must be an ISO-8601 UTC timestamp")
    return text


def _definition(workflow: str) -> tuple[tuple[str, ...], frozenset[str], str]:
    if workflow == "lifecycle":
        return LIFECYCLE_STEPS, LIFECYCLE_USER_GATES, "current_step"
    if workflow == "project-init":
        return PROJECT_PHASES, PROJECT_USER_GATES, "current_phase"
    raise WorkflowError(f"unknown workflow: {workflow}")


def validate_state(state: Mapping[str, Any], workflow: str) -> None:
    order, user_gates, current_key = _definition(workflow)
    if state.get("schema_version") != SCHEMA_VERSION:
        raise WorkflowError(
            f"unsupported {workflow} state schema: expected {SCHEMA_VERSION}, got {state.get('schema_version')!r}"
        )
    if state.get("workflow") != workflow:
        raise WorkflowError(f"state workflow must be {workflow!r}")
    _validate_text(state.get("repo_root"), "repo_root")
    _validate_timestamp(state.get("started_at"), "started_at")
    _validate_timestamp(state.get("updated_at"), "updated_at")
    if workflow == "lifecycle":
        _validate_text(state.get("task"), "task")
        slice_ref = state.get("slice")
        if slice_ref is not None:
            _validate_slice_ref(slice_ref)
        recorded_head = state.get("head_sha")
        if recorded_head is not None and (
            not isinstance(recorded_head, str) or HEX_SHA.fullmatch(recorded_head) is None
        ):
            raise WorkflowError("head_sha must be a hexadecimal commit id")
        _validate_text(state.get("base_branch"), "base_branch", maximum=255)
        _validate_text(state.get("branch"), "branch", maximum=255)
        if not isinstance(state.get("awaiting_compact"), bool):
            raise WorkflowError("awaiting_compact must be boolean")
    else:
        _validate_text(state.get("project"), "project")
        _validate_text(state.get("spec"), "spec")

    current = state.get(current_key)
    if current not in order:
        raise WorkflowError(f"{current_key} must be one of {', '.join(order)}")
    steps = state.get("steps")
    if not isinstance(steps, dict) or set(steps) != set(order):
        raise WorkflowError("steps must contain exactly the declared workflow steps")

    current_index = order.index(current)
    for index, name in enumerate(order):
        item = steps[name]
        if not isinstance(item, dict):
            raise WorkflowError(f"steps.{name} must be an object")
        status = item.get("status")
        if status not in VALID_STATUSES:
            raise WorkflowError(f"steps.{name}.status is invalid: {status!r}")
        expected_gate = "user" if name in user_gates else "auto"
        if item.get("gate") != expected_gate:
            raise WorkflowError(f"steps.{name}.gate must be {expected_gate!r}")
        if status == "awaiting_approval" and expected_gate != "user":
            raise WorkflowError(f"auto step {name} cannot await user approval")
        if index < current_index and status != "completed":
            raise WorkflowError(f"earlier step {name} must be completed")
        if index == current_index and status not in {"in_progress", "awaiting_approval", "completed"}:
            raise WorkflowError(f"current step {name} must be active or completed")
        if index > current_index and status != "pending":
            raise WorkflowError(f"later step {name} must remain pending")
        approved_at = item.get("approved_at")
        outcome = item.get("outcome")
        if outcome not in {None, "not_applicable"}:
            raise WorkflowError(f"steps.{name}.outcome is invalid: {outcome!r}")
        if outcome == "not_applicable" and (name != "COMPONENTS" or status != "completed"):
            raise WorkflowError("only a completed COMPONENTS step may be not_applicable")
        if status == "completed" and expected_gate == "user" and outcome is None:
            _validate_timestamp(approved_at, f"steps.{name}.approved_at")
        elif approved_at is not None:
            raise WorkflowError(f"steps.{name}.approved_at is only valid for a completed user gate")

    current_status = steps[current]["status"]
    if current_status == "completed":
        if current_index != len(order) - 1:
            raise WorkflowError(f"non-final current step {current} cannot be completed")
        _validate_timestamp(state.get("finished_at"), "finished_at")
    elif "finished_at" in state:
        raise WorkflowError("finished_at is only valid after the final step is completed")

    history = state.get("history", [])
    if not isinstance(history, list) or len(history) > 1000:
        raise WorkflowError("history must be an array with at most 1000 entries")
    approval_receipts: list[tuple[str, str, int]] = []
    gate_receipts: list[tuple[str, int]] = []
    skip_receipts: list[tuple[str, int]] = []
    for index, entry in enumerate(history):
        if not isinstance(entry, dict):
            raise WorkflowError(f"history[{index}] must be an object")
        event_at = _validate_timestamp(entry.get("at"), f"history[{index}].at")
        action = _validate_text(entry.get("action"), f"history[{index}].action", maximum=64)
        event_name = _validate_text(entry.get("name"), f"history[{index}].name", maximum=255)
        actor = _validate_text(entry.get("actor"), f"history[{index}].actor", maximum=64)
        if event_name not in order:
            raise WorkflowError(f"history[{index}].name is not a declared workflow step")
        if action == "gate":
            if event_name not in user_gates or actor != "codex":
                raise WorkflowError(f"history[{index}] is not a valid user gate receipt")
            gate_receipts.append((event_name, index))
        if action == "approve":
            if event_name not in user_gates or actor != "user-explicit":
                raise WorkflowError(f"history[{index}] is not a valid user approval receipt")
            approval_receipts.append((event_name, event_at, index))
        if action == "skip":
            if event_name != "COMPONENTS" or actor != "codex-not-applicable":
                raise WorkflowError(f"history[{index}] is not a valid not-applicable receipt")
            skip_receipts.append((event_name, index))

    for name in user_gates:
        item = steps[name]
        if item.get("outcome") == "not_applicable":
            if len([receipt for receipt in skip_receipts if receipt[0] == name]) != 1:
                raise WorkflowError(f"not-applicable step {name} lacks exactly one skip receipt")
            if any(receipt[0] == name for receipt in approval_receipts):
                raise WorkflowError(f"not-applicable step {name} cannot have an approval receipt")
            continue
        if any(receipt[0] == name for receipt in skip_receipts):
            raise WorkflowError(f"step {name} has a skip receipt without a not-applicable outcome")
        matching = [
            receipt
            for receipt in approval_receipts
            if receipt[:2] == (name, item.get("approved_at"))
        ]
        if item["status"] == "completed" and len(matching) != 1:
            raise WorkflowError(f"completed user gate {name} lacks exactly one matching approval receipt")
        if item["status"] == "completed" and not any(
            gate_name == name and gate_index < matching[0][2] for gate_name, gate_index in gate_receipts
        ):
            raise WorkflowError(f"completed user gate {name} lacks a preceding gate receipt")
        if item["status"] != "completed" and any(receipt[0] == name for receipt in approval_receipts):
            raise WorkflowError(f"incomplete user gate {name} cannot have an approval receipt")


def load_state(root: Path, workflow: str) -> dict[str, Any] | None:
    value = _read_json(require_contained_state(root, state_path(root, workflow)))
    if value is not None:
        validate_state(value, workflow)
        recorded_root = Path(value["repo_root"]).resolve()
        if recorded_root != root.resolve():
            raise WorkflowError(
                f"state belongs to a different repository root: {recorded_root} != {root.resolve()}"
            )
    return value


def save_state(root: Path, workflow: str, state: dict[str, Any]) -> None:
    state["updated_at"] = utc_now()
    validate_state(state, workflow)
    _atomic_write(require_contained_state(root, state_path(root, workflow)), state)


def _new_steps(order: Sequence[str], user_gates: Iterable[str]) -> dict[str, dict[str, Any]]:
    gates = set(user_gates)
    return {
        name: {
            "status": "in_progress" if index == 0 else "pending",
            "gate": "user" if name in gates else "auto",
            "approved_at": None,
            "outcome": None,
        }
        for index, name in enumerate(order)
    }


def _history(state: dict[str, Any], action: str, name: str, actor: str, *, at: str | None = None) -> None:
    state.setdefault("history", []).append(
        {"at": at or utc_now(), "action": action, "name": name, "actor": actor}
    )


def detect_default_branch(root: Path) -> str:
    symbolic = _run_git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if symbolic.returncode == 0 and symbolic.stdout.strip().startswith("origin/"):
        branch = symbolic.stdout.strip().split("/", 1)[1]
        target = _run_git(root, "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{branch}")
        if target.returncode == 0:
            return branch
    raise WorkflowError("cannot determine the default branch from origin/HEAD; pass --base explicitly")


def _validate_slice_ref(value: Any) -> str:
    text = _validate_text(value, "slice", maximum=255).replace("\\", "/")
    path = PurePosixPath(text)
    if (
        path.is_absolute()
        or ":" in text
        or any(part in {"", ".", ".."} for part in path.parts)
        or any(SAFE_PATH_COMPONENT.fullmatch(part) is None for part in path.parts[:-1])
        or re.fullmatch(r"slice-[A-Za-z0-9._-]+\.md", path.name) is None
    ):
        raise WorkflowError(
            "slice must be a repository-relative <plan-dir>/slice-*.md path with safe path components"
        )
    return path.as_posix()


def _one_line(value: Any) -> str:
    """Keep one status field on one line, even for state written by an older version."""
    return CONTROL_CHARS.sub(" ", str(value))


def head_sha(root: Path) -> str | None:
    result = _run_git(root, "rev-parse", "--verify", "HEAD")
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value if HEX_SHA.fullmatch(value) else None


def current_branch(root: Path) -> str:
    result = _run_git(root, "branch", "--show-current")
    if result.returncode != 0:
        return GIT_UNAVAILABLE
    branch = result.stdout.strip()
    if not branch:
        return DETACHED_HEAD
    return branch


def require_lifecycle_branch(root: Path, state: Mapping[str, Any]) -> None:
    recorded = _validate_text(state.get("branch"), "branch", maximum=255)
    active = current_branch(root)
    if recorded in BRANCH_SENTINELS:
        # A sentinel never identifies a commit, so it must not satisfy the guard even
        # when the current lookup reports the same placeholder.
        raise BranchMismatchError(
            f"lifecycle is bound to the placeholder {recorded!r} instead of a real branch; "
            "restore Git metadata and recover onto a named branch, or abandon the workflow"
        )
    if active != recorded:
        raise BranchMismatchError(
            f"lifecycle started on branch {recorded!r}, but the active branch is {active!r}; "
            "switch back or recover the workflow before mutating"
        )


def _repo_root_or_error(cwd: str | Path | None = None) -> Path:
    root = find_repo_root(Path(cwd or Path.cwd()))
    if root is None:
        raise WorkflowError("run this command inside a Git repository")
    return root


def _lock_workflow(workflow: str):
    def decorate(function):
        @wraps(function)
        def locked(*args, **kwargs):
            root = _repo_root_or_error()
            with workflow_lock(root, workflow):
                return function(*args, **kwargs)

        return locked

    return decorate


def _lock_named_workflow(function):
    @wraps(function)
    def locked(workflow: str, *args, **kwargs):
        root = _repo_root_or_error()
        with workflow_lock(root, workflow):
            return function(workflow, *args, **kwargs)

    return locked


SECRET_STORE_DIRS = frozenset({"secrets"})
SECRET_FILE_STEMS = frozenset({"secret", "secrets"})
# Extensions that carry configuration data rather than program text.
SECRET_DATA_SUFFIXES = frozenset(
    {"cfg", "conf", "env", "ini", "json", "properties", "toml", "txt", "yaml", "yml"}
)
# Extensions that are program text or documentation; a file named `secrets.ts` is a
# module, not a credential store.
NON_SECRET_SUFFIXES = frozenset(
    {
        "adoc", "bash", "c", "cc", "cjs", "clj", "cpp", "cs", "css", "erl", "ex", "exs",
        "go", "gradle", "h", "hpp", "html", "java", "js", "json5", "jsx", "kt", "kts",
        "lock", "lua", "md", "mdx", "mjs", "php", "pl", "ps1", "psm1", "py", "pyi", "r",
        "rb", "rs", "rst", "scala", "scss", "sh", "sql", "svelte", "swift", "tf", "ts",
        "tsx", "vue", "zsh",
    }
)
# Qualifiers that mark a checked-in placeholder rather than a real credential file.
NON_SECRET_QUALIFIERS = frozenset(
    {
        "dist", "example", "fixture", "fixtures", "mock", "sample", "schema", "spec",
        "template", "test", "tests",
    }
)


def _is_secret_store_file(parts: Sequence[str]) -> bool:
    """Detect conventional secret stores without flagging ordinary source names."""
    basename = parts[-1]
    segments = basename.split(".")
    suffix = segments[-1] if len(segments) > 1 else ""
    if suffix in NON_SECRET_SUFFIXES:
        return False
    if any(segment in NON_SECRET_QUALIFIERS for segment in segments[1:-1]):
        return False
    if any(directory in SECRET_STORE_DIRS for directory in parts[:-1]):
        return True
    return segments[0] in SECRET_FILE_STEMS and suffix in SECRET_DATA_SUFFIXES


def is_sensitive_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip('"').lower()
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return False
    basename = parts[-1].rstrip(" .") or parts[-1]
    if basename in {".env.example", ".env.sample", ".env.template"}:
        return False
    if basename == ".env" or basename.startswith(".env.") or basename.endswith(".env"):
        return True
    if STATE_DIR in parts:
        return True
    if basename in {
        ".npmrc",
        ".pypirc",
        "auth.json",
        "kubeconfig",
        "terraform.tfstate",
        "terraform.tfstate.backup",
    }:
        return True
    if _is_secret_store_file(parts):
        return True
    if re.fullmatch(r"credentials(?:\.(?:json|ya?ml|toml|ini))?", basename):
        return True
    if re.fullmatch(r"client_secret[^/]*\.json", basename):
        return True
    if re.fullmatch(r"id_(?:rsa|dsa|ecdsa|ed25519)(?!\.pub).*", basename):
        return True
    if basename.startswith("serviceaccount") and basename.endswith(".json"):
        return True
    if basename == "application_default_credentials.json":
        return True
    if len(parts) >= 2 and parts[-2:] == [".docker", "config.json"]:
        return True
    return basename.endswith((".key", ".pem", ".p12", ".pfx", ".jks", ".keystore", ".tfstate"))


def require_state_ignored(root: Path, workflow: str) -> None:
    relative = state_path(root, workflow).relative_to(root).as_posix()
    tracked = _run_git(root, "ls-files", "--error-unmatch", relative)
    if tracked.returncode == 0:
        raise WorkflowError(f"workflow state is already tracked by Git: {relative}")
    ignored = _run_git(root, "check-ignore", "--quiet", "--no-index", relative)
    if ignored.returncode != 0:
        raise WorkflowError(
            f"workflow state is not ignored by Git: add {STATE_DIR}/ to .gitignore before starting"
        )


@_lock_workflow("lifecycle")
def lifecycle_start(args: argparse.Namespace) -> int:
    root = _repo_root_or_error()
    path = state_path(root, "lifecycle")
    if path.exists():
        raise WorkflowError(f"an active lifecycle already exists: {path}")
    require_state_ignored(root, "lifecycle")
    now = utc_now()
    branch = current_branch(root)
    if branch == DETACHED_HEAD:
        raise WorkflowError("detached HEAD is not supported by lifecycle start; switch to a named branch")
    if branch in BRANCH_SENTINELS:
        raise WorkflowError(f"lifecycle start requires a named branch, but Git reported {branch}")
    slice_ref = _validate_slice_ref(args.slice) if args.slice is not None else None
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "workflow": "lifecycle",
        "repo_root": str(root),
        "task": args.task,
        "slice": slice_ref,
        "base_branch": args.base or detect_default_branch(root),
        "branch": branch,
        "head_sha": head_sha(root),
        "started_at": now,
        "updated_at": now,
        "current_step": LIFECYCLE_STEPS[0],
        "awaiting_compact": False,
        "steps": _new_steps(LIFECYCLE_STEPS, LIFECYCLE_USER_GATES),
        "history": [],
    }
    _history(state, "start", LIFECYCLE_STEPS[0], "codex")
    save_state(root, "lifecycle", state)
    print(f"Started lifecycle for {args.task!r} on branch {state['branch']!r}.")
    return 0


@_lock_workflow("project-init")
def project_start(args: argparse.Namespace) -> int:
    root = _repo_root_or_error()
    path = state_path(root, "project-init")
    if path.exists():
        raise WorkflowError(f"an active project-init workflow already exists: {path}")
    require_state_ignored(root, "project-init")
    now = utc_now()
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "workflow": "project-init",
        "repo_root": str(root),
        "project": args.project,
        "spec": args.spec,
        "started_at": now,
        "updated_at": now,
        "current_phase": PROJECT_PHASES[0],
        "steps": _new_steps(PROJECT_PHASES, PROJECT_USER_GATES),
        "history": [],
    }
    _history(state, "start", PROJECT_PHASES[0], "codex")
    save_state(root, "project-init", state)
    print(f"Started project-init for {args.project!r}.")
    return 0


@_lock_named_workflow
def _transition(workflow: str, action: str, name: str, *, user_confirmed: bool = False) -> int:
    root = _repo_root_or_error()
    state = load_state(root, workflow)
    if state is None:
        raise WorkflowError(f"no active {workflow} workflow")
    if workflow == "lifecycle":
        require_lifecycle_branch(root, state)
    order, user_gates, current_key = _definition(workflow)
    current = state[current_key]
    if name.upper() != current:
        raise WorkflowError(f"requested {name.upper()}, but current step is {current}")
    item = state["steps"][current]

    if action == "gate":
        if current not in user_gates:
            raise WorkflowError(f"{current} is not a user gate")
        if item["status"] != "in_progress":
            raise WorkflowError(f"{current} must be in_progress before opening its approval gate")
        item["status"] = "awaiting_approval"
        _history(state, "gate", current, "codex")
        save_state(root, workflow, state)
        print(f"{current} is awaiting explicit user approval.")
        return 0

    transition_at: str | None = None
    if action == "approve":
        if current not in user_gates:
            raise WorkflowError(f"{current} is not a user gate")
        if item["status"] != "awaiting_approval":
            raise WorkflowError(f"{current} is not awaiting approval")
        if not user_confirmed:
            raise WorkflowError("approval requires --user-confirmed after an explicit user message")
        transition_at = utc_now()
        item["approved_at"] = transition_at
        actor = "user-explicit"
    elif action == "finish":
        if current in user_gates:
            raise WorkflowError(f"{current} requires gate then approve, not finish")
        if item["status"] != "in_progress":
            raise WorkflowError(f"{current} is not in progress")
        actor = "codex"
    else:
        raise WorkflowError(f"unsupported transition action: {action}")

    item["status"] = "completed"
    _history(state, action, current, actor, at=transition_at)
    index = order.index(current)
    if index + 1 < len(order):
        next_name = order[index + 1]
        state[current_key] = next_name
        state["steps"][next_name]["status"] = "in_progress"
        if workflow == "lifecycle" and current == "PLAN":
            state["awaiting_compact"] = True
        _history(state, "enter", next_name, "codex")
        message = f"{current} completed; {next_name} is now in progress."
    else:
        state["finished_at"] = utc_now()
        message = f"{current} completed; {workflow} is finished."
    save_state(root, workflow, state)
    print(message)
    return 0


@_lock_workflow("lifecycle")
def lifecycle_skip_components(args: argparse.Namespace) -> int:
    root = _repo_root_or_error()
    state = load_state(root, "lifecycle")
    if state is None:
        raise WorkflowError("no active lifecycle workflow")
    require_lifecycle_branch(root, state)
    if args.step != "COMPONENTS" or state["current_step"] != "COMPONENTS":
        raise WorkflowError("only the active COMPONENTS step can be marked not applicable")
    item = state["steps"]["COMPONENTS"]
    if item["status"] != "in_progress":
        raise WorkflowError("COMPONENTS must be in_progress before it can be skipped")
    item["status"] = "completed"
    item["outcome"] = "not_applicable"
    _history(state, "skip", "COMPONENTS", "codex-not-applicable")
    state["current_step"] = "IMPLEMENT"
    state["steps"]["IMPLEMENT"]["status"] = "in_progress"
    _history(state, "enter", "IMPLEMENT", "codex")
    save_state(root, "lifecycle", state)
    print("COMPONENTS marked not applicable for non-UI work; IMPLEMENT is now in progress.")
    return 0


def _archive_raw_state(root: Path, workflow: str, label: str) -> Path:
    source = require_contained_state(root, state_path(root, workflow))
    if not source.exists():
        raise WorkflowError(f"no active {workflow} workflow")
    if _is_link(source) or not source.is_file():
        raise WorkflowError(f"refusing to archive non-regular workflow state: {source}")
    raw = source.read_bytes()
    if len(raw) > MAX_STATE_BYTES:
        raise WorkflowError(f"workflow state exceeds {MAX_STATE_BYTES} bytes")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    destination = require_contained_state(
        root, root / STATE_DIR / "history" / f"{stamp}-{workflow}-{label}.state"
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(raw)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, destination)
        _fsync_directory(destination.parent)
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass
    return destination


@_lock_named_workflow
def abandon_workflow(workflow: str, *, user_confirmed: bool) -> int:
    if not user_confirmed:
        raise WorkflowError("abandon requires --user-confirmed after an explicit user message")
    root = _repo_root_or_error()
    source = state_path(root, workflow)
    destination = _archive_raw_state(root, workflow, "abandoned")
    source.unlink()
    print(f"Abandoned {workflow}; preserved the original state at {destination}")
    return 0


@_lock_workflow("lifecycle")
def recover_lifecycle_branch(*, accept_current_branch: bool, user_confirmed: bool) -> int:
    if not accept_current_branch or not user_confirmed:
        raise WorkflowError(
            "recovery requires --accept-current-branch and --user-confirmed after an explicit user decision"
        )
    root = _repo_root_or_error()
    state = load_state(root, "lifecycle")
    if state is None:
        raise WorkflowError("no active lifecycle workflow")
    active = current_branch(root)
    if active == DETACHED_HEAD:
        raise WorkflowError(
            "cannot recover lifecycle onto detached HEAD; switch to a named branch first"
        )
    if active == GIT_UNAVAILABLE:
        raise WorkflowError(
            "cannot recover lifecycle while Git metadata is unavailable; restore the repository "
            "first, or abandon the workflow with --user-confirmed"
        )
    if active == state["branch"]:
        raise WorkflowError("lifecycle already matches the active branch; no recovery is needed")
    previous = state["branch"]
    destination = _archive_raw_state(root, "lifecycle", "before-branch-recovery")
    state["branch"] = active
    _history(state, "recover", state["current_step"], "user-explicit")
    save_state(root, "lifecycle", state)
    print(f"Recovered lifecycle branch {previous!r} -> {active!r}; original state: {destination}")
    return 0


@_lock_workflow("lifecycle")
def release_compact_gate(*, user_confirmed: bool) -> int:
    if not user_confirmed:
        raise WorkflowError("compact release requires --user-confirmed after an explicit user message")
    root = _repo_root_or_error()
    state = load_state(root, "lifecycle")
    if state is None:
        raise WorkflowError("no active lifecycle workflow")
    require_lifecycle_branch(root, state)
    if not state["awaiting_compact"]:
        raise WorkflowError("the lifecycle compact gate is not active")
    state["awaiting_compact"] = False
    _history(state, "release-compact", state["current_step"], "user-explicit")
    save_state(root, "lifecycle", state)
    print("Released the compact gate after explicit user confirmation.")
    return 0


def validate_slices(args: argparse.Namespace) -> int:
    root = _repo_root_or_error()
    plan_dir = (root / args.plan_dir).resolve()
    try:
        plan_dir.relative_to(root.resolve())
    except ValueError as exc:
        raise WorkflowError("plan directory must stay inside the repository") from exc
    if not plan_dir.is_dir():
        raise WorkflowError(f"plan directory does not exist: {plan_dir}")
    records: dict[str, dict[str, Any]] = {}
    problems: list[str] = []
    for path in sorted(plan_dir.glob("slice-*.md")):
        if path.is_symlink():
            problems.append(f"slice file must not be a symlink: {path.name}")
            continue
        match = re.fullmatch(r"slice-(\d{3})-[^/\\]+\.md", path.name)
        if not match:
            problems.append(f"invalid slice filename: {path.name}")
            continue
        slice_id = f"slice-{match.group(1)}"
        if slice_id in records:
            problems.append(f"duplicate slice id: {slice_id}")
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise WorkflowError(f"cannot read slice file {path.name} as UTF-8: {exc}") from exc
        dependency_match = re.search(r"(?mi)^Depends on:\s*(.+?)\s*$", text)
        if dependency_match is None:
            problems.append(f"{path.name}: missing Depends on header")
            dependencies: list[str] = []
        else:
            raw = dependency_match.group(1).strip()
            dependencies = [] if raw.lower() == "none" else [item.strip() for item in raw.split(",") if item.strip()]
        records[slice_id] = {"file": path.name, "dependencies": dependencies}
    if not records:
        problems.append("no valid slice files found")
    for slice_id, record in records.items():
        for dependency in record["dependencies"]:
            if not re.fullmatch(r"slice-\d{3}", dependency):
                problems.append(f"{record['file']}: invalid dependency id {dependency!r}")
            elif dependency == slice_id:
                problems.append(f"{record['file']}: self dependency {dependency}")
            elif dependency not in records:
                problems.append(f"{record['file']}: missing dependency {dependency}")
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(slice_id: str, trail: list[str]) -> None:
        if slice_id in visiting:
            cycle = trail[trail.index(slice_id):] + [slice_id]
            problems.append("dependency cycle: " + " -> ".join(cycle))
            return
        if slice_id in visited:
            return
        visiting.add(slice_id)
        for dependency in records[slice_id]["dependencies"]:
            if dependency in records:
                visit(dependency, [*trail, dependency])
        visiting.remove(slice_id)
        visited.add(slice_id)

    for slice_id in records:
        visit(slice_id, [slice_id])
    result = {"ok": not problems, "slices": records, "problems": sorted(set(problems))}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not problems else 2


def print_status(workflow: str) -> int:
    root = _repo_root_or_error()
    state = load_state(root, workflow)
    if state is None:
        print(f"No active {workflow} workflow.")
        return 0
    order, _, current_key = _definition(workflow)
    print(f"{workflow}: {state[current_key]}")
    if workflow == "lifecycle":
        print(f"task: {_one_line(state['task'])}")
        if state.get("slice") is not None:
            print(f"slice: {_one_line(state['slice'])}")
        active_branch = current_branch(root)
        if active_branch == state["branch"]:
            print(f"branch: {_one_line(state['branch'])} (base: {_one_line(state['base_branch'])})")
        else:
            print(
                f"branch: {_one_line(state['branch'])} (active: {_one_line(active_branch)}; "
                f"MISMATCH; base: {_one_line(state['base_branch'])})"
            )
        recorded_head = state.get("head_sha")
        if recorded_head:
            active_head = head_sha(root)
            if active_head is None:
                print(f"head: {recorded_head} (active: unknown)")
            elif active_head != recorded_head:
                print(f"head: {recorded_head} (active: {active_head}; MOVED)")
            else:
                print(f"head: {recorded_head}")
        print(f"awaiting_compact: {str(state['awaiting_compact']).lower()}")
    else:
        print(f"project: {_one_line(state['project'])}")
        print(f"spec: {_one_line(state['spec'])}")
    for name in order:
        item = state["steps"][name]
        marker = ">" if name == state[current_key] else " "
        gate = " user-gate" if item["gate"] == "user" else ""
        print(f"{marker} {name:<18} {item['status']}{gate}")
    return 0


def validate_command(workflow: str) -> int:
    root = _repo_root_or_error()
    state = load_state(root, workflow)
    if state is None:
        print(f"No active {workflow} workflow.")
        return 0
    print(f"{workflow} state is valid: {state_path(root, workflow)}")
    return 0


@_lock_named_workflow
def archive_workflow(workflow: str) -> int:
    root = _repo_root_or_error()
    source = state_path(root, workflow)
    state = load_state(root, workflow)
    if state is None:
        raise WorkflowError(f"no active {workflow} workflow")
    if workflow == "lifecycle":
        require_lifecycle_branch(root, state)
    order, _, current_key = _definition(workflow)
    if state[current_key] != order[-1] or state["steps"][order[-1]]["status"] != "completed":
        raise WorkflowError(f"cannot archive {workflow} before {order[-1]} is completed")
    if not state.get("finished_at"):
        raise WorkflowError(f"cannot archive {workflow} without finished_at")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = require_contained_state(
        root, root / STATE_DIR / "history" / f"{stamp}-{workflow}.json"
    )
    if destination.exists():
        raise WorkflowError(f"archive destination already exists: {destination}")
    _atomic_write(destination, state)
    source.unlink()
    print(f"Archived {workflow} receipt: {destination}")
    return 0


def git_preflight(args: argparse.Namespace) -> int:
    root = _repo_root_or_error()
    problems: list[str] = []
    status = _run_git(root, "status", "--porcelain=v1", "-z", "--untracked-files=all")
    if status.returncode != 0:
        raise WorkflowError(status.stderr.strip() or "git status failed")
    changed: list[str] = []
    records = status.stdout.split("\0")
    index = 0
    while index < len(records):
        record = records[index]
        index += 1
        if not record:
            continue
        if len(record) < 4:
            raise WorkflowError("git status returned an invalid porcelain record")
        code = record[:2]
        changed.append(record[3:])
        if "R" in code or "C" in code:
            if index >= len(records) or not records[index]:
                raise WorkflowError("git status returned an incomplete rename/copy record")
            changed.append(records[index])
            index += 1
    sensitive = [path for path in changed if is_sensitive_path(path)]
    if sensitive:
        problems.append(
            "high-confidence sensitive credential or transient paths present: "
            + ", ".join(sensitive)
        )
    tracked_sensitive = [path for path in iter_tracked_paths(root) if is_sensitive_path(path)]
    if tracked_sensitive:
        problems.append(
            "high-confidence sensitive credential or transient paths are tracked: "
            + ", ".join(tracked_sensitive)
        )
    if args.require_clean and changed:
        problems.append("working tree is not clean: " + ", ".join(changed))
    branch = current_branch(root)
    if args.expected_branch and branch != args.expected_branch:
        problems.append(f"current branch is {branch!r}, expected {args.expected_branch!r}")
    operations = {
        "MERGE_HEAD": "merge",
        "CHERRY_PICK_HEAD": "cherry-pick",
        "REVERT_HEAD": "revert",
        "rebase-merge": "rebase",
        "rebase-apply": "rebase",
    }
    git_dir_result = _run_git(root, "rev-parse", "--git-dir")
    if git_dir_result.returncode == 0:
        git_dir = Path(git_dir_result.stdout.strip())
        if not git_dir.is_absolute():
            git_dir = root / git_dir
        active = sorted({label for marker, label in operations.items() if (git_dir / marker).exists()})
        if active:
            problems.append("git operation in progress: " + ", ".join(active))
    try:
        default_branch: str | None = detect_default_branch(root)
    except WorkflowError:
        default_branch = None
    result = {
        "ok": not problems,
        "root": str(root),
        "branch": branch,
        "default_branch": default_branch,
        "changed": changed,
        "problems": problems,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not problems else 2


def inspect_git(args: argparse.Namespace) -> int:
    root = _repo_root_or_error()
    if args.inspect_command == "git-status":
        command = ("status", "--short", "--branch", "--untracked-files=all")
    elif args.inspect_command == "git-diff":
        command_parts = [
            "diff",
            "--no-ext-diff",
            "--no-textconv",
            "--no-renames",
            "--color=never",
        ]
        if args.staged:
            command_parts.append("--staged")
        names = _run_safe_git(root, *command_parts, "--name-only", "-z", "--")
        if names.returncode != 0:
            raise WorkflowError(names.stderr.strip() or "git diff path inspection failed")
        changed = [path for path in names.stdout.split("\0") if path]
        omitted = sorted({path for path in changed if is_sensitive_path(path)})
        for flag in ("staged", "stat", "check", "name_only", "name_status"):
            if flag != "staged" and getattr(args, flag):
                command_parts.append("--" + flag.replace("_", "-"))
        if omitted:
            # Never let a silent omission read as a complete diff: the reviewer must be
            # able to tell "nothing changed" from "the change was withheld".
            print(
                f"# TrueDev omitted {len(omitted)} sensitive path(s) from this diff: "
                + ", ".join(omitted)
            )
            if len(omitted) == len(changed):
                return 0
            # Subtracting the withheld paths keeps the command line bounded by the number
            # of omitted files instead of the size of the whole change set.
            command = (
                *command_parts,
                "--",
                ".",
                *(f":(exclude,literal){path}" for path in omitted),
            )
        else:
            command = tuple(command_parts)
    else:
        raise WorkflowError(f"unsupported inspection command: {args.inspect_command}")
    result = _run_safe_git(root, *command)
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.returncode != 0:
        if (
            args.inspect_command == "git-diff"
            and getattr(args, "check", False)
            and result.stdout
        ):
            # `git diff --check` reports whitespace findings through a non-zero status
            # while printing them. That is evidence for the gate, not a failure of the
            # inspection itself; a real failure produces no findings on stdout.
            return 2
        raise WorkflowError(result.stderr.strip() or f"git {command[0]} inspection failed")
    return 0


def inspect_file(args: argparse.Namespace) -> int:
    root = _repo_root_or_error().resolve()
    raw_path = _validate_text(args.path, "inspect path", maximum=4096).replace("\\", "/")
    if Path(raw_path).is_absolute() or ":" in raw_path or any(char in raw_path for char in "*?[]"):
        raise WorkflowError("inspect path must be a literal repository-relative path")
    candidate = root / raw_path
    try:
        resolved = candidate.resolve(strict=True)
        relative = resolved.relative_to(root).as_posix()
    except (OSError, ValueError) as exc:
        raise WorkflowError("inspect path must resolve to a file inside the repository") from exc
    cursor = root
    for part in Path(raw_path).parts:
        cursor /= part
        if cursor.is_symlink():
            raise WorkflowError("inspect path must not contain symlinks")
    if is_sensitive_path(relative):
        raise WorkflowError(f"refusing to inspect a sensitive path: {relative}")
    if not resolved.is_file():
        raise WorkflowError(f"inspect path is not a regular file: {relative}")
    try:
        raw = resolved.read_bytes()
        if len(raw) > MAX_INSPECT_FILE_BYTES:
            raise WorkflowError(f"inspect file exceeds {MAX_INSPECT_FILE_BYTES} bytes")
        text = raw.decode("utf-8")
    except (OSError, UnicodeError) as exc:
        raise WorkflowError(f"cannot inspect {relative} as UTF-8: {exc}") from exc
    print(text, end="" if text.endswith("\n") else "\n")
    return 0


def _read_hook_payload() -> dict[str, Any]:
    raw = sys.stdin.read(MAX_HOOK_BYTES + 1)
    if len(raw.encode("utf-8")) > MAX_HOOK_BYTES:
        raise WorkflowError(f"hook input exceeds {MAX_HOOK_BYTES} bytes")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"invalid hook input: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowError("hook input must be an object")
    return payload


def _validate_hook_payload(payload: Mapping[str, Any], event: str) -> None:
    cwd = payload.get("cwd")
    if cwd is not None:
        _validate_text(cwd, "hook input cwd", maximum=32768)
    if event == "pre-tool":
        _validate_text(payload.get("tool_name"), "hook input tool_name", maximum=255)
        if not isinstance(payload.get("tool_input"), dict):
            raise WorkflowError("hook input tool_input must be an object")
    elif event == "session-start":
        source = payload.get("source")
        if source is not None:
            _validate_text(source, "hook input source", maximum=255)
    elif event == "stop":
        active = payload.get("stop_hook_active")
        if active is not None and not isinstance(active, bool):
            raise WorkflowError("hook input stop_hook_active must be boolean")


def _has_workflow_state(root: Path | None) -> bool:
    if root is None:
        return False
    return any(
        path.exists() or path.is_symlink()
        for path in (state_path(root, "project-init"), state_path(root, "lifecycle"))
    )


def _hook_context(event: str) -> tuple[dict[str, Any] | None, Path | None]:
    """Read only enough input to preserve no-state inertness before strict validation."""
    try:
        payload = _read_hook_payload()
    except WorkflowError:
        root = find_repo_root(Path.cwd())
        if not _has_workflow_state(root):
            return None, root
        raise
    cwd = payload.get("cwd")
    root = find_repo_root(cwd if isinstance(cwd, str) and cwd.strip() else Path.cwd())
    if not _has_workflow_state(root):
        return payload, root
    if event == "stop" and payload.get("stop_hook_active") is True:
        # The turn was already continued once by this hook. Re-validating a payload
        # the host keeps sending would block the turn forever.
        return payload, root
    _validate_hook_payload(payload, event)
    return payload, root


def _emit(value: Mapping[str, Any]) -> int:
    print(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
    return 0


def _deny(reason: str) -> int:
    return _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        }
    )


def _is_safe_gate_command(payload: Mapping[str, Any]) -> bool:
    if payload.get("tool_name") != "Bash":
        return False
    tool_input = payload.get("tool_input")
    if not isinstance(tool_input, dict):
        return False
    command = tool_input.get("command")
    if not isinstance(command, str) or SHELL_CONTROL.search(command):
        return False
    match = SAFE_RUNNER_COMMAND.fullmatch(command)
    if match is None:
        return False
    runner = match.group("runner").strip("\"'")
    candidate = Path(runner)
    if not candidate.is_absolute():
        # The shell resolves a relative runner against the tool call's own working
        # directory, not against the repository root. Checking any other base would
        # approve one file while a different one executes.
        cwd = payload.get("cwd")
        if not isinstance(cwd, str) or not cwd.strip():
            return False
        try:
            candidate = Path(cwd) / candidate
        except (TypeError, ValueError):
            return False
    try:
        return candidate.resolve() == Path(__file__).resolve()
    except (OSError, ValueError):
        # A NUL byte in the path raises ValueError, not OSError.
        return False


def _active_states(root: Path) -> list[tuple[str, dict[str, Any]]]:
    active: list[tuple[str, dict[str, Any]]] = []
    for workflow in ("project-init", "lifecycle"):
        path = state_path(root, workflow)
        if path.exists():
            state = load_state(root, workflow)
            if state is not None:
                if workflow == "lifecycle":
                    require_lifecycle_branch(root, state)
                active.append((workflow, state))
    return active


def related_roots(root: Path) -> list[Path]:
    """Other checkouts whose open gate must also cover work done from this root.

    A linked worktree is the same repository, and a nested checkout such as a
    submodule sits inside its parent's working tree. Both used to be invisible
    here, so a gate opened in one of them did not stop mutations in the others.
    """
    roots: list[Path] = []
    seen = {root.resolve()}
    # Enclosing checkouts are a pure filesystem walk, so an ordinary single checkout
    # pays nothing extra here.
    for parent in root.resolve().parents:
        if parent in seen:
            continue
        if any(
            (parent / STATE_DIR / name).exists()
            for name in (LIFECYCLE_FILE, PROJECT_INIT_FILE)
        ):
            seen.add(parent)
            roots.append(parent)
    if not _may_have_linked_worktrees(root):
        return roots
    listing = _run_git(root, "worktree", "list", "--porcelain")
    if listing.returncode == 0:
        for line in listing.stdout.splitlines():
            if not line.startswith("worktree "):
                continue
            try:
                candidate = Path(line[len("worktree ") :].strip()).resolve()
            except OSError:
                continue
            if candidate not in seen and candidate.is_dir():
                seen.add(candidate)
                roots.append(candidate)
    return roots


def _may_have_linked_worktrees(root: Path) -> bool:
    """Avoid spawning Git for the common case of a single ordinary checkout."""
    marker = root / ".git"
    if marker.is_file():
        return True  # this checkout is itself linked: a worktree or a submodule
    return (marker / "worktrees").is_dir()


def _gate_decision(states: Sequence[tuple[str, Mapping[str, Any]]], scope: str) -> str | None:
    for workflow, state in states:
        _, _, current_key = _definition(workflow)
        current = state[current_key]
        if workflow == "lifecycle" and state.get("awaiting_compact"):
            return (
                f"TrueDev compact gate is active before {current}{scope}. "
                "Compact the Codex task, then retry."
            )
        if state["steps"][current]["status"] == "awaiting_approval":
            return (
                f"TrueDev user gate {workflow}:{current} is awaiting explicit approval{scope}; "
                "mutations are blocked."
            )
    return None


def hook_pre_tool() -> int:
    payload, root = _hook_context("pre-tool")
    if payload is None or root is None:
        return 0
    if _is_safe_gate_command(payload):
        return 0
    try:
        states = _active_states(root)
    except BranchMismatchError as exc:
        return _deny(f"TrueDev lifecycle branch mismatch; switch back or recover before mutating: {exc}")
    except WorkflowError as exc:
        return _deny(f"TrueDev state is invalid; repair or recover it before mutating the repo: {exc}")
    reason = _gate_decision(states, "")
    if reason is not None:
        return _deny(reason)
    for other in related_roots(root):
        try:
            other_states = _active_states(other)
        except BranchMismatchError:
            continue
        except WorkflowError as exc:
            return _deny(
                f"TrueDev state in a related checkout is invalid; repair or recover it: {exc}"
            )
        reason = _gate_decision(other_states, f" in the related checkout {other}")
        if reason is not None:
            return _deny(reason)
    return 0


def _safe_context(states: Sequence[tuple[str, Mapping[str, Any]]]) -> str:
    parts = ["TrueDev workflow state was schema-validated after compaction."]
    for workflow, state in states:
        _, _, current_key = _definition(workflow)
        current = state[current_key]
        status = state["steps"][current]["status"]
        compact = f"; awaiting_compact={str(state.get('awaiting_compact', False)).lower()}" if workflow == "lifecycle" else ""
        slice_ref = f"; slice={state['slice']}" if workflow == "lifecycle" and state.get("slice") else ""
        parts.append(f"{workflow}: current={current}; status={status}{compact}{slice_ref}.")
    parts.append("Use the bundled status command for details. Never infer user approval from this context.")
    return " ".join(parts)


def hook_session_start() -> int:
    payload, root = _hook_context("session-start")
    if payload is None or root is None:
        return 0
    if payload.get("source") != "compact":
        return 0
    try:
        states = _active_states(root)
        refreshed: list[tuple[str, dict[str, Any]]] = []
        for workflow, state in states:
            if workflow == "lifecycle" and state.get("awaiting_compact"):
                with workflow_lock(root, workflow):
                    locked_state = load_state(root, workflow)
                    if locked_state is None:
                        continue
                    require_lifecycle_branch(root, locked_state)
                    if locked_state.get("awaiting_compact"):
                        locked_state["awaiting_compact"] = False
                        _history(locked_state, "compact", locked_state["current_step"], "codex-host")
                        save_state(root, workflow, locked_state)
                    state = locked_state
            refreshed.append((workflow, state))
        states = refreshed
    except BranchMismatchError as exc:
        return _emit(
            {
                "continue": False,
                "stopReason": f"TrueDev lifecycle branch mismatch after compaction: {exc}",
                "systemMessage": "TrueDev workflow is paused until the branch is switched back or recovered.",
            }
        )
    except WorkflowError as exc:
        return _emit(
            {
                "continue": False,
                "stopReason": f"TrueDev state validation failed after compaction: {exc}",
                "systemMessage": "TrueDev workflow is paused until its state is repaired.",
            }
        )
    if not states:
        return 0
    return _emit(
        {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": _safe_context(states),
            }
        }
    )


def hook_stop() -> int:
    payload, root = _hook_context("stop")
    if payload is None or root is None:
        return 0
    if payload.get("stop_hook_active") is True:
        return 0
    try:
        states = _active_states(root)
    except BranchMismatchError as exc:
        return _emit(
            {
                "decision": "block",
                "reason": f"TrueDev lifecycle branch mismatch. Switch back or recover before ending the workflow turn: {exc}",
            }
        )
    except WorkflowError as exc:
        return _emit(
            {
                "decision": "block",
                "reason": f"TrueDev state is invalid. Repair or recover it before ending the workflow turn: {exc}",
            }
        )
    for workflow, state in states:
        _, _, current_key = _definition(workflow)
        current = state[current_key]
        if workflow == "lifecycle" and state.get("awaiting_compact"):
            return _emit(
                {
                    "decision": "block",
                    "reason": f"TrueDev compact gate is active before {current}. Ask the user to compact the task.",
                }
            )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    lifecycle = sub.add_parser("lifecycle")
    lifecycle_sub = lifecycle.add_subparsers(dest="lifecycle_command", required=True)
    start = lifecycle_sub.add_parser("start")
    start.add_argument("--task", required=True)
    start.add_argument("--slice")
    start.add_argument("--base")
    start.set_defaults(func=lifecycle_start)
    for action in ("gate", "finish", "approve"):
        item = lifecycle_sub.add_parser(action)
        item.add_argument("--step", required=True, choices=LIFECYCLE_STEPS)
        if action == "approve":
            item.add_argument("--user-confirmed", action="store_true")
        item.set_defaults(
            func=lambda args, action=action: _transition(
                "lifecycle", action, args.step, user_confirmed=getattr(args, "user_confirmed", False)
            )
        )
    skip = lifecycle_sub.add_parser("skip")
    skip.add_argument("--step", required=True, choices=("COMPONENTS",))
    skip.add_argument("--reason", required=True, choices=("non-ui",))
    skip.set_defaults(func=lifecycle_skip_components)
    recover = lifecycle_sub.add_parser("recover")
    recover.add_argument("--accept-current-branch", action="store_true")
    recover.add_argument("--user-confirmed", action="store_true")
    recover.set_defaults(
        func=lambda args: recover_lifecycle_branch(
            accept_current_branch=args.accept_current_branch, user_confirmed=args.user_confirmed
        )
    )
    release_compact = lifecycle_sub.add_parser("release-compact")
    release_compact.add_argument("--user-confirmed", action="store_true")
    release_compact.set_defaults(
        func=lambda args: release_compact_gate(user_confirmed=args.user_confirmed)
    )
    abandon = lifecycle_sub.add_parser("abandon")
    abandon.add_argument("--user-confirmed", action="store_true")
    abandon.set_defaults(func=lambda args: abandon_workflow("lifecycle", user_confirmed=args.user_confirmed))
    lifecycle_sub.add_parser("status").set_defaults(func=lambda _args: print_status("lifecycle"))
    lifecycle_sub.add_parser("validate").set_defaults(func=lambda _args: validate_command("lifecycle"))
    lifecycle_sub.add_parser("archive").set_defaults(func=lambda _args: archive_workflow("lifecycle"))

    project = sub.add_parser("project-init")
    project_sub = project.add_subparsers(dest="project_command", required=True)
    project_start_parser = project_sub.add_parser("start")
    project_start_parser.add_argument("--project", required=True)
    project_start_parser.add_argument("--spec", required=True)
    project_start_parser.set_defaults(func=project_start)
    for action in ("gate", "finish", "approve"):
        item = project_sub.add_parser(action)
        item.add_argument("--phase", required=True, choices=PROJECT_PHASES)
        if action == "approve":
            item.add_argument("--user-confirmed", action="store_true")
        item.set_defaults(
            func=lambda args, action=action: _transition(
                "project-init", action, args.phase, user_confirmed=getattr(args, "user_confirmed", False)
            )
        )
    project_sub.add_parser("status").set_defaults(func=lambda _args: print_status("project-init"))
    project_sub.add_parser("validate").set_defaults(func=lambda _args: validate_command("project-init"))
    project_sub.add_parser("archive").set_defaults(func=lambda _args: archive_workflow("project-init"))
    project_abandon = project_sub.add_parser("abandon")
    project_abandon.add_argument("--user-confirmed", action="store_true")
    project_abandon.set_defaults(
        func=lambda args: abandon_workflow("project-init", user_confirmed=args.user_confirmed)
    )
    slice_validation = project_sub.add_parser("validate-slices")
    slice_validation.add_argument("--plan-dir", default="docs/plan")
    slice_validation.set_defaults(func=validate_slices)

    preflight = sub.add_parser("git-preflight")
    preflight.add_argument("--require-clean", action="store_true")
    preflight.add_argument("--expected-branch")
    preflight.set_defaults(func=git_preflight)

    inspect = sub.add_parser("inspect")
    inspect_sub = inspect.add_subparsers(dest="inspect_command", required=True)
    inspect_sub.add_parser("git-status").set_defaults(func=inspect_git)
    inspect_diff = inspect_sub.add_parser("git-diff")
    inspect_diff.add_argument("--staged", action="store_true")
    inspect_diff.add_argument("--stat", action="store_true")
    inspect_diff.add_argument("--check", action="store_true")
    inspect_diff.add_argument("--name-only", action="store_true")
    inspect_diff.add_argument("--name-status", action="store_true")
    inspect_diff.set_defaults(func=inspect_git)
    inspect_file_parser = inspect_sub.add_parser("file")
    inspect_file_parser.add_argument("--path", required=True)
    inspect_file_parser.set_defaults(func=inspect_file)

    hook = sub.add_parser("hook")
    hook_sub = hook.add_subparsers(dest="hook_command", required=True)
    hook_sub.add_parser("pre-tool").set_defaults(func=lambda _args: hook_pre_tool())
    hook_sub.add_parser("session-start").set_defaults(func=lambda _args: hook_session_start())
    hook_sub.add_parser("stop").set_defaults(func=lambda _args: hook_stop())
    return parser


def use_utf8_output() -> None:
    """Emit UTF-8 regardless of the console code page.

    Output carries repository-controlled text: branch names, task text, and file
    names. On a Windows ANSI code page any character outside it turned every
    status, preflight, and hook emission into an unhandled UnicodeEncodeError.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (OSError, ValueError):
            pass


def main(argv: Sequence[str] | None = None) -> int:
    use_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except WorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        if args.command != "hook":
            raise
        print(f"ERROR: hook failed safely: {type(exc).__name__}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
