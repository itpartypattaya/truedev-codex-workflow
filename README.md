# TrueDev Workflow

**English** | [Русский](README.ru.md)

A Codex plugin that keeps a long task from drifting.

On a task that runs for hours, an agent tends to wander. It edits files nobody asked about, calls
work finished without running anything, and commits or pushes on its own initiative. TrueDev breaks
the work into named steps and stops at the ones that matter, waiting for you to say yes out loud.
Until you do, changes to the repository are blocked — not by the agent promising to behave, but by
Codex hooks that refuse the tool call.

![TrueDev workflow overview](docs/images/workflow-overview.png)

## What you get

| Component | What it does |
| --- | --- |
| `project-init` skill | Turns a specification into requirements, a PRD, architecture decisions, phases, and dependency-ordered slices |
| `lifecycle` skill | Walks one slice from context through scope, plan, implementation, tests, review, docs, and closeout |
| Codex hooks | Refuse file-changing tools while a gate is open, and check the state file when a turn ends |
| Python runner | Owns the state file: validated transitions, atomic writes, an archive of finished work, and a Git safety check |

The skills do not assume a stack. They read your repository to find out how it builds and tests
itself rather than reaching for npm, React, Vitest, Playwright, or a `master` branch.

## Requirements

- Codex with plugin and hook support
- Git
- Python 3.9 or newer — `python3` on macOS and Linux, `python` on Windows

Codex shows you each hook and asks you to trust it by hash. Without trusted hooks the skills and the
runner still work, but nothing blocks changes automatically.

## Install

```text
codex plugin marketplace add itpartypattaya/truedev-codex-workflow --ref main
codex plugin add truedev-workflow@truedev-workflow
```

Start a new Codex task afterwards so the skills and hooks load. Open `/hooks` in the Codex CLI to
review the bundled hooks and trust them.

To work on the plugin itself, point the marketplace at your checkout:

```text
codex plugin marketplace add <absolute-path-to-this-checkout>
codex plugin add truedev-workflow@truedev-workflow
```

## Using it

```text
$project-init Analyze docs/spec.md and prepare implementation-ready project documentation.
$project-init status

$lifecycle Start the next approved slice.
$lifecycle status
$lifecycle Continue the active step.
```

Approvals happen in conversation. At a gate the skill shows you what it did, states what it wants to
do next, and stops. When you approve that specific step, the skill records it through the runner. A
vague "go on" does not count as approval when the decision is unclear — you have to name the thing
you are approving.

## The flow

```text
specification
  → INPUT_VALIDATION → PRD → ARCHITECTURE → PLANNING → DECOMPOSITION → FINALIZE
  → docs/plan/slice-NNN-*.md
  → CONTEXT_CHECK → SCOPE → PLAN → COMPONENTS → IMPLEMENT
  → TEST → VERIFY → REVIEW → DOCUMENT → CLOSE
```

`project-init` produces the plan once. `lifecycle` then runs per slice. Five of its ten steps are
gates that wait for you: SCOPE, COMPONENTS, VERIFY, REVIEW, and CLOSE.

The pieces fit together like this. The agent drives the skills, the skills drive the runner, the
runner owns the state file, and the hooks sit in front of every tool call to check the current gate:

![How TrueDev fits together: hooks, agent, skills, and the state machine](docs/images/architecture.png)

After PLAN the lifecycle asks you to compact the Codex session, because the plan is long and the
implementation should not carry it. Compacting clears that gate and hands the next session a short
summary — the workflow name, the current step, its status, and the slice file. Your task text and
raw state never make it into that summary. If your Codex build does not emit a compact event, you
can release the gate deliberately with `lifecycle release-compact --user-confirmed`.

## Where state lives

Everything active sits in `.truedev-workflow/` at the repository root, and it must be Git-ignored —
the runner refuses to start otherwise. Transitions are serialized, writes are atomic, invalid
transitions are rejected, and finished work is archived under `.truedev-workflow/history/`.

An open gate also covers linked worktrees and nested checkouts such as submodules, so moving to a
sibling directory does not get you past it.

If the state file is damaged, matching tool calls fail closed until you fix it. `abandon
--user-confirmed` saves the original bytes before clearing the workflow. If the branch changed under
a valid workflow, `recover --accept-current-branch --user-confirmed` rebinds it. With no active
state, the plugin does nothing at all.

## What the gates actually enforce

Hooks are guardrails, not a security boundary — please do not treat them as one. The pre-tool hook
sees Codex shell commands, `apply_patch`, subagents, and MCP calls that match the plugin's pattern.
Hosted tools and specialized tool paths may not emit hook events at all. Your repository
permissions, sandboxing, protected branches, CI, and provider-side authorization are what actually
hold the line.

While a gate is open the agent can still gather evidence, but only through the bundled `inspect
git-status`, `inspect git-diff`, and `inspect file` commands. Raw shell reads are blocked, because
Git helpers and PowerShell providers can turn a supposedly read-only command into code execution or
a read outside the repository. The diff inspector leaves out likely credential files and tells you
which ones it left out, so a short diff is never mistaken for a complete one.

A few details worth knowing; [`SECURITY.md`](SECURITY.md) has the full trust model:

- One launcher serves both platforms. It reads `PLUGIN_ROOT` inside Python and insists on an
  absolute installed path, so a broken installation does nothing instead of running a same-named
  script out of the repository you are reviewing.
- The state directory has to be a real directory inside the repository. A symlink or a Windows
  junction anywhere in that path is refused for reads and writes alike.
- Stored text carries no line breaks and status prints one field per line, so text from the
  repository cannot fake the status the model reads.
- The starting commit is recorded. The guard still compares branch identity, but `status` flags the
  commit as `MOVED` when history is rewritten under an unchanged branch name.
- Output is UTF-8 whatever the console code page says.

There is no telemetry and no bundled network client; [`PRIVACY.md`](PRIVACY.md) states exactly what
is stored and where.

## Git safety

The workflow never pulls, stages everything, commits, pushes, opens or merges a PR, deletes a
branch, or removes a worktree on its own. Before it touches the repository it:

1. finds the real default and current branches instead of guessing;
2. looks for uncommitted work, likely credential files, and a Git operation already in progress;
3. leaves changes it does not own alone;
4. asks for explicit permission for anything external or destructive;
5. stages only the files belonging to the current task when you authorize a commit.

## Development

Run the test suite:

```text
python -m unittest discover -s tests -v
```

Validate the plugin and both skills:

```text
python <plugin-creator>/scripts/validate_plugin.py .
python <skill-creator>/scripts/quick_validate.py skills/lifecycle
python <skill-creator>/scripts/quick_validate.py skills/project-init
```

Check the release contract and build the public package:

```text
python scripts/validate_release.py
python scripts/package_plugin.py
```

The ZIP deliberately leaves out marketplace metadata, tests, eval definitions and fixtures,
screenshots, and repository-only docs. A skills-only submission must not declare
`interface.screenshots`; the review images in `docs/images/` are separate submission assets.

## Publishing

The publisher checklist, five positive and three negative review cases, the listing copy, and the
steps only the account owner can perform are in
[`docs/public-submission.md`](docs/public-submission.md). The benchmark and a standalone evidence
viewer are in [`evals/results/benchmark.md`](evals/results/benchmark.md) and
[`evals/results/review.html`](evals/results/review.html) — one run per case, a behavioral comparison
rather than a statistical claim. Support goes through [`SUPPORT.md`](SUPPORT.md) and GitHub Issues.

## License

MIT. The original upstream copyright and license are kept in [`LICENSE`](LICENSE).
