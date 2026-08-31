# Project-init phases

Read only the active phase. Each user phase ends by writing its durable artifact, presenting the
decision summary, and opening the runner gate.

## INPUT_VALIDATION

Check the specification for:

- a defined problem, target users, and measurable outcome;
- functional requirements and explicit exclusions;
- non-functional requirements relevant to the domain;
- constraints such as platforms, scale, integrations, deadline, budget, and team;
- contradictions, undefined terms, unverifiable claims, and missing decision owners.

Write `docs/REQUIREMENTS.md` with stable requirement IDs, open questions, and clearly labelled
assumptions. Do not silently fill material gaps. Present the blocking questions and open the gate.

## PRD

Read the approved requirements. Act as a senior product partner:

1. Identify workflow gaps, onboarding and recovery needs, abuse or support burdens, and weak success
   metrics.
2. Propose a narrow MVP plus explicitly deferred items. Recommendations must remain distinguishable
   from approved requirements.
3. Research market or competitors only when requested or decision-relevant. Cite direct sources and
   dates rather than relying on model memory.
4. Assess current legal and compliance concerns from authoritative jurisdiction-specific sources.
   Separate MVP controls, later controls, and owner/legal sign-offs.
5. Write `docs/prd.md` with users, prioritized stories, acceptance criteria, key flows, success
   metrics, risks, compliance obligations, and out-of-scope items.

Present the MVP boundary and unresolved decisions, then open the PRD gate.

## ARCHITECTURE

Read approved requirements and PRD, then inspect the existing repository when one exists.

1. Describe the simplest architecture that meets the approved scale and operational constraints.
2. Present alternatives only where a real decision exists; include cost, complexity, lock-in,
   operability, security, and migration trade-offs.
3. Define component responsibilities, interfaces, data model, API or message contracts, identity and
   authorization, failure handling, observability, deployment, backup/restore, migrations, and
   rollback.
4. Score error handling, concurrency, data integrity, performance, security, observability,
   testability, and scalability from 0–3. Scores 0–1 require mitigation or explicit deferral.
5. For frontend work, extend the project's actual design system. Document tokens, reusable
   components, accessibility target, responsive rules, relevant states, and key-page wireframes.
   Select tooling from repository context; do not mandate a framework or Storybook.
6. Verify only the versions that the plan actually pins, using official sources and a verification
   date.

Write `docs/architecture.md`, link separate design artifacts rather than duplicating them, present
the consequential decisions, and open the ARCHITECTURE gate.

## PLANNING

Build dependency-ordered vertical phases that each deliver a testable user or operational outcome.
Avoid plans split only into frontend/backend/database layers.

For each `docs/plan/phase-N.md`, include:

- goal and user-visible or operational outcome;
- prerequisites and external sign-offs;
- atomic tasks with size and definition of done;
- verification layers and rollback considerations;
- acceptance criteria and explicit exclusions.

Put foundational security, data integrity, migration, CI, and operability work in the earliest phase
that depends on it. Visual refinement can be late; accessibility and safe error states cannot.
Present phase boundaries and open the PLANNING gate.

## DECOMPOSITION

Turn the approved plan into independently deliverable slices. Each slice should be small enough for
one lifecycle but large enough to produce coherent value.

Create `docs/plan/slice-NNN-<title>.md` containing:

- `Status: pending`;
- owning phase and dependency slice IDs;
- scope and out-of-scope;
- owned surfaces or likely files, when known;
- tasks with definitions of done;
- acceptance criteria and required verification layers;
- external approvals or provider dependencies.

Validate the dependency graph for missing nodes and cycles. Present the ordered slice table. Sync to
an external tracker only after the user explicitly requests that external write. Open the
DECOMPOSITION gate.

## FINALIZE

1. Check that requirements, PRD, architecture, phases, and slices agree. Report unresolved
   contradictions instead of papering over them.
2. Merge concise commands, conventions, document pointers, and verification expectations into the
   nearest appropriate `AGENTS.md`. Preserve unrelated instructions.
3. Ensure `.gitignore` covers `.truedev-workflow/`, secrets, and actual build outputs without broad
   patterns that hide source files.
4. Finish FINALIZE, archive the state receipt, and identify the first unblocked slice for lifecycle.
