# TrueDev Workflow

**English** | [Русский](README.ru.md)

TrueDev Workflow is a native Codex plugin for long product and engineering tasks. It turns a
specification into durable project documents, then delivers one vertical slice at a time through
explicit scope, verification, review, and closeout gates.

## What is included

| Component | Purpose |
| --- | --- |
| `project-init` skill | Specification → requirements → PRD → architecture → phases → vertical slices → `AGENTS.md` |
| `lifecycle` skill | One slice through context, scope, plan, implementation, evidence, review, docs, and closeout |
| Codex hooks | Block common mutating tools at compact and user-approval gates; validate state at stop |
| Python runner | Cross-platform, schema-validated transitions, atomic state writes, archive receipts, and Git preflight |

The skills are stack-neutral. They discover repository commands and conventions instead of assuming
Node.js, React, npm, Vitest, Playwright, Storybook, Tailwind, or a `master` branch.

## Requirements

- Codex with plugin and hook support
- Git
- Python 3.9 or newer (`python3` on macOS/Linux; `python` on Windows)

Hooks are reviewed and trusted by hash in Codex. If hooks are unavailable or disabled, the skills and
runner still work, but automatic mutation blocking is absent.

![TrueDev workflow overview](docs/images/workflow-overview.png)

## Install

Add this repository as a marketplace and install the plugin:

```text
codex plugin marketplace add itpartypattaya/truedev-codex-workflow --ref main
codex plugin add truedev-workflow@truedev-workflow
```

Start a new Codex task after installation so the skills and hooks are loaded. Open `/hooks` in Codex
CLI to review and trust the bundled hook definitions.

For local development, add the checkout as a marketplace root:

```text
codex plugin marketplace add <absolute-path-to-this-checkout>
codex plugin add truedev-workflow@truedev-workflow
```

## Use

```text
$project-init Analyze docs/spec.md and prepare implementation-ready project documentation.
$project-init status

$lifecycle Start the next approved slice.
$lifecycle status
$lifecycle Continue the active step.
```

Approval is conversational in Codex. The skill opens a named gate, presents evidence, and stops.
After the user explicitly approves that phase or step, the skill records the approval through the
runner. Vague continuation is not treated as approval when the decision is unclear.

## Durable flow

```text
specification
  → INPUT_VALIDATION → PRD → ARCHITECTURE → PLANNING → DECOMPOSITION → FINALIZE
  → docs/plan/slice-NNN-*.md
  → CONTEXT_CHECK → SCOPE → PLAN → COMPONENTS → IMPLEMENT
  → TEST → VERIFY → REVIEW → DOCUMENT → CLOSE
```

An open gate also covers linked worktrees and enclosing checkouts such as submodules, so work done
from a sibling directory cannot slip past it.

Active state is stored below `.truedev-workflow/` at the repository root and is Git-ignored. The
runner serializes concurrent transitions, writes state atomically, rejects invalid transitions, and archives completed receipts below
`.truedev-workflow/history/`.

After PLAN, the lifecycle sets a compact gate. A real Codex compact session clears it and injects
only an allowlisted state summary. Task text and arbitrary state values are never elevated into
developer context.

## Enforcement boundary

Hooks are useful guardrails, not a security boundary. The pre-tool hook covers Codex shell commands,
`apply_patch`, subagents, and MCP tool calls matched by the plugin. Hosted tools and specialized tool
paths may not emit hook events. Repository permissions, sandboxing, protected branches, CI, and
provider-side authorization remain authoritative.

The detailed trust model, hook inputs, stored data, and limitations are documented in
[`SECURITY.md`](SECURITY.md). TrueDev has no telemetry or bundled network client; see
[`PRIVACY.md`](PRIVACY.md) for the complete data-handling statement.

If an active state file is malformed, matching mutating tool calls fail closed. Explicit
`abandon --user-confirmed` preserves its original bytes before a clean restart. A valid lifecycle
whose branch changed can be rebound only with `recover --accept-current-branch --user-confirmed`.
If no active state exists, the plugin is inert.

While a gate is open, evidence reads use the bundled `inspect git-status`, `inspect git-diff`, and
`inspect file` commands. Raw shell reads are blocked so Git helpers and PowerShell providers cannot
turn a nominally read-only exemption into code execution or an out-of-repository read.
The diff inspector omits high-confidence credential paths such as `.env`, private keys, credential
stores, `secrets/` directories, and transient workflow state; ordinary source names such as
`src/secrets.ts` are not blocked. It names every path it withheld, so a shortened diff is never
mistaken for a complete one.

Both platforms use the same launcher, which reads `PLUGIN_ROOT` inside Python instead of assuming
Command Prompt `%VAR%`, PowerShell `$env:VAR`, or POSIX shell expansion. The launcher requires an
absolute installed path: an unset or relative value makes it inert rather than resolving against the
repository under review or turning a bootstrap error into a repository-wide tool denial.

## Git safety

The workflow does not automatically pull, stage all files, commit, push, create or merge a PR,
delete branches, or remove worktrees. Before repository mutations it:

1. discovers the real default and current branches;
2. detects dirty or high-confidence credential/transient paths and in-progress Git operations;
3. preserves unrelated user changes;
4. requires explicit authority for external or destructive actions;
5. stages only task-owned files when a commit is authorized.

## Development

Run the deterministic test suite:

```text
python -m unittest discover -s tests -v
```

Validate the plugin and both skills with the built-in creators:

```text
python <plugin-creator>/scripts/validate_plugin.py .
python <skill-creator>/scripts/quick_validate.py skills/lifecycle
python <skill-creator>/scripts/quick_validate.py skills/project-init
```

Run the repository-owned release validation and build a deterministic public package:

```text
python scripts/validate_release.py
python scripts/package_plugin.py
```

The ZIP intentionally excludes marketplace metadata, tests, eval definitions/fixtures, screenshots,
and repository-only docs.
Skills-only submissions must not declare `interface.screenshots`; the review images under
`docs/images/` are separate submission/reference assets.

## Public release

The publisher checklist, five positive and three negative review cases, listing copy, and
owner-dependent Platform steps are in [`docs/public-submission.md`](docs/public-submission.md).
The final single-run benchmark and standalone evidence viewer are available in
[`evals/results/benchmark.md`](evals/results/benchmark.md) and
[`evals/results/review.html`](evals/results/review.html).
Support is handled through [`SUPPORT.md`](SUPPORT.md) and GitHub Issues.

## License

MIT. The original upstream copyright and license are preserved in [`LICENSE`](LICENSE).
