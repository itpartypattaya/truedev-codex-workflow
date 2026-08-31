# Security Policy

## Supported version

Security fixes target the latest released version. During prerelease development, reports should
reference the exact commit SHA.

## Trust model

TrueDev Workflow coordinates a model-driven process. Its hooks are guardrails, not a complete
security boundary. The authoritative controls remain Codex approvals and sandboxing, operating-system and
repository permissions, protected branches, CI, secrets management, and provider-side
authorization.

The plugin's synchronous `PreToolUse` hook can deny matched local shell, patch, agent, and MCP tool
calls while a compact or user-approval gate is active. Codex can have hosted or specialized tool
paths that do not emit the same hook event. Multiple matching hooks may also start concurrently.
Users must therefore treat the hook as a guardrail and review it through `/hooks` after every hash
change.

## Data and command boundaries

- Hook input is accepted as JSON on standard input and schema-checked before use.
- Repository roots are resolved before state access, and state is bound to the recorded root.
- State writes are atomic and use restrictive permissions where supported.
- Invalid active state fails closed for matched mutation tools.
- Compaction injects only allowlisted workflow names, enum values, statuses, and a boolean compact
  flag. Free-form task, state, and transcript text is not elevated to developer context.
- Approval transitions require the explicit `--user-confirmed` flag after a named user decision.
  This is auditable workflow evidence, not cryptographic proof of human identity.
- The runner does not pull, stage all, push, merge, reset, delete branches, or remove worktrees.
- The plugin has no network client, telemetry, credential store, or MCP server.

## Known limitations

- Disabling or declining trust for hooks removes automatic mutation blocking.
- A missing or shadowed Python executable prevents hook execution.
- An agent or external process with direct filesystem access can alter local state outside the
  runner; schema checks detect many but not all malicious environmental changes.
- Stop hooks can keep a workflow turn active but cannot prove that every external side effect was
  observed or reversed.
- User approval is interpreted conversationally by the host model and must be reviewed for the
  named gate and evidence.

## Reporting a vulnerability

Use GitHub's private security-advisory flow for this repository. If that flow is unavailable, open a
minimal public issue requesting a private contact channel without including exploit details,
credentials, personal data, or confidential repository content.

Include the affected version or SHA, operating system, Codex version, Python version, hook event,
minimal reproduction, impact, and whether the behavior requires trusted hooks. Maintainers will
acknowledge actionable reports, reproduce them, and coordinate a versioned fix and disclosure.
