---
name: lifecycle
description: Run a planned software slice or scoped bug fix through safe context checking, scope approval, planning, implementation, testing, verification, review, documentation, and closeout. Use whenever the user asks to start or continue a feature lifecycle, implement the next slice, fix a bug within an active delivery workflow, check workflow status, resume after compaction, or enforce approval gates during a long Codex coding task. Do not use for a one-off explanation or read-only review that is not part of an active delivery workflow.
---

# TrueDev Lifecycle

Deliver one vertical slice at a time while keeping scope, approvals, and repository state explicit.
The workflow state is durable, but hooks are guardrails rather than a security boundary. Never claim
that a gate is impossible to bypass.

## Requirements

Require Git and Python 3.9 or newer. Treat installed Codex hooks as optional, user-trusted
guardrails.

## Locate the bundled runner

Let `<SKILL_DIR>` be the directory containing this `SKILL.md`. Its grandparent is `<PLUGIN_ROOT>`:

```text
<PLUGIN_ROOT>/scripts/truedev_workflow.py
```

Use `python3` on macOS/Linux and `python` on Windows. Do not edit state JSON directly. The runner
validates transitions, writes atomically, and resolves the repository root from nested directories.
Resolve all `references/...` paths relative to `<SKILL_DIR>`, never relative to the plugin root or
the user's repository.

## Route the request

- **status or no explicit action:** run `lifecycle status`, report the table, and make no changes.
- **start `<task>`:** initialize a lifecycle after the repository preflight.
- **next:** ask the runner which slice is ready with
  `project-init next-slice [--plan-dir <plan-dir>]`, then follow `start` with the file it names.
  When it exits non-zero, report its `reason`, the `blocked` list, and any `unrecognized_status`
  entries, and stop. Never choose a slice by listing the directory yourself, and never skip a
  blocked dependency.
- **approve `<STEP>`:** only after the user's latest message explicitly approves that exact gate,
  run `lifecycle complete --step <STEP> --user-confirmed`.
- **ambiguous response at a user gate:** do not transition. Name the gate and ask the user to approve
  it or reject/request revisions to the presented evidence.
- **continue/resume:** validate state, then recover the task itself from durable artifacts — the
  slice file named by `status`, its acceptance criteria, and the repository documents it points to.
  The restored summary carries enum values only, never task text, so it tells you where you are and
  never what the work is. Then read only the current section of
  `<SKILL_DIR>/references/steps.md` and continue that step.
- **bug or failing check:** reproduce it, trace the root cause, add the smallest regression test that
  fails for that cause, then make the narrowest fix. Keep these actions inside the normal ordered steps.
- **recover after a branch change:** stop mutation, show the recorded and active branches, and use
  `recover --accept-current-branch --user-confirmed` only after explicit approval. Never recover
  onto detached HEAD or a repository whose Git metadata is missing; restore a named branch first, or
  offer `abandon --user-confirmed`.
- **invalid or obsolete state:** do not fabricate approvals. Offer `abandon --user-confirmed`, which
  preserves the original state in history before allowing a clean restart.
- **compact event unavailable:** explain the missing host evidence and use
  `skip-compact --user-confirmed` only after the user explicitly accepts bypassing that checkpoint.
  Never run it on your own initiative to get past a block; `status` prints the bypass afterwards.

If a runner command fails, report the error once. Do not retry by weakening validation or editing the
state file manually.

## Start safely

1. Run `<PYTHON> <RUNNER> --help` and stop if the required runner cannot start. A missing interpreter
   means hook enforcement is unavailable; do not create active state and imply gates are enforced.
2. Read the nearest applicable `AGENTS.md`, the selected slice, and the repository's own command
   sources — its `Makefile`, package manifest, and CI configuration — then run `project-config show`
   for the commands the user has already confirmed. These are reads; they change nothing. Name every
   file you actually read: the confirmed configuration replaces guessing, not reading the project.
   Record only successful reads; follow the CONTEXT_CHECK evidence rules in `references/steps.md`.
3. Run `git-preflight --require-clean`. A dirty tree may contain user work; stop and agree ownership
   instead of stashing, resetting, committing, or deleting it.
4. Only now, if `truedev.project.json` was missing, run `detect` and follow the adoption dialogue in
   `references/project-config.md` — commands, then the unit runner, then the browser and
   integration layers when detection names them — and write the answers with
   `project-config init ... --user-confirmed`. This order is not optional: the file is a task-owned
   change, and writing it before the clean-tree preflight would make that preflight fail on the
   workflow's own edit. Never write it without asking, and never fall back to a guessed stack.
5. Ensure `.truedev-workflow/` is ignored by Git. If it is missing, add the narrow ignore rule as a
   task-owned change; never start with tracked or potentially committable state.
6. Detect the default branch only from a valid `origin/HEAD`. If Git cannot identify it
   authoritatively, obtain an explicit `--base` from the user; never infer `main`, `master`, or the
   current branch, and do not pull automatically.
7. For implementation work, create a dedicated local branch or worktree only when this is within the
   user's request. Never switch branches across unrelated user changes.
8. Run:

```text
python3 <RUNNER> lifecycle start --task "<task>" --slice "<plan-dir>/slice-NNN-name.md"
```

`--slice` is a repository-relative path. It may use the default `docs/plan/` directory or the same
custom plan directory recorded as `plan_dir` in `truedev.project.json`. Each directory component
must contain only ASCII letters, digits, `.`, `_`, or `-`, because this validated reference is restored
after context compaction.

9. Keep Codex's task plan synchronized with the current workflow step when a plan tool is available.

## Commands

One vocabulary, used in this file, in the README, and by the runner. `approve` and `complete`
are the same command; so are `release-compact` and `skip-compact`. Prefer the second name of each
pair when speaking to the user — it is the one the status line prints.

| Command | What it does |
| --- | --- |
| `lifecycle start --task "<task>" --slice "<plan-dir>/slice-NNN-name.md"` | Open a lifecycle for one slice, after the preflight |
| `lifecycle status` | Where this workflow is: the step table, the open gate, and the one next action |
| `lifecycle gate --step <STEP>` | Present the evidence and stop at a user gate |
| `lifecycle complete --step <STEP> --user-confirmed` | The user's approval of that exact gate. The only thing that clears one |
| `lifecycle finish --step <STEP>` | Close an automatic step whose work is done |
| `lifecycle skip --step COMPONENTS --reason non-ui` | Record that the slice has no UI surface |
| `lifecycle skip-compact --user-confirmed` | The user's deliberate bypass of the compact checkpoint. Recorded, and printed by `status` afterwards |
| `lifecycle recover --accept-current-branch --user-confirmed` | Rebind a valid workflow to the branch it is actually on |
| `lifecycle abandon --user-confirmed` | Archive the original state and clear the workflow |
| `lifecycle archive` | Close out an approved CLOSE and free the slot for the next slice |
| `project-init next-slice [--plan-dir <plan-dir>]` | Which slice is ready, and why the others are not |
| `detect` / `project-config show` | What the repository is, and the commands the user confirmed |

## Transition commands

Use these commands; never represent a transition by hand-editing JSON:

```text
python3 <RUNNER> lifecycle status
python3 <RUNNER> lifecycle validate
python3 <RUNNER> lifecycle finish --step <AUTO_STEP>
python3 <RUNNER> lifecycle gate --step <USER_GATE>
python3 <RUNNER> lifecycle complete --step <USER_GATE> --user-confirmed
python3 <RUNNER> lifecycle skip --step COMPONENTS --reason non-ui
python3 <RUNNER> lifecycle recover --accept-current-branch --user-confirmed
python3 <RUNNER> lifecycle skip-compact --user-confirmed
python3 <RUNNER> lifecycle abandon --user-confirmed
python3 <RUNNER> lifecycle archive
```

Before `gate`, finish the work and present the evidence the user needs to decide. After `gate`, stop
mutating the repository until approval. A vague “continue” does not approve a named gate when the
decision or consequences are unclear.

While a gate is open, use only the runner's validation/status commands or its hardened inspection
commands. Raw shell reads and raw Git inspection remain blocked because Git helpers and PowerShell
providers can execute code or escape repository paths:

```text
python3 <RUNNER> inspect git-status
python3 <RUNNER> inspect git-diff [--staged] [--stat|--check|--name-only|--name-status]
python3 <RUNNER> inspect file --path <repository-relative-non-sensitive-file>
python3 <RUNNER> detect
python3 <RUNNER> project-config show
python3 <RUNNER> project-init next-slice [--plan-dir <plan-dir>]
```

The file inspector accepts only regular UTF-8 files inside the Git root, rejects symlinks and
high-confidence credential paths, and caps output size. Git-diff inspection omits those paths and
prints the list of what it withheld; treat that list as a gap in the evidence rather than as an
empty change set. Chaining, redirection, and writes remain blocked.

## Step order

`CONTEXT_CHECK → SCOPE → PLAN → COMPONENTS → IMPLEMENT → TEST → VERIFY → REVIEW → DOCUMENT → CLOSE`

Read `<SKILL_DIR>/references/steps.md` only for the active step. Read
`<SKILL_DIR>/references/state-schema.md` when diagnosing state validation or recovery, and
`<SKILL_DIR>/references/project-config.md` when adopting or reading the project's command
configuration. Keep the main context focused on the active slice.

## Universal safety rules

- Take build, lint, test, and E2E commands from `truedev.project.json` once the user has confirmed
  them; until then, discover them from repository documentation and configuration and ask. A `null`
  command means that layer does not exist in this project: say so instead of inventing one. Do not
  assume npm, Vitest, Playwright, React, Storybook, or any other stack.
- Treat existing and unrelated changes as user-owned. Stage only files owned by the current task.
- Do not automatically commit, push, create a PR, merge, delete branches, or remove worktrees. Perform
  each external or destructive action only when the user has authorized that exact class of action.
  If several such actions are bundled together or the user refuses an evidence checkpoint, stop after
  presenting the exact diff and release state. Request an explicit decision for each still-pending
  action: commit, push, PR creation or merge, and branch or worktree deletion, as applicable.
- Before any commit or push, rerun `git-preflight`, inspect the intended staged diff, and scan it for
  secrets and transient workflow files.
  At a release checkpoint, name all three checks explicitly in the evidence or requested next actions;
  showing a general diff or file list does not substitute for staged-diff review and a secret scan.
- Keep published or otherwise immutable project data immutable. Use the repository's migration and
  compatibility contracts.
- Distinguish static, unit, integration, E2E, staging, and live evidence. Never imply an unavailable
  layer passed.
- Missing optional tools reduce evidence; they do not justify invented results or weakened gates. A
  layer that is not configured — an external reviewer, an E2E suite — is reported as absent in the
  evidence, never omitted from it.
- Use subagents only when host policy and the user's request permit them. The workflow must work with
  one agent.

## Closeout

When `CLOSE` is explicitly approved and all authorized actions are complete, mark it approved and run
`lifecycle archive`. Archiving preserves the validated receipt under `.truedev-workflow/history/` and
removes the active state so `next` can begin another slice.
