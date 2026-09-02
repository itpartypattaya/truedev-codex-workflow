---
name: project-init
description: Turn a product or engineering specification into durable requirements, a PRD, architecture decisions, an implementation plan, and dependency-ordered vertical slices. Use whenever the user asks Codex to analyze a spec or ТЗ, initialize a project from requirements, create a PRD or architecture plan, decompose a project into slices, or prepare structured implementation documentation. Do not use for implementing an already-approved slice; use lifecycle for that.
---

# TrueDev Project Init

Convert an input specification into an approved, implementation-ready contract. Decisions live in
files; conversation context is not the source of truth.

## Requirements

Require Python 3.9 or newer and Git. `project-init start` resolves the repository root through
Git and refuses to begin unless `.truedev-workflow/` is Git-ignored, so Git is a hard
requirement rather than an optional convenience.

## Locate the bundled runner

Let `<SKILL_DIR>` be the directory containing this `SKILL.md`. Its grandparent is `<PLUGIN_ROOT>`,
then use:

```text
<PLUGIN_ROOT>/scripts/truedev_workflow.py
```

Use `python3` on macOS/Linux and `python` on Windows. Never edit
`.truedev-workflow/project-init.json` directly.
Resolve all `references/...` paths relative to `<SKILL_DIR>`, never relative to the plugin root or
the user's repository.

## Route the request

- **status or no explicit action:** run `project-init status` and make no changes.
- **start `<spec>`:** inspect the spec and existing docs, then initialize state.
- **existing repository:** run `detect`, present the artifacts and stack it found, and offer to
  enter at the phase it suggests instead of regenerating documents the project already has.
- **next slice:** run `project-init next-slice [--plan-dir <plan-dir>]` and hand the file it names
  to `$lifecycle`. Report its `reason` and `blocked` list when it exits non-zero.
- **approve `<PHASE>`:** only after the latest user message explicitly approves the exact phase,
  run `project-init approve --phase <PHASE> --user-confirmed`.
- **continue/resume:** validate state and read only the active phase in
  `<SKILL_DIR>/references/phases.md`.
- **invalid or obsolete state:** infer nothing and do not fabricate approvals. Offer
  `abandon --user-confirmed`, which preserves the original state before a clean restart.

## Start

1. Run `<PYTHON> <RUNNER> --help` and stop if the runner cannot start. Do not create active state when
   hook enforcement and validated transitions would be unavailable.
2. Read applicable `AGENTS.md`, the specification, and existing `docs/` artifacts.
   If host policy rejects a combined or piped read command, retry each required file with a separate
   read-only operation. A rejected read is not evidence that the file was inspected.
3. If a target artifact exists, show the conflict and obtain permission before overwriting or
   materially restructuring it.
4. Ensure `.truedev-workflow/` is ignored by Git. Refuse tracked or potentially committable state.
5. Run `detect`. When it reports a `suggested_entry_phase` later than `INPUT_VALIDATION`, list the
   artifacts that justify it and ask the user whether to adopt those phases as already done. Start
   at a later phase only with that explicit confirmation; never skip a phase silently, and never
   claim an adopted artifact was reviewed by this workflow.
6. Run:

```text
python3 <RUNNER> project-init start --project "<name>" --spec "<source>"
python3 <RUNNER> project-init start --project "<name>" --spec "<source>" \
  --from <PHASE> --user-confirmed
```

7. Execute the entry phase using its contract in `references/phases.md`, write the proposed
   artifact, present open questions, then open its gate.

## Transition commands

```text
python3 <RUNNER> project-init status
python3 <RUNNER> project-init validate
python3 <RUNNER> project-init finish --phase FINALIZE
python3 <RUNNER> project-init gate --phase <USER_PHASE>
python3 <RUNNER> project-init approve --phase <USER_PHASE> --user-confirmed
python3 <RUNNER> project-init validate-slices --plan-dir docs/plan
python3 <RUNNER> project-init next-slice --plan-dir docs/plan
python3 <RUNNER> project-init abandon --user-confirmed
python3 <RUNNER> project-init archive
```

Before opening a gate, ensure the durable artifact contains the decisions and evidence the user is
approving. Once a gate is open, mutating repository tools are blocked by the optional hooks.
Use only the bundled `inspect git-status`, `inspect git-diff`, `inspect file --path <path>`,
`detect`, and `project-config show` commands for additional evidence while a gate is open; raw
shell and Git reads are intentionally blocked.

## Phase order and artifacts

1. `INPUT_VALIDATION` → `docs/REQUIREMENTS.md`
2. `PRD` → `docs/prd.md`
3. `ARCHITECTURE` → `docs/architecture.md` and UI design artifacts only when relevant
4. `PLANNING` → `docs/plan/phase-N.md`
5. `DECOMPOSITION` → `docs/plan/slice-NNN-*.md`
6. `FINALIZE` → concise `AGENTS.md` integration and ignore rules

Read only the active section in `<SKILL_DIR>/references/phases.md`. Use
`<SKILL_DIR>/references/artifact-templates.md` when creating a new artifact; preserve an established
project format when one already exists.

## Decision and research rules

- Be advisory, not prescriptive. Present options, trade-offs, and a recommendation grounded in the
  actual product, team, repository, and operating constraints.
- Do not hardcode a framework, architecture style, package manager, design system, test framework,
  deployment provider, or default branch.
- Cover the validation, error handling, security/privacy, observability, operations, and testability
  concerns that are material to this system. Mark a concern inapplicable instead of silently omitting it.
- Turn testability into concrete requirements before choosing a framework: define expected unit and
  integration or contract coverage, invalid-input and boundary cases, material security and failure-mode
  checks, and the evidence required for acceptance. Add performance, resilience, migration, or E2E
  coverage when the system makes those concerns material.
- Verify versions only when a version decision is required. Use current primary documentation and
  record the verification date; avoid “latest” without a source.
- When legal, privacy, security, financial, medical, or regulatory requirements are material,
  research current authoritative sources, cite them, identify jurisdiction and date, and label
  remaining professional sign-off. Otherwise record `N/A` with a reason; do not perform ceremonial
  research or convert a web summary into legal approval.
- Use optional external research only when it materially improves a decision and is within the user's
  request. Missing tools are an evidence limitation, not permission to invent facts.
- A frontend project needs appropriate accessibility, responsive behavior, component states, and
  visual verification. It does not automatically need React, Tailwind, shadcn, Storybook, or a large
  multi-agent design ceremony.
- Use subagents only when host policy and the user's request permit them. The workflow must remain
  usable by one Codex agent.

## Finalize

Merge a concise project-specific section into `AGENTS.md`; do not overwrite unrelated instructions.
Ensure `.truedev-workflow/` and secrets are ignored without duplicating patterns. Finish FINALIZE,
archive the receipt, and hand the first approved slice to `$lifecycle`.
