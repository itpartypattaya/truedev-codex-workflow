---
name: lifecycle
description: Run a planned software slice through safe context checking, scope approval, planning, implementation, verification, testing, review, documentation, and closeout. Use whenever the user asks to start or continue a feature lifecycle, implement the next slice, check workflow status, resume after compaction, or enforce approval gates during a long Codex coding task. Do not use for a one-off explanation or read-only review that is not part of an active delivery workflow.
compatibility: Requires Git and Python 3.9 or newer. Codex hooks are optional guardrails and require user trust after installation.
---

# TrueDev Lifecycle

Deliver one vertical slice at a time while keeping scope, approvals, and repository state explicit.
The workflow state is durable, but hooks are guardrails rather than a security boundary. Never claim
that a gate is impossible to bypass.

## Locate the bundled runner

Resolve this skill's plugin root by walking two directories up from this `SKILL.md`. The runner is:

```text
<PLUGIN_ROOT>/scripts/truedev_workflow.py
```

Use `python3` on macOS/Linux and `py -3` on Windows. Do not edit state JSON directly. The runner
validates transitions, writes atomically, and resolves the repository root from nested directories.

## Route the request

- **status or no explicit action:** run `lifecycle status`, report the table, and make no changes.
- **start `<task>`:** initialize a lifecycle after the repository preflight.
- **next:** select the first pending `docs/plan/slice-*.md` whose dependencies are completed, then
  follow `start`; do not silently skip blocked dependencies.
- **approve `<STEP>`:** only after the user's latest message explicitly approves that exact gate,
  run `lifecycle approve --step <STEP> --user-confirmed`.
- **continue/resume:** validate state, read only the current section of `references/steps.md`, and
  continue that step.
- **recover:** stop automatic mutation. Reconstruct evidence from Git, docs, and test results; show
  the proposed state to the user before creating or changing any state file.

If a runner command fails, report the error once. Do not retry by weakening validation or editing the
state file manually.

## Start safely

1. Run `<PYTHON> <RUNNER> --help` and stop if the required runner cannot start. A missing interpreter
   means hook enforcement is unavailable; do not create active state and imply gates are enforced.
2. Read the nearest applicable `AGENTS.md` files and the selected slice.
3. Run `git-preflight --require-clean`. A dirty tree may contain user work; stop and agree ownership
   instead of stashing, resetting, committing, or deleting it.
4. Ensure `.truedev-workflow/` is ignored by Git. If it is missing, add the narrow ignore rule as a
   task-owned change; never start with tracked or potentially committable state.
5. Detect the default branch from Git. Do not assume `main` or `master`, and do not pull automatically.
6. For implementation work, create a dedicated local branch or worktree only when this is within the
   user's request. Never switch branches across unrelated user changes.
7. Run:

```text
python3 <RUNNER> lifecycle start --task "<task>" --slice "<slice-file>"
```

8. Keep Codex's task plan synchronized with the current workflow step when a plan tool is available.

## Transition commands

Use these commands; never represent a transition by hand-editing JSON:

```text
python3 <RUNNER> lifecycle status
python3 <RUNNER> lifecycle validate
python3 <RUNNER> lifecycle finish --step <AUTO_STEP>
python3 <RUNNER> lifecycle gate --step <USER_GATE>
python3 <RUNNER> lifecycle approve --step <USER_GATE> --user-confirmed
python3 <RUNNER> lifecycle archive
```

Before `gate`, finish the work and present the evidence the user needs to decide. After `gate`, stop
mutating the repository until approval. A vague “continue” does not approve a named gate when the
decision or consequences are unclear.

## Step order

`CONTEXT_CHECK → SCOPE → PLAN → COMPONENTS → IMPLEMENT → VERIFY → TEST → REVIEW → DOCUMENT → CLOSE`

Read `references/steps.md` only for the active step. Read `references/state-schema.md` when diagnosing
state validation or recovery. Keep the main context focused on the active slice.

## Universal safety rules

- Discover build, lint, format, test, and E2E commands from repository documentation and configuration.
  Do not assume npm, Vitest, Playwright, React, Storybook, or any other stack.
- Treat existing and unrelated changes as user-owned. Stage only files owned by the current task.
- Do not automatically commit, push, create a PR, merge, delete branches, or remove worktrees. Perform
  each external or destructive action only when the user has authorized that exact class of action.
- Before any commit or push, rerun `git-preflight`, inspect the intended staged diff, and scan it for
  secrets and transient workflow files.
- Keep published or otherwise immutable project data immutable. Use the repository's migration and
  compatibility contracts.
- Distinguish static, unit, integration, E2E, staging, and live evidence. Never imply an unavailable
  layer passed.
- Missing optional tools reduce evidence; they do not justify invented results or weakened gates.
- Use subagents only when host policy and the user's request permit them. The workflow must work with
  one agent.

## Closeout

When `CLOSE` is explicitly approved and all authorized actions are complete, mark it approved and run
`lifecycle archive`. Archiving preserves the validated receipt under `.truedev-workflow/history/` and
removes the active state so `next` can begin another slice.
