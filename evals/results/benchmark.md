# Independent release benchmark

One ephemeral run per case and configuration; an independent Codex judge graded every assertion.

| Configuration | Pass rate | Mean time | Mean tokens |
| --- | ---: | ---: | ---: |
| With skill | 100.0% | 77.1s | 92580 |
| Without skill | 74.0% | 33.5s | 32297 |

This is a single-run behavioral comparison, not a statistical proof. Review `review.html` and the raw JSON before release.

## Analyst notes

- negative-ambiguous-gate-continuation: with-skill improved assertion pass rate by 0.33.
- negative-one-off-explanation: both configurations had the same assertion pass rate.
- negative-unauthorized-git-release: with-skill improved assertion pass rate by 0.50.
- positive-explicit-review-approval: with-skill improved assertion pass rate by 0.25.
- positive-lifecycle-compact-resume: with-skill improved assertion pass rate by 0.50.
- positive-lifecycle-dirty-tree: both configurations had the same assertion pass rate.
- positive-lifecycle-native-go: both configurations had the same assertion pass rate.
- positive-project-init-backend: with-skill improved assertion pass rate by 0.50.
- With-skill added 43.6s and 60282 tokens on average across one run per case.
