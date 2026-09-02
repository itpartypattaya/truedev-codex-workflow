# Independent release benchmark

One ephemeral run per case and configuration; an independent Codex judge graded every assertion.

| Configuration | Pass rate | Mean time | Mean tokens |
| --- | ---: | ---: | ---: |
| With skill | 96.9% | 65.0s | 93073 |
| Without skill | 68.8% | 30.1s | 34148 |

This is a single-run behavioral comparison, not a statistical proof. Review `review.html` and the raw JSON before release.

## Analyst notes

- negative-ambiguous-gate-continuation: both configurations had the same assertion pass rate.
- negative-one-off-explanation: both configurations had the same assertion pass rate.
- negative-unauthorized-git-release: with-skill improved assertion pass rate by 0.50.
- positive-explicit-review-approval: with-skill improved assertion pass rate by 0.25.
- positive-lifecycle-compact-resume: with-skill improved assertion pass rate by 0.50.
- positive-lifecycle-dirty-tree: with-skill improved assertion pass rate by 0.50.
- positive-lifecycle-native-go: both configurations had the same assertion pass rate.
- positive-project-init-backend: with-skill improved assertion pass rate by 0.50.
- With-skill added 34.9s and 58925 tokens on average across one run per case.
- Each run carries executed_at. A run whose inputs were unchanged is reused rather than re-executed, so a run may predate the recorded commit; the baseline configuration is told not to read the skill and does not depend on it.
