# Final Review

Self-review against the assignment's own rubric and acceptance criteria, written as an
EVE Healthcare interviewer would evaluate this submission. No score is assigned to
myself — just an honest PASS/FAIL/RISK breakdown.

## A. Requirement checklist

| Requirement | Status |
|---|---|
| Signup / login / JWT auth | PASS |
| Basic request validation | PASS (Pydantic v2 everywhere; explicit password/appointment/price rules) |
| Centres & tests CRUD + N:M with price | PASS |
| Booking (user, test, centre, time, amount, status) | PASS |
| Booking states PENDING/CONFIRMED/FAILED/CANCELLED | PASS |
| Simulated payment (`POST /payments/`) | PASS — no real gateway anywhere |
| Payment result SUCCESS or FAILED, booking updated | PASS |
| Webhook (`POST /payments/webhook/`) | PASS |
| Webhook idempotent under repeats/restarts/multi-worker | PASS — DB-level UNIQUE constraint, proven under real concurrency (8 threads) |
| PostgreSQL as source of truth for idempotency | PASS |
| Edge cases (see §B) | PASS, see below |
| Docker & docker-compose | WRITTEN, NOT EXECUTED — see §I |
| Swagger/OpenAPI | PASS — polished tags/summaries/response models |
| Tests | PASS — 113 tests, 95% coverage |
| Structured logging | PASS |
| Pagination | PASS — centres, tests, offerings, bookings |
| Rate limiting | NOT IMPLEMENTED (explicitly optional in the brief) |
| Retry handling for webhooks | N/A by design — provider retries are handled by idempotency, not a client-side retry loop (this endpoint doesn't call out to anything that needs retrying) |
| Redis | NOT IMPLEMENTED — deliberate, see README §23 |
| Celery | NOT IMPLEMENTED — deliberate, see README §23 |

## B. Edge-case checklist (from the assignment's own list)

| Edge case | Handled | Where tested |
|---|---|---|
| Invalid requests | Yes | Pydantic 422s throughout |
| Repeated webhook events | Yes | `test_duplicate_webhook_delivery_has_no_extra_side_effects`, concurrency test |
| Invalid booking IDs | Yes (404) | `test_cancel_nonexistent_booking_is_404` |
| Failed payments | Yes | `test_failed_payment_fails_booking` |
| Unauthorized resource modification | Yes (403 for admin-only; 404 for cross-user resource access) | `test_non_admin_cannot_create_centre`, `test_user_cannot_see_or_cancel_another_users_booking` |
| Invalid authentication | Yes | `test_protected_endpoint_without_token_rejected` |
| Invalid JWT | Yes | `test_protected_endpoint_with_invalid_jwt_rejected`, `test_tampered_or_foreign_signed_jwt_rejected`, `test_alg_none_token_rejected` |
| Duplicate users | Yes | `test_duplicate_signup_rejected`, `test_signup_case_insensitive_duplicate_rejected` |
| Invalid centre/test relationships | Yes | `test_test_not_offered_by_centre_is_rejected` |
| Invalid appointment data | Yes | `test_appointment_without_timezone_rejected`, past/too-soon/too-far tests |
| Invalid booking state transitions | Yes, exhaustively | `test_every_other_booking_transition_is_rejected` (every non-allowed pair) |
| Duplicate payment attempts | Yes | `test_duplicate_payment_attempt_rejected` |
| Nonexistent resources | Yes | 404 tests across centres/tests/bookings/payments |
| Ownership/authorization problems | Yes | cross-user tests on bookings and payments |
| Database integrity problems | Yes | global `IntegrityError` handler; partial-unique-index backstop tests |
| Concurrent requests | Yes | `test_concurrent_identical_webhooks_apply_exactly_once` (real threads, real Postgres) |

## C. The assignment's 12 "critical tests" — explicit mapping

1. Create booking → PENDING: `test_create_booking_is_pending_with_snapshotted_amount` ✅
2. Successful payment → booking CONFIRMED: `test_successful_payment_confirms_booking` ✅
3. Failed payment → booking FAILED: `test_failed_payment_fails_booking` ✅
4. Duplicate webhook → no duplicate side effects: `test_duplicate_webhook_delivery_has_no_extra_side_effects` + concurrency variant ✅
5. Unauthorized user cannot access another's booking: `test_user_cannot_see_or_cancel_another_users_booking` ✅
6. Invalid booking state transition rejected: `test_cancel_already_cancelled_booking_rejected` + exhaustive unit tests ✅
7. Test not offered by centre rejected: `test_test_not_offered_by_centre_is_rejected` ✅
8. Duplicate user rejected: `test_duplicate_signup_rejected` ✅
9. Invalid JWT rejected: `test_protected_endpoint_with_invalid_jwt_rejected` ✅
10. Payment for non-payable booking rejected: `test_payment_for_non_payable_booking_rejected` ✅
11. Webhook for unknown payment rejected safely: `test_webhook_for_unknown_payment_reference_is_404_and_not_retried_as_duplicate` ✅
12. Database constraints behave correctly: `test_duplicate_active_slot_rejected`, `test_price_update_does_not_retroactively_change_existing_bookings`, offering/centre uniqueness tests ✅

All 12 present and passing.

## D. Security checklist

- [x] Passwords hashed with Argon2 (`pwdlib`), never stored/logged in plaintext
- [x] JWT expiry enforced, algorithm pinned (no `alg: none` acceptance — tested)
- [x] Webhook authenticated by constant-time HMAC comparison, not JWT
- [x] Replay protection via timestamp tolerance window on webhooks
- [x] Secrets only from environment variables; app refuses to start without them
- [x] `.env` git-ignored; only `.env.example` (placeholders) committed
- [x] SQL injection: 100% SQLAlchemy Core/ORM, no raw string interpolation into SQL anywhere
- [x] No stack traces or internal details returned to API clients on 500s
- [x] Login timing equalised between "wrong password" and "unknown email"
- [ ] CORS: disabled by default (empty allow-list) rather than "configured well" — acceptable
      for an assignment API with no browser frontend, but would need real origins in
      production
- [ ] No rate limiting on login/signup — a real weakness for a public deployment, called
      out explicitly rather than silently left out

## E. Database checklist

- [x] Primary keys (UUID) on every table
- [x] Foreign keys with explicit `ondelete` behaviour (`RESTRICT` throughout — no silent
      cascading deletes of financial/booking history)
- [x] Composite FK enforcing centre/test offering validity at the DB level
- [x] Unique constraints: user email, test name, centre (name, location), payment
      provider_reference, webhook_event provider_event_id
- [x] Partial unique indexes: one live booking per (user, centre, test, time); one live
      payment per booking
- [x] NOT NULL on all required columns
- [x] `NUMERIC(10,2)` for all monetary values, never float
- [x] `timestamptz` throughout, UTC-normalised at both the connection level and in
      application validation
- [x] Deterministic constraint naming convention (`ck_`, `fk_`, `uq_`, `ix_`, `pk_`)
      configured on `Base.metadata`, making constraint-violation error handling reliable
- [x] Alembic migration reviewed and confirmed idempotent (`alembic check` → "No new
      upgrade operations detected" after autogenerate against the current models)

## F. API checklist

- [x] RESTful resource structure matching the assignment's suggested shape
- [x] Every endpoint has an explicit `response_model`
- [x] Appropriate status codes: 200/201/401/403/404/409/422 all used correctly and
      intentionally (no endpoint returns a blanket 400 for everything)
- [x] `responses=errors(...)` documents each endpoint's real error surface in OpenAPI
- [x] Pagination validated (`limit` 1-100, `offset` ≥0) and documented
- [x] Response schemas never leak ORM internals (e.g. `hashed_password` never serialized)

## G. Documentation checklist

- [x] README covers all 28 requested sections
- [x] Mermaid architecture + ER diagrams
- [x] Complete curl-based end-to-end example
- [x] Design decisions section answers every "why X" the assignment asked for
- [x] INTERVIEW_NOTES.md with 2-minute pitch, 20 Q&A, and 5 live-coding scenarios
- [x] This file (FINAL_REVIEW.md)

## H. Potential interviewer criticisms

1. **"You didn't actually run Docker."** True and stated plainly in §I below — the
   sandbox this was built in had no Docker installed and no registry access. The
   Dockerfile and compose file follow standard, low-risk patterns (single `pip install`
   layer, non-root user, explicit healthcheck, `service_completed_successfully`
   dependency on the migration step) but I would not claim "verified" for something I
   didn't watch succeed.
2. **"Why no repository/unit-of-work pattern?"** Deliberate — see README §4 and §25.
   Defensible, but an interviewer favoring stricter layering could push back here.
3. **"Rate limiting is genuinely a gap for a public auth endpoint."** Correct, called out
   directly in README §26/§27 rather than glossed over.
4. **"The webhook and payment endpoints trust the client's JWT for `POST /payments/`, but
   what stops a user from spamming `simulate_outcome`?"** `ALLOW_SIMULATION_OVERRIDE`
   exists specifically to be turned off outside a demo; worth surfacing proactively in
   discussion rather than waiting to be asked.
5. **"95% coverage, not 100% — what's missing?"** Mostly generic exception-handler bodies
   and a couple of `IntegrityError` backstops sitting behind row locks that make the
   underlying race essentially unreachable within a single test process (see §J). None of
   the missed lines are on the idempotency or state-machine critical path.

## I. What is genuinely NOT independently verified

Being explicit rather than optimistic:

- **`docker compose up --build`** — Docker was not installed in the build sandbox
  (`docker: not found`), and the network allowlist there did not include Docker Hub, so
  neither the build nor a registry pull could be attempted. The Dockerfile and
  `docker-compose.yml` were written carefully and their YAML syntax was validated, but
  they were not run end-to-end. **Run this yourself before submitting.**
- Everything else — migrations, seed script, every API endpoint, the full test suite,
  linting, formatting, and a manual curl-driven end-to-end smoke test — **was** executed
  in this environment against a real, locally-installed PostgreSQL 16, and the outputs
  shown in this repo's history are real command output, not projected/assumed results.

## J. Weaknesses that remain

- No rate limiting (§D, §H.3).
- No admin-wide booking/payment listing endpoint (only owner-scoped lists exist).
- A handful of `IntegrityError` "backstop" branches in `catalog_service` and
  `payment_service` are defensive code for races that the row locks already prevent in
  practice, so they're hard to hit in a deterministic single-process test — they're
  reviewed by inspection rather than covered by a targeted test.
- Docker unverified (§I).

## K. Exact fixes made during development (chronological, not exhaustive)

- Alembic's `--autogenerate` initially emitted each `Enum`'s CHECK constraint twice
  (once from SQLAlchemy's `Enum(..., create_constraint=True)`, once from the naming
  convention) — deduplicated by hand in the generated migration before applying it.
- First migration attempt failed with `DuplicateObject` on the enum check constraints for
  the same reason above — fixed and re-verified with a clean `upgrade` → `downgrade` →
  `upgrade` cycle plus `alembic check`.
- Ruff initially flagged an unused `noqa` and several long lines in route decorators —
  fixed via `ruff format` plus a `pyproject.toml` line-length allowance specifically for
  `tests/**` (test fixture readability favored over strict wrapping there; application
  code stays under the stricter limit everywhere).
- Confirmed via a manual, un-mocked curl session (signup → login → browse catalog → book →
  pay → refetch) that the live server's actual JSON responses match what the automated
  tests assert, not just what the test client reports.
