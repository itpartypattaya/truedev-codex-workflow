# Lifecycle step playbook

Read only the active section. The runner owns state transitions; these instructions own the work and
the evidence presented to the user.

## CONTEXT_CHECK

1. Read applicable `AGENTS.md`, the selected slice, repository status, and current branch.
   Read repository command configuration before selecting commands. Name every successfully read
   instruction/config file and summarize at least one material directive in past tense. If a required
   read fails, stop instead of inferring commands from conventions or the request.
2. Run the bundled `git-preflight --require-clean` before branch or worktree changes.
3. Load the project's commands with `project-config show`, having already read the repository's own
   command sources — `Makefile`, package manifest, CI configuration — and named them as evidence.
   If `show` exits 2, run `detect`, present the detected stack and commands next to what you read,
   and write them with `project-config init ... --user-confirmed` only after the user confirms. Do
   this after the preflight, never before: the file is a task-owned change, and writing it first
   makes the clean-tree check fail on the workflow's own edit. A `null` command marks an absent
   layer, not a command to invent.
4. Confirm the slice dependencies are completed and the task does not overlap unrelated work.
5. Record any unavailable validation layers. Do not treat them as passed.
6. Finish `CONTEXT_CHECK` through the runner.

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
   runner sets `awaiting_compact`; the SessionStart hook clears it after a real compact event. If the
   host never emits that event, present the limitation and require explicit user confirmation before
   `lifecycle skip-compact --user-confirmed`.

## COMPONENTS — user gate

For UI work, implement or update shared components and their repository-native visual examples or
tests before page integration. Cover relevant loading, empty, populated, error, disabled, and
read-only states plus keyboard and screen-reader behavior. Present render or test evidence.

For non-UI work, document the evidence that no component surface exists, then run
`lifecycle skip --step COMPONENTS --reason non-ui`. This records an explicit not-applicable receipt;
do not open an empty user gate.

Open the COMPONENTS gate and stop.

## IMPLEMENT

1. Work through the approved plan in small, reviewable changes.
2. For a defect, reproduce it and identify the root cause before editing; make the regression test fail
   first, then apply the smallest fix. Avoid unrelated refactoring.
3. Preserve user-owned changes and agreed file ownership.
4. Run focused checks after each meaningful unit rather than waiting for the end.
5. If scope must change, stop and return to a user decision; do not silently expand it.
6. Finish IMPLEMENT only after the implementation checks available in the repository pass.

## TEST

1. Add or update tests in the project's existing frameworks.
2. Cover the business logic and regressions introduced by the slice. Add integration or E2E coverage
   only where that layer exists and materially protects the behavior.
3. Run the narrow tests first, then the repository's broader relevant suite, using `commands.test`
   and `commands.e2e` from `truedev.project.json`. A `null` command means that layer was skipped;
   say so rather than substituting another command. When `test_setup` records an accepted runner
   and no test command exists yet, setting that runner up is part of this slice.
4. Record commands, outcomes, and unavailable layers. Finish TEST when evidence is reproducible.

## VERIFY — user gate

1. Run the `commands.build` and `commands.lint` entries from `truedev.project.json`, plus any
   formatting, type, migration, or packaging checks relevant to the task. A `null` entry means that
   check does not exist here; report it as not run instead of guessing a command.
2. Summarize automated TEST evidence and provide a short user-facing manual verification checklist.
3. State exactly what was not executed and why.
4. Open the VERIFY gate and wait for the user's manual-test result or explicit acceptance of the
   documented limitation.

## REVIEW — user gate

1. Inspect the complete task diff before staging anything. When `inspect git-diff` prints
   `# TrueDev omitted N sensitive path(s)`, the diff you just read is short by exactly those files.
   Name them in the review, state that their contents were not shown, and treat each one as an
   unreviewed change rather than an absent one.
2. Scan for secrets, transient state, generated noise, and unrelated files.
3. Review correctness, authorization, data integrity, concurrency, error handling, observability,
   performance, compatibility, and test gaps.
4. Report findings as P0/P1/P2 with exact files and evidence. Do not hide findings because tests pass.
5. Map every approved acceptance criterion before opening the gate:

   | Criterion | Evidence | Gap |
   | --- | --- | --- |
   | `<criterion>` | `<command/result, test, diff, or artifact>` | `none` or `<unresolved work>` |

   Use `none` only when current evidence directly proves the criterion. Turn unresolved gaps into
   findings or explicit limitations; do not treat the matrix itself as evidence.
6. Open the REVIEW gate. Apply fixes only after the user selects or approves them; then rerun relevant
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
4. Open CLOSE and wait for explicit approval. While the gate is open every repository change is
   blocked, including `git add`, `git commit`, and `git push`, so no close action can run yet.
5. Once the user approves, record it first with `approve --step CLOSE --user-confirmed`. That
   transition completes the lifecycle and unblocks the tools, and it is the only order in which the
   authorized close actions can actually run.
6. Then perform exactly the actions the user authorized, change only this slice's header from
   `Status: pending` to `Status: completed`, and run `lifecycle archive`. Individual task checkboxes
   may be updated earlier, but the slice header changes only after CLOSE.
7. Approval covers the actions named at the gate and nothing else. If something new comes up after
   the transition, stop and ask again rather than treating the completed lifecycle as open
   authority.
