# slice-004: Billing retry

Status: pending
Phase: phase-2
Depends on: slice-003

## Acceptance criteria

- A failed charge is retried once with the same idempotency key.
- Duplicate successful charges are rejected.
- The operator can verify the retry result manually.
