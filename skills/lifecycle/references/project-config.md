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
  "test_setup": "declined:once",
  "adopted_at": "2026-09-02T05:00:00Z"
}
```

## Fields

- `commands` — exactly the keys `build`, `lint`, `test`, and `e2e`. A string is the command to run.
  `null` means the project has no such layer. No shell chaining, redirection, or command substitution
  is accepted.
- `plan_dir` — where slice files live. Defaults to `docs/plan`. Each path component may contain only
  ASCII letters, digits, `.`, `_`, and `-`.
- `test_setup` — optional. `accepted:<runner>` records that the user agreed to introduce that test
  runner; `declined:once` means ask again next time; `declined:always` means stop offering.
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
- `detect` and `project-config show` are read-only and stay available while a gate is open;
  `project-config init` writes and is blocked there.
- Write the file after the clean-tree preflight, never before it. It is a task-owned change, and
  creating it first makes `git-preflight --require-clean` fail on the workflow's own edit.
