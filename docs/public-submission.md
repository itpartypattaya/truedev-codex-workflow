# Public submission package

This document is the handoff for submitting the **directory edition** of TrueDev Workflow to the
universal Plugins Directory through the **Skills only** path. It separates repository evidence from
Platform actions that only the verified publisher can complete.

Requirements were checked against the OpenAI developer documentation on 2026-10-06:
[Submit plugins](https://developers.openai.com/plugins/deploy/submission),
[Plugin guidelines](https://developers.openai.com/plugins/plugin-guidelines), and
[Submission errors](https://developers.openai.com/plugins/deploy/submission-errors).

## Why a separate edition

The directory does not currently accept plugin ZIPs that contain lifecycle hooks. The directory
edition is built from the same sources with `python scripts/package_plugin.py --edition directory`
and differs from the GitHub edition in exactly three ways:

- `hooks/` is left out; gates are held by the runner's integrity check, which refuses to approve a
  gate whose evidence changed after it opened, and by the compact checkpoint, which the runner now
  enforces on every transition;
- the runner is copied into `skills/<skill>/scripts/`, so each skill bundle is self-contained, and
  the root `scripts/` directory is not shipped;
- each `skills/<skill>/agents/openai.yaml` gains `policy.products: ["CODEX"]`, because the skills
  need a local repository, Git, and Python that a ChatGPT conversation does not have.

`scripts/validate_release.py` checks the archive with `validate_directory_entries`, and
`tests/test_release.py` proves the build is deterministic and that the bundled runner reports the
correct edition.

## Listing

- **Name:** TrueDev Workflow (16/30)
- **Short description:** Gated delivery for Codex (24/30)
- **Category:** Developer Tools — the directory could not confirm Productivity for a coding workflow
- **Developer:** Anton Vaskov — must match the verified individual identity; the portal overrides
  `developerName` with that identity
- **Website:** <https://github.com/itpartypattaya/truedev-codex-workflow>
- **Support:** <https://github.com/itpartypattaya/truedev-codex-workflow/issues>
- **Privacy:** <https://github.com/itpartypattaya/truedev-codex-workflow/blob/main/PRIVACY.md>
- **Terms:** <https://github.com/itpartypattaya/truedev-codex-workflow/blob/main/TERMS.md>

The long description and release notes live in `.codex-plugin/plugin.json`
(`interface.longDescription`, `extensions.com.openai.publication.release_notes`) and are imported
with the ZIP. The public URLs must resolve on `main` and name the same publisher, so merge before
uploading.

## Assets

- Directory composer icon: `assets/icon.svg` (128×128)
- Directory logo: `assets/logo.svg`, dark variant `assets/logo-dark.svg` (512×512)

Screenshots are not declared: the Skills only upload rejects `interface.screenshots`, and
starter-prompt screenshots are allowed only when an MCP server exposes custom UI.

## Reviewer test inventory

Skills-only plugins do not need MCP review cases or a demo recording. The cases below remain the
behavioral evidence for this release; the machine-readable source is
[`../evals/plugin/evals.json`](../evals/plugin/evals.json) and the single-run comparison is in
[`../evals/results/benchmark.md`](../evals/results/benchmark.md).

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
python scripts/validate_release.py --require-current-evidence
python scripts/package_plugin.py --edition directory
```

`--require-current-evidence` fails unless `evals/results/benchmark.json` records the version being
released and a clean checkout that produced it. Rerun the suite whenever the skills or the runner
change; `--resume` reuses only the runs whose inputs still match.

Upload `dist/truedev-workflow-<version>-directory.zip` as **Skills only** after a fresh install of
that exact ZIP in Codex has shown both skills loading and `lifecycle status` reporting
`enforcement: integrity check (this edition bundles no hooks)`.

## Publisher-owned steps

These cannot be proven by repository tests:

- verify the individual identity **Anton Vaskov** in the OpenAI Platform organization settings;
- use an organization where you are owner or hold **Apps Management Write**;
- merge the release into `main` so the legal URLs show the current publisher, and tag the version;
- install the directory ZIP in a fresh Codex task and run the eight cases from the release SHA;
- upload the ZIP, resolve **Metadata & Skills** findings (skill scans can take up to two hours);
- choose country availability, complete the policy attestations, and submit for review;
- publish explicitly after approval — approval does not publish automatically.
