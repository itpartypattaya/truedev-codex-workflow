# Lifecycle state contract

Active state lives at `<repo>/.truedev-workflow/lifecycle.json`. It is transient and must be ignored
by Git. Completed receipts are archived under `.truedev-workflow/history/`.

The Python runner is the only supported writer. It serializes each read-modify-write transition with
an OS advisory lock and validates these invariants before every atomic replace:

- `schema_version` is currently `4` and `workflow` is `lifecycle`.
- The step set and order are fixed.
- All steps before `current_step` are completed; all later steps are pending.
- A user gate may be `awaiting_approval`; an automatic step may not.
- A completed user gate has an ISO-8601 UTC `approved_at` timestamp and exactly one matching,
  ordered approval receipt after its gate receipt.
- `COMPONENTS` alone may complete with `outcome: not_applicable` and one deterministic skip receipt
  when the work has no UI surface.
- Lifecycle transitions and mutation hooks require the active Git branch to match the branch recorded
  at workflow start. Status remains readable and labels a mismatch for recovery.
- `awaiting_compact` is boolean and is cleared by a validated compact-session hook or an explicit
  `release-compact --user-confirmed` receipt when the host event is unavailable.
- History contains transition metadata, not free-form prompts or repository content.

Hooks ask Git for its authoritative root before considering a standalone state root, even when Codex
starts below a nested `.truedev-workflow/` directory. If the state file
exists but is malformed or violates an invariant, mutating tool calls are denied until the state is
recovered or explicitly abandoned. `abandon --user-confirmed` archives the original bytes before
removing active state; it never synthesizes approval history. If no state file exists, the plugin is inert.

Session restoration injects only a small allowlisted summary: workflow name, current enum, status,
validated `docs/plan/slice-*.md` reference, and compact flag. Task text and arbitrary state values are
never promoted into developer context.

The state and hooks are workflow guardrails. They do not replace repository permissions, sandboxing,
code review, protected branches, CI, or provider-side authorization.
