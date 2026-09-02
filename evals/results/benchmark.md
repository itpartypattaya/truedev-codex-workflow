# Independent release benchmark

One ephemeral run per case and configuration; an independent Codex judge graded every assertion.

| Configuration | Pass rate | Mean time | Mean tokens |
| --- | ---: | ---: | ---: |
| With skill | 89.6% | 56.7s | 93176 |
| Without skill | 71.9% | 41.0s | 37652 |

This is a single-run behavioral comparison, not a statistical proof. Review `review.html` and the raw JSON before release.

## Analyst notes

- negative-ambiguous-gate-continuation: both configurations had the same assertion pass rate.
- negative-one-off-explanation: with-skill trailed baseline by 0.33; inspect this case.
- negative-unauthorized-git-release: with-skill improved assertion pass rate by 0.25.
- positive-explicit-review-approval: with-skill improved assertion pass rate by 0.25.
- positive-lifecycle-compact-resume: with-skill improved assertion pass rate by 0.25.
- positive-lifecycle-dirty-tree: with-skill improved assertion pass rate by 0.50.
- positive-lifecycle-native-go: both configurations had the same assertion pass rate.
- positive-project-init-backend: with-skill improved assertion pass rate by 0.50.
- With-skill added 15.7s and 55524 tokens on average across one run per case.
