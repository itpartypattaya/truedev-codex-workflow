# Project configuration

`truedev.project.json` lives in the repository root and records what this project actually uses. It is
a committed project file, not workflow state, so it survives archiving and is reviewed like any other
change.

```json
{
  "commands": {
    "build": "npm run build",
    "lint": "npm run lint",
    "test": "npm test",
    "e2e": null
  },
  "plan_dir": "docs/plan",
  "test_setup": "accepted:vitest",
  "e2e_setup": "declined:once",
  "integration_test": null,
  "adopted_from": null,
  "second_opinion": {"scope": "toxic-opinion", "review": null},
  "adopted_at": "2026-09-02T05:00:00Z"
}
```

## Fields

- `commands` — exactly the keys `build`, `lint`, `test`, and `e2e`. A string is the command to run.
  `null` means the project has no such layer. No shell chaining, redirection, or command substitution
  is accepted.
- `plan_dir` — where slice files live. Defaults to `docs/plan`. Each path component may contain only
  ASCII letters, digits, `.`, `_`, and `-`.
- `test_setup`, `e2e_setup`, `integration_test` — optional, one grammar each:
  `accepted:<tool>` records that the user agreed to introduce it, `declined:once` means ask again
  at the first slice that adds real logic, `declined:always` means stop offering. Absent means the
  offer has not been made yet — silence never sets a decline.
- `adopted_from` — `"empty"` when the repository had no manifest at adoption. The first step that
  finds one runs the dialogue again instead of reporting "not configured" forever.
- `second_opinion` — optional object with exactly `scope` and `review`. Each names one reviewer to
  consult before that gate opens — another installed skill, or a subagent brief. `null` means the
  layer is not configured, and the step must say so in its evidence rather than omitting it.
- `adopted_at` — ISO-8601 UTC timestamp of when the user confirmed this file.

## Rules

- Never write or change this file without the user's explicit confirmation in the current
  conversation. `project-config init` requires `--user-confirmed` and refuses to overwrite an existing
  file without `--overwrite`.
- Run `detect` to propose values; it only reads the repository and prints JSON. Present what it found
  and let the user correct it before writing.
- This file replaces guessing, not reading. Keep reading the project's own command sources — its
  `Makefile`, package manifest, and CI configuration — and name them as evidence; the confirmed file
  is what you run, not what you looked at.
- A `null` command is an answer, not a gap to fill. Report the layer as absent and never substitute a
  guessed command such as `npm test` for a project that has none.
- `project-config show` exits 2 when the file is absent. That is the signal to run `detect` and ask,
  not to proceed on assumptions.
- Ask the way `The adoption dialogue` below says, in that order. Each layer is its own answer.
- A `null` reviewer is a fact to report, not a step to skip quietly. The gate evidence says
  `second opinion: not configured`, so the reader knows an outside view was never taken rather than
  taken and agreed.
- `detect` and `project-config show` are read-only and stay available while a gate is open;
  `project-config init` writes and is blocked there.
- Write the file after the clean-tree preflight, never before it. It is a task-owned change, and
  creating it first makes `git-preflight --require-clean` fail on the workflow's own edit.

## The adoption dialogue

Detection proposes; the user decides. Ask in this order, once, and only after the clean-tree
preflight. Each answer is independent — a yes to one is not a yes to the next.

**Commands first.** Show what `detect` found for `build`, `lint`, `test`, and `e2e`, and show
which came back empty. Ask the user to correct or fill them. Never invent one: a project with no
lint command has no lint command, and VERIFY reports the skip instead of substituting a guess.

**No test command is the ordinary case, not an edge case.** Most repositories have none, and not
having to work out how to add one is much of the point. So do not record `null` and move on —
make the offer, using `test_setup` from the detection output, which names a runner that suits the
stack. Say what it costs and what it buys, because the person who most needs this offer is the one
who has not heard of the runner:

> This project has no test command, so the TEST step would have nothing to run and every slice
> would ship unverified. `<runner>` is what this stack normally uses. It adds one development
> dependency and a config file, and it goes in on the first slice that needs it — in that branch,
> through the same review as the code. I'd recommend saying yes. You can also give me the command
> you already use, or say not now.

**Name the browser layer too when `test_setup.e2e` is set.** A UI project's logic tests and its
browser tests are two different decisions, and the second is where a front end actually breaks:

> The project has a UI, so there is a second layer worth having: `<e2e>` drives a real browser
> through the flows a unit test cannot see. Same terms — installed on the first slice that needs
> it. This is a separate yes or no.

**When `test_setup.integration` is set, offer it as a third, optional layer, with its price.**
For a chat bot the part that breaks is the conversation, and only a real client exercises it:

> This looks like a bot. Unit tests cover your handlers — the functions — but not the thing that
> actually breaks: the conversation. `<integration>` is a *client* library: it signs in as an
> ordinary user account and messages your bot the way a person would, so a test can send `/start`,
> read what comes back, tap a button and check the next screen. Here is the honest price: it needs
> a second account and API credentials, it talks to real servers rather than a local mock, it is
> slower, and it should not run in CI by default. Worth having, but only if you want it — say no
> and the unit layer still stands on its own.

Explain what the tool *is* in that much detail every time.

Record each answer in its own field:

- accepted → `accepted:<tool>`
- the user gave their own command → put it straight in `commands.test` or `commands.e2e`
- "not now" → `declined:once`
- "never ask again" → `declined:always`
- no answer at all → record nothing. Silence is not a decline, and the offer stands.

**Never install anything during adoption.** Its job is to ask. An install belongs in a branch,
inside the first slice that needs the layer, and credentials belong in the environment, never in
the repository — the REVIEW secret scan treats a leaked session string or API hash like any other
secret.

**Empty repository?** When `detect` reports `adopted_from_hint: "empty"` — every command `null`
and no manifest yet, the `project-init` case where the code does not exist — say so, record what
you have, and pass `--adopted-from empty`. The first later step that finds a manifest runs the
dialogue again rather than reporting "not configured" for the rest of the project's life.
