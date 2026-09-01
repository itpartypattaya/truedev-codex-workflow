# Changelog

All notable changes to this plugin are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/);
versioning follows [Semantic Versioning](https://semver.org/).

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
