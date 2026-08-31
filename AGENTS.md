# TrueDev Workflow contributor guidance

## Scope

This repository is a Codex plugin containing two reusable skills and deterministic lifecycle hooks.
Keep it cross-platform and stack-neutral.

## Required verification

Run before committing changes:

```text
python -m unittest discover -s tests -v
python -m py_compile scripts/truedev_workflow.py tests/test_truedev_workflow.py tests/test_plugin_layout.py
python <plugin-creator>/scripts/validate_plugin.py .
python <skill-creator>/scripts/quick_validate.py skills/lifecycle
python <skill-creator>/scripts/quick_validate.py skills/project-init
git diff --check
```

Live Codex hook behavior requires a fresh-session installation smoke test; do not report it as passed
from unit tests alone.

## Invariants

- Do not edit workflow state directly; use `scripts/truedev_workflow.py`.
- If an active state file exists but is invalid, matched mutation tools fail closed.
- Never inject free-form state or task text as developer context.
- Keep approval transitions ordered and recorded; completed user gates require `approved_at`.
- Keep Git actions explicit. Do not add automatic pull, stage-all, push, merge, reset, branch deletion,
  or worktree removal.
- Do not hardcode a language, package manager, frontend framework, test framework, or default branch.
- Hooks are guardrails rather than a security boundary; documentation must preserve that distinction.
- Preserve the original MIT license and upstream attribution in the audit/changelog.
