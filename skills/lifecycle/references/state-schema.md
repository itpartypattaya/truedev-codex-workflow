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
  at workflow start. Status remains readable and labels a mismatch for recovery. The placeholders
  `(detached)` and `(git-unavailable)` identify no commit, so they can never be recorded by recovery
  and never satisfy the branch guard; a workflow already bound to one stays blocked until it is
  recovered onto a named branch or abandoned.
- `awaiting_compact` is boolean and is cleared by a validated compact-session hook or an explicit
  `release-compact --user-confirmed` receipt when the host event is unavailable.
- History contains transition metadata, not free-form prompts or repository content.

Hooks first recognize validated `.git` directory/worktree markers, then ask Git only for unusual
layouts before considering a standalone state root. This avoids a Git subprocess on every normal
hook call and prevents a nested `.truedev-workflow/` directory from shadowing the repository. If Git
metadata disappears, status and explicitly confirmed recovery or abandonment remain available with
the `(git-unavailable)` sentinel; the advisory lock becomes unavailable, but writes remain atomic.
If the state file
exists but is malformed or violates an invariant, mutating tool calls are denied until the state is
recovered or explicitly abandoned. `abandon --user-confirmed` archives the original bytes before
removing active state; it never synthesizes approval history. If no state file exists, the plugin is inert.

Session restoration injects only a small allowlisted summary: workflow name, current enum, status,
validated repository-relative `<plan-dir>/slice-*.md` reference, and compact flag. Every plan-directory
component is restricted to ASCII letters, digits, `.`, `_`, and `-`. Task text and arbitrary state
values are never promoted into developer context.

The state and hooks are workflow guardrails. They do not replace repository permissions, sandboxing,
code review, protected branches, CI, or provider-side authorization.
