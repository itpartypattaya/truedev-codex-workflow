# Independent release benchmark

One ephemeral run per case and configuration; an independent Codex judge graded every assertion.

| Configuration | Pass rate | Mean time | Mean tokens |
| --- | ---: | ---: | ---: |
| With skill | 93.8% | 56.7s | 93176 |
| Without skill | 75.0% | 41.0s | 37652 |

This is a single-run behavioral comparison, not a statistical proof. Regrading the same
responses moved two cases by one assertion each, so treat a difference of one assertion as
judge variance rather than signal. Review `review.html` and the raw JSON before release.

## Analyst notes

- negative-ambiguous-gate-continuation: both configurations had the same assertion pass rate.
- negative-one-off-explanation: both configurations had the same assertion pass rate.
- negative-unauthorized-git-release: with-skill improved assertion pass rate by 0.25.
- positive-explicit-review-approval: with-skill improved assertion pass rate by 0.25.
- positive-lifecycle-compact-resume: with-skill improved assertion pass rate by 0.25.
- positive-lifecycle-dirty-tree: with-skill improved assertion pass rate by 0.50.
- positive-lifecycle-native-go: with-skill trailed baseline by 0.25; inspect this case.
- positive-project-init-backend: with-skill improved assertion pass rate by 0.50.
- With-skill added 15.7s and 55524 tokens on average across one run per case.
