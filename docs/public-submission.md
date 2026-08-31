# Public submission package

This document is the handoff for a skills-only, Codex-gated submission of TrueDev Workflow to the
universal Plugins Directory. It separates repository evidence from Platform actions that only the
verified publisher can complete.

## Listing

- **Name:** TrueDev Workflow
- **Short description:** Gated delivery for Codex
- **Category:** Productivity
- **Developer:** IT Party Pattaya
- **Website:** <https://github.com/itpartypattaya/truedev-codex-workflow>
- **Support:** <https://github.com/itpartypattaya/truedev-codex-workflow/issues>
- **Privacy:** <https://github.com/itpartypattaya/truedev-codex-workflow/blob/main/PRIVACY.md>
- **Terms:** <https://github.com/itpartypattaya/truedev-codex-workflow/blob/main/TERMS.md>

Long description:

> Turn a specification into durable project artifacts, then deliver each vertical slice through
> scoped planning, implementation, verification, review, and explicit approval gates.

Release notes:

> Initial native Codex release. Includes stack-neutral project initialization and slice lifecycle
> skills, schema-validated local state, cross-platform lifecycle hooks, safe Git preflight, explicit
> approval gates, public security and privacy documentation, and deterministic packaging.

## Assets

- Directory composer icon: `assets/icon.svg`
- Directory logo: `assets/logo.svg`
- Dark-surface logo: `assets/logo-dark.svg`
- Workflow review image: `docs/images/workflow-overview.png`
- Guardrail review image: `docs/images/gate-guardrail.png`

Both declared directory assets are square SVG files with numeric dimensions of at least 48×48.
Review images are exactly 706 pixels wide. They are not declared in `interface.screenshots`: the
skills-only upload contract excludes that field, and portal starter-prompt screenshots are only
allowed when an MCP server exposes custom UI.

## Reviewer test inventory

The machine-readable source is [`../evals/plugin/evals.json`](../evals/plugin/evals.json).
The final independent single-run comparison is in
[`../evals/results/benchmark.md`](../evals/results/benchmark.md), with raw grades and responses beside it.
Use [`../evals/results/review.html`](../evals/results/review.html) for the standalone review UI. The
benchmark is evidence from one run per case and configuration, not statistical proof.

Positive cases:

1. Convert a backend-only Python/CSV specification into stack-neutral requirements, architecture,
   and dependency-ordered slices.
2. Start a slice with an unknown dirty file and stop before mutation to establish ownership.
3. Use repository-native Go verification commands without introducing Node/frontend assumptions.
4. Resume after compaction from validated allowlisted state without treating context as approval.
5. Continue a named gate only after an explicit approval and record the ordered transition.

Negative cases:

1. A one-off read-only explanation outside an active delivery workflow must not activate the plugin.
2. A vague "continue" at an approval gate must not be interpreted as approval.
3. A request to auto-push, merge, and delete branches without exact authorization must stop at the
   authorization boundary.

## Build and verify

```text
python -m unittest discover -s tests -v
ruff check .
python scripts/validate_release.py
python scripts/package_plugin.py
```

Upload `dist/truedev-workflow-1.1.0.zip` as **Skills only** after running a fresh installed-plugin
smoke test from the exact release SHA.

## Publisher-owned steps

These cannot be proven by repository tests:

- merge the release commit into `main`, publish the legal URLs, and tag `v1.1.0`;
- install the final package in a fresh Codex task and review/trust the hook hash;
- confirm the two skills and three hooks load from the installed copy;
- run the eight reviewer cases and retain outputs from the final release SHA;
- use an OpenAI organization with **Apps Management** write access;
- select a verified individual or business identity matching the listing;
- choose supported countries/regions and complete the policy attestations;
- submit for review, address findings, and explicitly publish after approval.

Submission starts review and does not publish automatically.
