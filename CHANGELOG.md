# Changelog

All notable changes to this plugin are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

## [1.1.15] — 2026-09-02

### Added
- `lifecycle recover --rebuild --task <task> --user-confirmed` recreates a lost or unusable state
  file. A repository can outlive its state — a stray delete, a fresh checkout, a different machine
  — and until now the only route back was to start over and lose the recorded task.
- The bytes it replaces are archived as `before-rebuild` under `.truedev-workflow/history/` before
  anything is written, so an unusable state file is still the only record of what happened.

### Changed
- The rebuild puts every user gate back at pending and restarts at the first step. Commits and
  touched test files show that work happened, never that anyone approved it; an over-generous
  reconstruction would retire the remaining gates in silence, which is worse than repeating them.
- `--rebuild` and `--accept-current-branch` are mutually exclusive, and `--rebuild` stays out of the
  gate allowlist because it writes — unlike the branch rebinding, it cannot run while a gate is open.

## [1.1.14] — 2026-09-02

### Added
- `second_opinion` in `truedev.project.json`: an object with exactly `scope` and `review`, each
  naming one reviewer to consult before that gate opens — another installed skill, or a subagent
  brief. `project-config init` takes `--second-opinion-scope` and `--second-opinion-review`.
- SCOPE and REVIEW consult the named reviewer and present its findings as their own attributed
  block, so the reader can tell an outside view from the author's own.

### Changed
- The reviewer runs **before** `gate`, never after. An open gate blocks subagent launches, so a
  review deferred to that point cannot happen at all — the layer would look optional and be absent.
- `null` is a reported fact, not a silent skip: the step writes `second opinion: not configured` in
  its evidence. An unmentioned reviewer reads as one that was taken and agreed.
- `project-init` asks once at `INPUT_VALIDATION` and keeps the answer in `docs/REQUIREMENTS.md`
  instead of asking again at every phase.

## [1.1.13] — 2026-09-02

### Added
- Adoption asks about each test layer separately and records each answer in its own field:
  `test_setup` for the unit runner, `e2e_setup` for the browser layer, `integration_test` for a
  real-client layer such as a bot driven through an ordinary user account. One offer covering three
  different decisions meant the two a project most needed were never made.
- The offers themselves are written out in `references/project-config.md`, with what each layer
  costs and what it buys. The person who most needs the offer is the one who has not heard of the
  tool, and "set up an integration client?" is not a question they can answer.
- `adopted_from: "empty"` marks a repository adopted before it had any code. The first step that
  finds a manifest runs the dialogue again instead of reporting "not configured" for the rest of
  the project's life; `detect` reports the same condition as `adopted_from_hint`.

### Changed
- Silence is not a decline. An unanswered offer records nothing and stands again at the next slice
  that adds real logic; `declined:once` returns once; `declined:always` never returns.
- Installing an accepted layer belongs to the first slice that needs it, in that branch, through
  the same review as the code. Credentials stay in the environment, and an integration layer that
  needs real ones does not run in CI by default.

## [1.1.12] — 2026-09-02

### Added
- `status` now names the open gate and the single next action, so reading it does not require
  working out which command applies to the step it just printed. That inference is where a run
  talks itself into approving its own gate.
- A deliberate compact bypass stays visible: `status` prints `compact_released: before <STEP> at
  <time>` for the rest of the run. The receipt was already recorded and nothing displayed it.

### Changed
- One vocabulary across the runner, both skills, and the README. `complete` is accepted wherever
  `approve` was, and `skip-compact` wherever `release-compact` was, with one implementation and
  one receipt behind each pair. Both spellings pass the gate allowlist; the documentation and the
  status line use the second of each pair. The words a person reads are now the words the gate
  accepts.
- User gates are marked `[GATE]` in the step table rather than trailing `user-gate`.
- Both skills carry a command table, and the suggested prompts speak the same vocabulary.

## [1.1.11] — 2026-09-02

### Added
- `detect` reads a repository and reports its stack, package manager, build/lint/test/E2E
  commands, existing planning documents, and a suggested entry phase. The skills had been told
  not to assume a stack but were given no way to find out what the stack actually was, so the
  work fell back to whatever the model guessed from a directory listing.
- `truedev.project.json`, written only by `project-config init --user-confirmed`, records the
  project's own commands. A `null` entry states that a layer does not exist, which the skills
  now report as a skipped check instead of substituting a plausible command.
- `project-init start --from <PHASE> --user-confirmed` adopts earlier phases as `pre_existing`
  with one `adopt` receipt each. An existing repository previously had to regenerate
  requirements and a PRD it already had, or skip phases with no record of who decided that.
- `project-init next-slice` answers which slice is ready, with the blocked ones and their
  unmet dependencies. Slice selection was prose in the skill that hardcoded `docs/plan/`, so a
  custom plan directory was invisible and a blocked dependency was one misreading away. Both slice
  commands now take the plan directory from the project file when no flag is given.

### Fixed
- The non-Git fallback for locating a state root now stops at the home directory. A forgotten
  `.truedev-workflow/` high in the tree captured every directory beneath it, so unrelated work
  in a sibling project was gated by a workflow the user had abandoned months earlier.
- `--resume` no longer discards baseline eval runs when skill text changes. The baseline is
  instructed not to read the skill, so its answer cannot depend on it.
- Adopting the project description is ordered after the clean-tree preflight in both the skill and
  the step playbook. The two documents disagreed, and the earlier order wrote a task-owned file and
  then failed the preflight on that same file.

## [1.1.10] — 2026-09-02

### Fixed
- Benchmark provenance records a modified working tree, and the release gate refuses evidence
  produced from one. A commit id alone was not provenance: a run made with uncommitted edits
  claimed the commit it started from and so described neither that tree nor any released artifact.
- `lifecycle` resume now says where the task itself comes from. The restored summary carries enum
  values only, so narrowing attention to `references/steps.md` left the agent without the slice, its
  acceptance criteria, or the documents they reference.

### Changed
- The `positive-lifecycle-compact-resume` assertion listing the injected-context allowlist named four
  fields; the shipped contract has carried five since the validated slice reference was added, so the
  assertion matched no released version.

## [1.1.9] — 2026-09-01

### Security
- A single `&` no longer passes the gate allowlist. Command Prompt chains on it, so
  `git-preflight --expected-branch main&whoami` was accepted as a read-only command and ran the
  second half. Argument values are also confined to characters that carry no shell meaning.
- A state file replaced by a broken link is treated as tampering rather than absence. Existence was
  tested before link-ness in three places, so following the dangling link reported no active
  workflow and mutations were allowed.
- A branch mismatch in a related checkout now denies instead of being skipped. Opening a gate, then
  moving the gated checkout to another branch, let a sibling worktree mutate freely.
- Starting a workflow requires an ignore rule covering the whole state directory. A rule naming only
  the active file left archived receipts, which carry task and approval metadata, committable.

### Fixed
- Archive receipts include microseconds, so two archives in the same second no longer collide.
- `--resume` and grading reject an eval run whose prompt, assertions, skill text, or runner changed
  since it was produced; runs now record a fingerprint of everything they depend on.

### Documentation
- The CLOSE step described an impossible order: it asked for the close actions before recording the
  approval, while the open gate blocks exactly those actions. Approval is recorded first, which is
  what unblocks the tools, and the authorized actions follow.
- `project-init` states that Git is required. `start` resolves the repository root through Git and
  refuses unless the state directory is ignored, so it was never optional.
- The published benchmark records the version and commit that produced it, and is marked as
  describing 1.0.0. `validate_release.py --require-current-evidence` fails until the suite is rerun
  from the release SHA; the submission checklist now uses that flag.

## [1.1.8] — 2026-09-01

### Fixed
- An open gate inside a submodule now also stops work done from the parent checkout. Enclosing
  checkouts were already covered; the reverse direction was not, so the guard was asymmetric.
  Declared submodule paths are read from `.gitmodules` without spawning Git, and paths that are
  absolute or escape the repository are ignored.
- `inspect git-diff` refuses with an explanation when excluding the sensitive paths would exceed the
  command-line limit, instead of failing with an opaque operating-system error.
- Gate denials for the compact gate now name `lifecycle release-compact --user-confirmed`, so a host
  that never emits a compact event does not look like a dead end.
- Archiving and abandoning tolerate a state file removed underneath them.

### Documentation
- `SECURITY.md` states which tool names the `PreToolUse` matcher enumerates, that a tool introduced
  later would not be gated, and what widening the matcher to `.*` costs — roughly half a second per
  tool call on Windows.

## [1.1.7] — 2026-09-01

### Fixed
- Accepted the bare `py` launcher and `py -3.11` in gate-exempt commands. Only `py -3` was allowed,
  so the standard Windows launcher spelling was refused as if it were an unsafe command.
- Streamed `git ls-files` in `git-preflight` instead of buffering the whole index listing, so peak
  memory no longer grows with repository size, and decoded paths with `surrogateescape` so a name
  that is not valid UTF-8 stays testable rather than losing the bytes that identify it.

### Documentation
- `steps.md` now tells the REVIEW step to name the paths `inspect git-diff` withheld and treat each
  one as an unreviewed change rather than an absent one.

## [1.1.6] — 2026-09-01

### Security
- Refused a `.truedev-workflow` directory that a symlink or Windows junction redirects, which
  previously moved every state read and write outside the repository.
- Detected Windows junctions wherever symlinks were already rejected, so a junction can no longer
  present an arbitrary directory as a repository root.
- Extended an open gate to linked worktrees and enclosing checkouts such as submodules; work done
  from those directories used to bypass the gate entirely.
- Rejected line breaks in stored workflow text, and rendered every status field on a single line, so
  task or specification text can no longer forge status lines the model is told to trust.

### Fixed
- Emitted UTF-8 regardless of the console code page. Any character outside a Windows ANSI code page
  previously turned `status`, `git-preflight`, `validate-slices`, and hook output into an unhandled
  `UnicodeEncodeError`, losing the hook's denial reason.
- Recorded the starting commit and reported it in `status`, so a history rewrite under an unchanged
  branch name is visible instead of silent.
- Stopped the Stop hook from blocking a turn forever when the host repeats a payload it cannot
  validate.
- Treated `*.env` names and trailing-dot or trailing-space variants as credential paths, and returned
  a clean refusal instead of a `ValueError` for a NUL byte in a runner path.

## [1.1.5] — 2026-09-01

### Security
- Hook launchers now require an absolute installed `PLUGIN_ROOT`, so an unset or relative value can
  no longer resolve to a `scripts/truedev_workflow.py` inside the repository under review.
- Both platforms use the same shell-neutral launcher, so a missing installation path is inert
  everywhere instead of denying every tool call on POSIX and running nothing on Windows.
- A relative runner in a gate-exempt command is resolved against the tool call's own working
  directory again; resolving it against the repository root approved one file while a different one
  would execute.
- A workflow bound to the `(detached)` or `(git-unavailable)` placeholder never satisfies the branch
  guard, and recovery refuses to record either placeholder as the active branch.

### Fixed
- Restored detection of conventional secret stores (`secrets/` directories, `secret(s).yaml|json|toml`
  and similar data files) while keeping ordinary source names such as `secrets.ts` unflagged.
- The diff inspector now names the paths it withholds instead of returning a silently shortened diff,
  and excludes them by pathspec so the command line no longer grows with the change set.
- `inspect git-diff --check` reports whitespace findings through its exit status instead of failing
  as if the inspection itself broke.

## [1.1.4] — 2026-09-01

### Fixed
- Made Windows hook launch commands independent of Command Prompt or PowerShell variable syntax and
  fail-open when the installed plugin root is unavailable.
- Preserved status, explicit recovery, and abandonment when Git metadata disappears; detached HEAD
  remains readable but can no longer be recorded as a recovered branch.
- Restored no-state hook inertness before tool-specific payload validation.
- Narrowed credential-path blocking to high-confidence files and excluded those files from the
  bundled Git diff inspector without blocking ordinary source names such as `secrets.ts`.
- Accepted repository-relative slice files from a custom plan directory and avoided a Git subprocess
  during normal repository-root discovery.
- Rejected incomplete nested Git markers and free-form slice-directory components before using them
  for hook root selection or compact-session context.
- Passed filtered Git diff filenames back as literal pathspecs so pathspec magic cannot reselect a
  sensitive file.

## [1.1.3] — 2026-09-01

### Security
- Replaced raw shell and Git gate exemptions with bounded, repository-confined runner inspection.
- Resolve the authoritative Git root before considering standalone workflow state, preventing nested
  state directories from shadowing an active repository.
- Serialize workflow mutations with cross-platform advisory locks and fail malformed hook payloads
  closed without tracebacks.
- Expanded sensitive-path detection for SSH keys, Terraform state, Docker credentials, kubeconfig,
  Composer auth, and common cloud credential files.
- Pinned CI actions and the Ruff dependency by immutable hashes.
- Added skill-local icon assets so Codex can load interface metadata without path warnings.
- Keep advisory lock files inside Git metadata so a rejected start cannot dirty the working tree.

## [1.1.2] — 2026-09-01

### Changed
- Reserved during local release preparation; its candidate changes were superseded by `1.1.3`
  before publication.

## [1.1.1] — 2026-09-01

### Fixed
- Kept lifecycle status and recovery usable on detached HEAD, with branch mismatch reported separately
  from malformed state.
- Added explicit compact-gate release when Codex does not emit a compact `SessionStart` event.
- Allowed narrow read-only evidence inspection while user gates are open without allowing shell chaining,
  redirection, sensitive-file reads, or a substitute runner.
- Validated and restored the active slice reference; handled non-UTF-8 slice files as controlled errors.
- Expanded sensitive-path detection for common credential, private-key store, and package-registry files.
- Made package filenames follow the manifest version and removed internal eval fixtures from public ZIPs.
- Hardened eval selection, empty aggregation, and the Go fixture used by release evals.
- Synced state directories after atomic replacement on platforms that support directory fsync.
- Fixed Windows hook commands to expand `PLUGIN_ROOT` in PowerShell.

## [1.1.0] — 2026-09-01

### Added
- Explicit, receipt-preserving lifecycle branch recovery and fail-closed workflow abandonment.
- Deterministic slice dependency validation for malformed IDs, missing nodes, self-dependencies, and cycles.
- File-backed internal eval fixtures, recovery cases, and near-miss trigger checks for both skills.

### Changed
- Automated TEST now precedes the manual VERIFY gate.
- Backend and other non-UI slices record COMPONENTS as not applicable without an empty approval gate.
- Architecture robustness uses evidence-backed `covered`, `deferred`, or `N/A` classifications.
- Skill metadata and default prompts now follow the current Codex skill schema.

### Security
- State reads reject symlinks and files larger than 1 MiB.
- Recovery never fabricates approval receipts; abandonment archives the exact original state bytes.

## [1.0.0] — 2026-08-31

### Changed
- Ported the package from its legacy agent-host format to a native Codex plugin and repo marketplace.
- Replaced vendor-specific frontmatter, slash commands, task-list calls, and legacy instruction output with
  portable Agent Skills instructions, `$` invocation, Codex plans, and `AGENTS.md` integration.
- Replaced Bash/jq hooks with a cross-platform Python runner and native Codex hook schema.
- Made project-init and lifecycle stack-neutral; repository commands and architecture choices are
  discovered from the actual project rather than hardcoded to React/Node tooling.
- Replaced automatic pull/stage-all/commit/push/merge/delete behavior with explicit authorization and
  Git preflight requirements.

### Security
- State parsing and transition validation now fail closed for matched mutation tools.
- State is resolved from the Git root, written atomically, and protected by a versioned schema.
- Compact restoration injects only allowlisted enum/status context rather than raw state content.
- Compact and approval gates cover Bash, `apply_patch`, subagent, and matched MCP tool calls.
- Shell-control chaining is rejected for the narrow approval-command exemption.

### Added
- Sixteen deterministic tests covering plugin layout, state validation, gates, compaction,
  prompt-injection resistance, nested working directories, Git preflight, project-init transitions,
  and receipt archival.
- Formal P0–P2 upstream audit with fix mapping.
- Cross-platform GitHub Actions validation, deterministic public-package creation, and release checks.
- Public listing assets, privacy, terms, support, security, and submission documentation.
- A reviewer-ready evaluation set with five positive and three negative cases.

### Fixed
- Windows hooks now use the working `python` launcher instead of assuming `py -3` is registered.

## [0.2.0] — 2026-08-27

### Changed
- GitHub operations in `lifecycle` now go through the `gh` CLI first (`gh pr create`,
  `gh pr merge --squash --delete-branch`), with the GitHub MCP server as the fallback.
  Previously the skill mandated the MCP server and explicitly forbade `gh`, which stalled
  `CLOSE` whenever the MCP connection dropped.

### Added
- README — an ASCII diagram of both skills: the `project-init` phases with the artifact
  each one writes, the slice handoff into `lifecycle`, and which steps are user gates
  versus compact gates.
- README — an install path for users with no SSH key on GitHub. The `owner/repo`
  shorthand clones over SSH; the explicit HTTPS url and a local checkout both work as
  marketplace sources instead.

### Note
- Installs made while `0.1.0` was current may hold a stale cache because the legacy host keyed its
  plugin cache by version. This historical refresh command does not apply to the Codex port.

## [0.1.0] — 2026-08-21

First public release.

### Added
- `project-init` skill — turns a spec into structured docs:
  `INPUT_VALIDATION → PRD → ARCHITECTURE → PLANNING → DECOMPOSITION → FINALIZE`.
  DECOMPOSITION writes task slices to `docs/plan/`.
- `lifecycle` skill — drives one feature end-to-end:
  `CONTEXT_CHECK → SCOPE → PLAN → COMPONENTS → IMPLEMENT → VERIFY → TEST → REVIEW → DOCUMENT → CLOSE`.
- Three hooks enforcing the lifecycle contract: `check-compact-gate.sh`
  (`PreToolUse(Agent)`), `inject-lifecycle-state.sh` (`SessionStart(compact)`),
  `check-lifecycle-gate.sh` (`Stop`).
- Marketplace manifest — the repo installs directly as a plugin marketplace.
- MIT license.

### Fixed
- `check-lifecycle-gate.sh` omitted `COMPONENTS` from its ordered step list, so the
  `COMPONENTS` user gate was never enforced by the `Stop` hook.

### Notes
- Optional agents and skills (design agents, second-opinion and design-system skills,
  GitHub and Jira MCP, Storybook) are not bundled. Every step that uses one falls back
  to a documented in-house path instead of blocking.

[0.2.0]: https://github.com/UnBergant/bergant-workflow/releases/tag/v0.2.0
[0.1.0]: https://github.com/UnBergant/bergant-workflow/releases/tag/v0.1.0
