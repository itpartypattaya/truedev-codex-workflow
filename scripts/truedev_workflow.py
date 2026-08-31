#!/usr/bin/env python3
"""Deterministic state and safety guard for the TrueDev Workflow plugin.

The script intentionally uses only the Python standard library. It is called both
by Codex hooks and by the bundled skills. Hooks are guardrails, not a security
boundary: Codex hosts may have tool paths that do not emit hook events.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Mapping, Sequence


SCHEMA_VERSION = 3
STATE_DIR = ".truedev-workflow"
LIFECYCLE_FILE = "lifecycle.json"
PROJECT_INIT_FILE = "project-init.json"

LIFECYCLE_STEPS = (
    "CONTEXT_CHECK",
    "SCOPE",
    "PLAN",
    "COMPONENTS",
    "IMPLEMENT",
    "VERIFY",
    "TEST",
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
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
SHELL_CONTROL = re.compile(r"(?:\r|\n|;|&&|\|\||(?<!\|)\|(?!\|)|`|\$\(|[<>])")
SAFE_GATED_COMMAND = re.compile(
    r"^\s*(?:(?:python(?:3(?:\.\d+)?)?)|(?:py\s+-3))\s+"
    r"(?:\"[^\"]*truedev_workflow\.py\"|'[^']*truedev_workflow\.py'|\S*truedev_workflow\.py)\s+"
    r"(?:(?:lifecycle|project-init)\s+(?:status|validate)|"
    r"(?:lifecycle|project-init)\s+approve\s+(?:--(?:step|phase)\s+)?[A-Z_]+\s+--user-confirmed)\s*$"
)
class WorkflowError(RuntimeError):
    """A user-actionable workflow validation error."""


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def _run_git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def find_repo_root(start: Path | str) -> Path | None:
    """Find a repo/state root even when Codex starts in a nested directory."""
    current = Path(start).resolve()
    if current.is_file():
        current = current.parent
    for candidate in (current, *current.parents):
        if (candidate / STATE_DIR).exists() or (candidate / ".git").exists():
            return candidate
    result = _run_git(current, "rev-parse", "--show-toplevel")
    if result.returncode == 0 and result.stdout.strip():
        return Path(result.stdout.strip()).resolve()
    return None


def state_path(root: Path, workflow: str) -> Path:
    filename = LIFECYCLE_FILE if workflow == "lifecycle" else PROJECT_INIT_FILE
    return root / STATE_DIR / filename


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
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
    finally:
        try:
            os.unlink(temp_name)
        except FileNotFoundError:
            pass


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
    _validate_text(state.get("started_at"), "started_at")
    _validate_text(state.get("updated_at"), "updated_at")
    if workflow == "lifecycle":
        _validate_text(state.get("task"), "task")
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
        if status == "completed" and expected_gate == "user" and not item.get("approved_at"):
            raise WorkflowError(f"completed user gate {name} lacks approved_at")

    current_status = steps[current]["status"]
    if current_status == "completed":
        if current_index != len(order) - 1:
            raise WorkflowError(f"non-final current step {current} cannot be completed")
        _validate_text(state.get("finished_at"), "finished_at")
    elif "finished_at" in state:
        raise WorkflowError("finished_at is only valid after the final step is completed")

    history = state.get("history", [])
    if not isinstance(history, list) or len(history) > 1000:
        raise WorkflowError("history must be an array with at most 1000 entries")
    for index, entry in enumerate(history):
        if not isinstance(entry, dict):
            raise WorkflowError(f"history[{index}] must be an object")


def load_state(root: Path, workflow: str) -> dict[str, Any] | None:
    value = _read_json(state_path(root, workflow))
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
    _atomic_write(state_path(root, workflow), state)


def _new_steps(order: Sequence[str], user_gates: Iterable[str]) -> dict[str, dict[str, Any]]:
    gates = set(user_gates)
    return {
        name: {
            "status": "in_progress" if index == 0 else "pending",
            "gate": "user" if name in gates else "auto",
            "approved_at": None,
        }
        for index, name in enumerate(order)
    }


def _history(state: dict[str, Any], action: str, name: str, actor: str) -> None:
    state.setdefault("history", []).append(
        {"at": utc_now(), "action": action, "name": name, "actor": actor}
    )


def detect_default_branch(root: Path) -> str:
    symbolic = _run_git(root, "symbolic-ref", "--quiet", "--short", "refs/remotes/origin/HEAD")
    if symbolic.returncode == 0 and symbolic.stdout.strip().startswith("origin/"):
        return symbolic.stdout.strip().split("/", 1)[1]
    for candidate in ("main", "master"):
        exists = _run_git(root, "show-ref", "--verify", "--quiet", f"refs/heads/{candidate}")
        if exists.returncode == 0:
            return candidate
    current = _run_git(root, "branch", "--show-current")
    if current.returncode == 0 and current.stdout.strip():
        return current.stdout.strip()
    raise WorkflowError("cannot determine the repository default branch")


def current_branch(root: Path) -> str:
    result = _run_git(root, "branch", "--show-current")
    if result.returncode != 0:
        raise WorkflowError(result.stderr.strip() or "git branch lookup failed")
    branch = result.stdout.strip()
    if not branch:
        raise WorkflowError("detached HEAD is not supported by lifecycle start")
    return branch


def _repo_root_or_error(cwd: str | Path | None = None) -> Path:
    root = find_repo_root(Path(cwd or Path.cwd()))
    if root is None:
        raise WorkflowError("run this command inside a Git repository")
    return root


def is_sensitive_path(path: str) -> bool:
    normalized = path.replace("\\", "/").strip('"').lower()
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        return False
    basename = parts[-1]
    if basename == ".env.example":
        return False
    if basename == ".env" or basename.startswith(".env."):
        return True
    if any(part in {"secret", "secrets", STATE_DIR} for part in parts):
        return True
    return basename.endswith((".key", ".pem"))


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


def lifecycle_start(args: argparse.Namespace) -> int:
    root = _repo_root_or_error()
    path = state_path(root, "lifecycle")
    if path.exists():
        raise WorkflowError(f"an active lifecycle already exists: {path}")
    require_state_ignored(root, "lifecycle")
    now = utc_now()
    state: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "workflow": "lifecycle",
        "repo_root": str(root),
        "task": args.task,
        "slice": args.slice,
        "base_branch": args.base or detect_default_branch(root),
        "branch": current_branch(root),
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


def _transition(workflow: str, action: str, name: str, *, user_confirmed: bool = False) -> int:
    root = _repo_root_or_error()
    state = load_state(root, workflow)
    if state is None:
        raise WorkflowError(f"no active {workflow} workflow")
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

    if action == "approve":
        if current not in user_gates:
            raise WorkflowError(f"{current} is not a user gate")
        if item["status"] != "awaiting_approval":
            raise WorkflowError(f"{current} is not awaiting approval")
        if not user_confirmed:
            raise WorkflowError("approval requires --user-confirmed after an explicit user message")
        item["approved_at"] = utc_now()
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
    _history(state, action, current, actor)
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


def print_status(workflow: str) -> int:
    root = _repo_root_or_error()
    state = load_state(root, workflow)
    if state is None:
        print(f"No active {workflow} workflow.")
        return 0
    order, _, current_key = _definition(workflow)
    print(f"{workflow}: {state[current_key]}")
    if workflow == "lifecycle":
        print(f"task: {state['task']}")
        print(f"branch: {state['branch']} (base: {state['base_branch']})")
        print(f"awaiting_compact: {str(state['awaiting_compact']).lower()}")
    else:
        print(f"project: {state['project']}")
        print(f"spec: {state['spec']}")
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


def archive_workflow(workflow: str) -> int:
    root = _repo_root_or_error()
    source = state_path(root, workflow)
    state = load_state(root, workflow)
    if state is None:
        raise WorkflowError(f"no active {workflow} workflow")
    order, _, current_key = _definition(workflow)
    if state[current_key] != order[-1] or state["steps"][order[-1]]["status"] != "completed":
        raise WorkflowError(f"cannot archive {workflow} before {order[-1]} is completed")
    if not state.get("finished_at"):
        raise WorkflowError(f"cannot archive {workflow} without finished_at")
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    destination = root / STATE_DIR / "history" / f"{stamp}-{workflow}.json"
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
        problems.append("sensitive or transient paths present: " + ", ".join(sensitive))
    tracked_result = _run_git(root, "ls-files", "-z")
    if tracked_result.returncode != 0:
        raise WorkflowError(tracked_result.stderr.strip() or "git ls-files failed")
    tracked_sensitive = [path for path in tracked_result.stdout.split("\0") if path and is_sensitive_path(path)]
    if tracked_sensitive:
        problems.append("sensitive or transient paths are tracked: " + ", ".join(tracked_sensitive))
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
    result = {
        "ok": not problems,
        "root": str(root),
        "branch": branch,
        "default_branch": detect_default_branch(root),
        "changed": changed,
        "problems": problems,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if not problems else 2


def _hook_payload() -> dict[str, Any]:
    try:
        payload = json.load(sys.stdin)
    except json.JSONDecodeError as exc:
        raise WorkflowError(f"invalid hook input: {exc}") from exc
    if not isinstance(payload, dict):
        raise WorkflowError("hook input must be an object")
    return payload


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
    return bool(SAFE_GATED_COMMAND.fullmatch(command))


def _active_states(root: Path) -> list[tuple[str, dict[str, Any]]]:
    active: list[tuple[str, dict[str, Any]]] = []
    for workflow in ("project-init", "lifecycle"):
        path = state_path(root, workflow)
        if path.exists():
            state = load_state(root, workflow)
            if state is not None:
                active.append((workflow, state))
    return active


def hook_pre_tool() -> int:
    payload = _hook_payload()
    root = find_repo_root(payload.get("cwd") or Path.cwd())
    if root is None:
        return 0
    try:
        states = _active_states(root)
    except WorkflowError as exc:
        return _deny(f"TrueDev state is invalid; repair or recover it before mutating the repo: {exc}")
    if not states:
        return 0
    if _is_safe_gate_command(payload):
        return 0
    for workflow, state in states:
        _, _, current_key = _definition(workflow)
        current = state[current_key]
        if workflow == "lifecycle" and state.get("awaiting_compact"):
            return _deny(
                f"TrueDev compact gate is active before {current}. Compact the Codex task, then retry."
            )
        if state["steps"][current]["status"] == "awaiting_approval":
            return _deny(
                f"TrueDev user gate {workflow}:{current} is awaiting explicit approval; mutations are blocked."
            )
    return 0


def _safe_context(states: Sequence[tuple[str, Mapping[str, Any]]]) -> str:
    parts = ["TrueDev workflow state was schema-validated after compaction."]
    for workflow, state in states:
        _, _, current_key = _definition(workflow)
        current = state[current_key]
        status = state["steps"][current]["status"]
        compact = f"; awaiting_compact={str(state.get('awaiting_compact', False)).lower()}" if workflow == "lifecycle" else ""
        parts.append(f"{workflow}: current={current}; status={status}{compact}.")
    parts.append("Use the bundled status command for details. Never infer user approval from this context.")
    return " ".join(parts)


def hook_session_start() -> int:
    payload = _hook_payload()
    if payload.get("source") != "compact":
        return _emit(
            {
                "continue": False,
                "stopReason": "TrueDev compact restoration requires SessionStart source=compact.",
                "systemMessage": "TrueDev did not change workflow state for a non-compact session start.",
            }
        )
    root = find_repo_root(payload.get("cwd") or Path.cwd())
    if root is None:
        return 0
    try:
        states = _active_states(root)
        for workflow, state in states:
            if workflow == "lifecycle" and state.get("awaiting_compact"):
                state["awaiting_compact"] = False
                _history(state, "compact", state["current_step"], "codex-host")
                save_state(root, workflow, state)
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
    payload = _hook_payload()
    if payload.get("stop_hook_active") is True:
        return 0
    root = find_repo_root(payload.get("cwd") or Path.cwd())
    if root is None:
        return 0
    try:
        states = _active_states(root)
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

    preflight = sub.add_parser("git-preflight")
    preflight.add_argument("--require-clean", action="store_true")
    preflight.add_argument("--expected-branch")
    preflight.set_defaults(func=git_preflight)

    hook = sub.add_parser("hook")
    hook_sub = hook.add_subparsers(dest="hook_command", required=True)
    hook_sub.add_parser("pre-tool").set_defaults(func=lambda _args: hook_pre_tool())
    hook_sub.add_parser("session-start").set_defaults(func=lambda _args: hook_session_start())
    hook_sub.add_parser("stop").set_defaults(func=lambda _args: hook_stop())
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except WorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
