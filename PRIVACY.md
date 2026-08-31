# Privacy Policy

Effective date: 2026-08-31

TrueDev Workflow is a skills-only Codex plugin maintained by IT Party Pattaya. It does not include
telemetry, analytics, advertising, an MCP server, or a bundled network client. The maintainer does
not receive repository contents, prompts, workflow state, or hook payloads through the plugin.

## Data processed locally

When enabled, the plugin may process information already available to the user's Codex session:

- repository paths, Git status, branch names, and project documentation;
- the specification, task, or slice selected by the user;
- Codex hook event fields needed to identify the working directory, event, tool, and tool input;
- approval and workflow-transition timestamps.

Active state and archive receipts are stored locally inside the selected repository under
`.truedev-workflow/`. State is schema-validated, written atomically, and expected to remain
Git-ignored. Hook payloads are read from standard input and are not separately retained by the
plugin. Free-form prompts and transcripts are not written into workflow state.

## Retention and deletion

The user controls the repository and its local files. Completing a workflow moves a receipt to
`.truedev-workflow/history/`. The user may delete that directory when the receipts are no longer
needed. Uninstalling the plugin does not delete project state automatically because doing so could
destroy user-owned audit records.

## Third-party services

The skills may recommend or use tools already authorized by the user, such as Git hosting, web
research, or repository-specific services. Those services are outside this plugin and are governed
by their own privacy terms. TrueDev does not silently enable, authenticate, or transmit data to
them.

## Security and contact

Hooks are workflow guardrails, not a complete security boundary. See [SECURITY.md](SECURITY.md) for
the threat model and reporting instructions. Privacy questions can be opened through the public
support channel described in [SUPPORT.md](SUPPORT.md).

Material privacy changes will be documented in the repository changelog and released with a new
plugin version.
