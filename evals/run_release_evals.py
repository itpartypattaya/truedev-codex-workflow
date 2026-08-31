#!/usr/bin/env python3
"""Run independent Codex with-skill and baseline release evaluations."""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
EVALS_PATH = ROOT / "evals" / "plugin" / "evals.json"
DEFAULT_WORKSPACE = ROOT / "evals" / "workspace" / "iteration-1"


def codex_command() -> list[str]:
    override = os.environ.get("CODEX_EVAL_COMMAND")
    if override:
        return [override]
    if os.name == "nt":
        node = shutil.which("node")
        cli = Path.home() / "AppData" / "Roaming" / "npm" / "node_modules" / "@openai" / "codex" / "bin" / "codex.js"
        if node and cli.is_file():
            return [node, str(cli)]
    executable = shutil.which("codex")
    if not executable:
        raise RuntimeError("codex CLI was not found; set CODEX_EVAL_COMMAND")
    return [executable]


def load_evals() -> list[dict[str, Any]]:
    data = json.loads(EVALS_PATH.read_text(encoding="utf-8"))
    return data["evals"]


def prepare_fixture(workspace: Path) -> Path:
    fixture = workspace / "fixture"
    fixture.mkdir(parents=True, exist_ok=True)
    (fixture / "src").mkdir(exist_ok=True)
    (fixture / "docs" / "plan").mkdir(parents=True, exist_ok=True)
    (fixture / "AGENTS.md").write_text(
        "# Eval repository\n\nUse Makefile commands. Preserve unknown changes. "
        "Do not claim a check ran unless evidence exists.\n",
        encoding="utf-8",
    )
    (fixture / "Makefile").write_text("lint:\n\t@echo lint\n\ntest:\n\tgo test ./...\n", encoding="utf-8")
    (fixture / "src" / "billing.py").write_text("# existing unknown user change\n", encoding="utf-8")
    (fixture / "docs" / "plan" / "slice-004-billing.md").write_text(
        "# Slice 004\n\nAdd billing validation without changing unrelated work.\n",
        encoding="utf-8",
    )
    return fixture


def skill_instruction(item: dict[str, Any]) -> str:
    skill = item.get("skill")
    if skill:
        path = ROOT / "skills" / skill / "SKILL.md"
        return (
            f"Read and follow the TrueDev skill at {path}. Read only the references it routes to for "
            "this scenario. The skill is the configuration under evaluation."
        )
    lifecycle = ROOT / "skills" / "lifecycle" / "SKILL.md"
    project_init = ROOT / "skills" / "project-init" / "SKILL.md"
    return (
        f"Read the routing descriptions in {lifecycle} and {project_init}, then decide whether either "
        "TrueDev skill should activate. Do not force activation for a near-miss request."
    )


def make_prompt(item: dict[str, Any], configuration: str) -> str:
    common = (
        "This is a read-only behavior evaluation. Do not modify files. You may read files and use "
        "read-only inspection commands. Respond as if you were about to handle the request in this "
        "repository. State the exact first "
        "actions, named blockers or approvals, and what mutation authority exists. Do not claim a command "
        "or check actually ran.\n\n"
    )
    if configuration == "with_skill":
        setup = skill_instruction(item)
    else:
        setup = "Use default Codex behavior. Do not read or invoke the TrueDev skills in the parent repository."
    return f"{common}{setup}\n\nUSER REQUEST:\n{item['prompt']}"


def extract_total_tokens(events: str) -> int:
    maximum = 0

    def visit(value: Any) -> None:
        nonlocal maximum
        if isinstance(value, dict):
            input_tokens = value.get("input_tokens")
            output_tokens = value.get("output_tokens")
            if isinstance(input_tokens, int) and isinstance(output_tokens, int):
                maximum = max(maximum, input_tokens + output_tokens)
            for key, child in value.items():
                if key == "total_tokens" and isinstance(child, int):
                    maximum = max(maximum, child)
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    for line in events.splitlines():
        try:
            visit(json.loads(line))
        except json.JSONDecodeError:
            continue
    return maximum


def run_one(item: dict[str, Any], configuration: str, fixture: Path, workspace: Path) -> None:
    eval_dir = workspace / item["id"]
    run_dir = eval_dir / configuration
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True, exist_ok=True)
    metadata = {
        "eval_id": item["id"],
        "eval_name": item["id"].replace("-", " ").title(),
        "prompt": item["prompt"],
        "assertions": item["assertions"],
    }
    (eval_dir / "eval_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    response_path = outputs / "response.md"
    response_path.unlink(missing_ok=True)
    command = [
        *codex_command(),
        "exec",
        "--ephemeral",
        "--ignore-user-config",
        "--sandbox",
        "read-only",
        "--skip-git-repo-check",
        "--json",
        "-C",
        str(fixture),
        "-o",
        str(response_path),
        "-",
    ]
    start_wall = dt.datetime.now(dt.timezone.utc)
    start = time.perf_counter()
    result = subprocess.run(
        command,
        input=make_prompt(item, configuration),
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    duration = time.perf_counter() - start
    end_wall = dt.datetime.now(dt.timezone.utc)
    (run_dir / "transcript.jsonl").write_text(result.stdout, encoding="utf-8")
    (run_dir / "stderr.txt").write_text(result.stderr, encoding="utf-8")
    timing = {
        "total_tokens": extract_total_tokens(result.stdout),
        "duration_ms": round(duration * 1000),
        "total_duration_seconds": round(duration, 3),
        "executor_start": start_wall.isoformat(),
        "executor_end": end_wall.isoformat(),
        "executor_duration_seconds": round(duration, 3),
        "exit_code": result.returncode,
    }
    (run_dir / "timing.json").write_text(
        json.dumps(timing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if result.returncode != 0 or not response_path.is_file() or response_path.stat().st_size == 0:
        raise RuntimeError(f"{item['id']} {configuration} failed with exit code {result.returncode}")
    print(f"PASS executor {item['id']} {configuration}: {duration:.1f}s, {timing['total_tokens']} tokens", flush=True)


def completed_run(workspace: Path, eval_id: str, configuration: str) -> bool:
    run_dir = workspace / eval_id / configuration
    output = run_dir / "outputs" / "response.md"
    timing_path = run_dir / "timing.json"
    if not output.is_file() or output.stat().st_size == 0 or not timing_path.is_file():
        return False
    try:
        timing = json.loads(timing_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return False
    return timing.get("exit_code") == 0 and timing.get("total_tokens", 0) > 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=DEFAULT_WORKSPACE)
    parser.add_argument("--configuration", choices=("all", "with_skill", "without_skill"), default="all")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--eval-id")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)
    fixture = prepare_fixture(workspace)
    items = load_evals()[: args.limit]
    if args.eval_id:
        items = [item for item in items if item["id"] == args.eval_id]
        if not items:
            parser.error(f"unknown --eval-id: {args.eval_id}")
    configurations = ("with_skill", "without_skill") if args.configuration == "all" else (args.configuration,)
    try:
        for item in items:
            for configuration in configurations:
                if args.resume and completed_run(workspace, item["id"], configuration):
                    print(f"SKIP existing {item['id']} {configuration}", flush=True)
                    continue
                run_one(item, configuration, fixture, workspace)
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
