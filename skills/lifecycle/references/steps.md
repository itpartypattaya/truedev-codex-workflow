# Lifecycle step playbook

Read only the active section. The runner owns state transitions; these instructions own the work and
the evidence presented to the user.

## CONTEXT_CHECK

1. Read applicable `AGENTS.md`, the selected slice, repository status, and current branch.
2. Run the bundled `git-preflight --require-clean` before branch or worktree changes.
3. Confirm the slice dependencies are completed and the task does not overlap unrelated work.
4. Record any unavailable validation layers. Do not treat them as passed.
5. Finish `CONTEXT_CHECK` through the runner.

## SCOPE — user gate

1. Read the slice and relevant contracts or specifications.
2. Present the intended outcome, acceptance criteria, out-of-scope items, risks, and unresolved choices.
3. Separate confirmed requirements from assumptions and recommendations.
4. If current or niche facts matter, verify them from primary sources and preserve citations in the
   durable artifact.
5. Open the SCOPE gate and stop. Approval must name or clearly refer to SCOPE.

## PLAN

1. Inspect the implementation surface without editing it first.
2. Produce an ordered plan with owned files, verification for each step, rollback concerns, and
   external actions that require separate authority.
3. For UI work, inventory new and existing components, tokens, states, accessibility, responsive
   behavior, and visual verification. Reuse the project's established design system.
4. For data or schema work, document migration, compatibility, rollback, and immutable-data rules.
5. Synchronize the Codex plan, finish PLAN, and ask the user to compact before implementation. The
   runner sets `awaiting_compact`; the SessionStart hook clears it after a real compact event.

## COMPONENTS — user gate

For UI work, implement or update shared components and their repository-native visual examples or
tests before page integration. Cover relevant loading, empty, populated, error, disabled, and
read-only states plus keyboard and screen-reader behavior. Present render or test evidence.

For non-UI work, document that there is no component surface and ask the user to approve skipping
this gate. Do not pretend the gate does not exist.

Open the COMPONENTS gate and stop.

## IMPLEMENT

1. Work through the approved plan in small, reviewable changes.
2. For a defect, reproduce it and identify the root cause before editing; make the regression test fail
   first, then apply the smallest fix. Avoid unrelated refactoring.
3. Preserve user-owned changes and agreed file ownership.
4. Run focused checks after each meaningful unit rather than waiting for the end.
5. If scope must change, stop and return to a user decision; do not silently expand it.
6. Finish IMPLEMENT only after the implementation checks available in the repository pass.

## VERIFY — user gate

1. Run discovered build, lint, formatting, type, migration, or package checks relevant to the task.
2. Provide a short user-facing manual verification checklist.
3. State exactly what was not executed and why.
4. Open the VERIFY gate and wait for the user's manual-test result or explicit acceptance of the
   documented limitation.

## TEST

1. Add or update tests in the project's existing frameworks.
2. Cover the business logic and regressions introduced by the slice. Add integration or E2E coverage
   only where that layer exists and materially protects the behavior.
3. Run the narrow tests first, then the repository's broader relevant suite.
4. Record commands, outcomes, and unavailable layers. Finish TEST when evidence is reproducible.

## REVIEW — user gate

1. Inspect the complete task diff before staging anything.
2. Scan for secrets, transient state, generated noise, and unrelated files.
3. Review correctness, authorization, data integrity, concurrency, error handling, observability,
   performance, compatibility, and test gaps.
4. Report findings as P0/P1/P2 with exact files and evidence. Do not hide findings because tests pass.
5. Open the REVIEW gate. Apply fixes only after the user selects or approves them; then rerun relevant
   verification before approval transition.

## DOCUMENT

Update durable repository documentation only when behavior, commands, architecture, or operational
contracts changed. Prefer `AGENTS.md` for Codex repository instructions. Do not write personal/global
memory unless the user explicitly asks. Finish DOCUMENT after docs and implementation agree.

## CLOSE — user gate

1. Run the final relevant checks and `git-preflight`.
2. Show the exact intended commit paths and any proposed push/PR/merge action.
3. Do not stage all files. Do not push, create or merge a PR, delete a branch, or clean a worktree
   without authority for that action.
4. Open CLOSE and wait for explicit approval.
5. After the approved close actions, approve CLOSE, change only this slice's header from
   `Status: pending` to `Status: completed`, and archive the lifecycle receipt. Individual task
   checkboxes may be updated earlier, but the slice header changes only after CLOSE.
