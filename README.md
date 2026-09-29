# EVE Healthcare Diagnostic Booking API

A backend service for booking diagnostic tests at partner centres and paying for them
through a **simulated** payment provider, built as a take-home SDE Intern assignment.

## 1. Overview

Users sign up, browse diagnostic centres and the tests they offer, book a test, and pay
for it through a mock payment flow. A signed webhook lets the "provider" push the
authoritative payment status back to the API — idempotently, so retries and duplicate
deliveries never corrupt state.

## 2. Features

- Email/password signup and login with JWT bearer authentication
- Diagnostic centres and tests, with a per-centre price for each test (N:M with price)
- Booking lifecycle with a centrally-enforced state machine
- Simulated payment initiation (`POST /payments/`) — no real gateway
- **Idempotent** signed webhook (`POST /payments/webhook/`) for asynchronous settlement
- Ownership-based authorization (users only see their own bookings/payments) plus a
  simple admin role for catalog management
- Pagination on all list endpoints
- Structured JSON logging with request correlation IDs
- 113 tests (unit + integration, including a real concurrency test) at 95% line coverage
- Docker Compose for one-command local setup; GitHub Actions CI

## 3. Tech stack

Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.x · Alembic · PostgreSQL 16 ·
PyJWT · pwdlib (Argon2) · pytest · Ruff · Docker · GitHub Actions.

## 4. Architecture

```
app/
  main.py                  # app factory, exception handlers, health/ready
  core/                    # config, security (JWT/password/HMAC), logging
  db/                      # engine/session, declarative Base
  models/                  # SQLAlchemy ORM models (one file per table)
  schemas/                 # Pydantic request/response models
  api/
    deps.py                # get_current_user, require_admin, pagination
    routes/                # thin FastAPI routers — no business logic here
  services/                # business logic, transactions, state machine
alembic/                   # migrations (no create_all() in production)
tests/
  unit/                    # pure-function tests: security, state machine, schemas
  integration/             # full HTTP tests against a real PostgreSQL test DB
scripts/seed.py            # optional dev seed data
```

**Layering rule:** routes only validate input (via Pydantic), call a service, and return
the result. All business logic, transactions and locking live in `services/`. This keeps
routes trivially readable and lets services be unit-tested without an HTTP client if
needed. Repository classes were deliberately **not** added — each service uses SQLAlchemy
directly, because at this schema size a repository layer would just be a thin, untested
wrapper around `db.scalars(select(...))` with no real abstraction value.

### Architecture diagram

```mermaid
flowchart LR
    Client -->|JWT Bearer| FastAPI
    Provider[Simulated Payment Provider] -->|HMAC-signed webhook| FastAPI
    subgraph API[FastAPI app]
        Auth[Auth routes]
        Centres[Centre/Test routes]
        Bookings[Booking routes]
        Payments[Payment routes]
        Webhooks[Webhook route]
    end
    FastAPI --> Auth & Centres & Bookings & Payments & Webhooks
    Auth --> AuthSvc[auth_service]
    Centres --> CatalogSvc[catalog_service]
    Bookings --> BookingSvc[booking_service]
    Payments --> PaymentSvc[payment_service]
    Webhooks --> WebhookSvc[webhook_service]
    AuthSvc & CatalogSvc & BookingSvc & PaymentSvc & WebhookSvc --> ORM[SQLAlchemy]
    ORM --> PG[(PostgreSQL)]
```

## 5. Database schema / ER diagram

```mermaid
erDiagram
    USERS ||--o{ BOOKINGS : places
    DIAGNOSTIC_CENTRES ||--o{ CENTRE_TESTS : offers
    DIAGNOSTIC_TESTS ||--o{ CENTRE_TESTS : "offered as"
    CENTRE_TESTS ||--o{ BOOKINGS : "booked via"
    BOOKINGS ||--o{ PAYMENTS : has

    USERS {
        uuid id PK
        string email UK
        string hashed_password
        string full_name
        enum role
    }
    DIAGNOSTIC_CENTRES {
        uuid id PK
        string name
        string location
    }
    DIAGNOSTIC_TESTS {
        uuid id PK
        string name UK
        text description
    }
    CENTRE_TESTS {
        uuid centre_id FK
        uuid test_id FK
        numeric price
    }
    BOOKINGS {
        uuid id PK
        uuid user_id FK
        uuid centre_id FK
        uuid test_id FK
        timestamptz appointment_at
        numeric amount
        enum status
    }
    PAYMENTS {
        uuid id PK
        uuid booking_id FK
        numeric amount
        enum status
        string provider_reference UK
    }
    WEBHOOK_EVENTS {
        uuid id PK
        string provider_event_id UK
        string event_type
        string payment_reference
        string payload_hash
    }
```

Key design points:

- **`CENTRE_TESTS` is the N:M junction and the only place price lives.** A `Booking`
  snapshots `amount` from it at creation time, so a later price change never alters an
  existing booking (tested in `test_price_update_does_not_retroactively_change_existing_bookings`).
- `Booking` has a composite FK `(centre_id, test_id) -> centre_tests(centre_id, test_id)`,
  so the database itself rejects booking a test a centre doesn't offer — not just app code.
- A **partial unique index** on `bookings (user_id, centre_id, test_id, appointment_at)
  WHERE status IN ('PENDING','CONFIRMED')` stops a double-submit from creating two live
  bookings for the same slot, while still allowing a new booking after the old one is
  cancelled or failed.
- A **partial unique index** on `payments (booking_id) WHERE status IN ('PENDING','SUCCESS')`
  is the database-level guarantee behind "no duplicate payments" — it holds even if two
  requests race past the application-level check.
- `webhook_events.provider_event_id` is `UNIQUE` — this one constraint *is* the webhook
  idempotency mechanism (see §9).
- All money is `NUMERIC(10,2)`, never `float`. All timestamps are `timestamptz`, stored
  and compared in UTC.

## 6. Booking state machine

```
PENDING -> CONFIRMED   (payment succeeds)
PENDING -> FAILED      (payment fails)
PENDING -> CANCELLED   (user cancels before paying)
CONFIRMED -> CANCELLED (user cancels after paying; payment is refunded)
FAILED, CANCELLED      are terminal
```

Every transition goes through `services/state_machine.py::ensure_booking_transition`,
which is a single dict of `{current: {allowed targets}}`. No route or service mutates
`.status` without going through this — so `FAILED -> CONFIRMED` or `CANCELLED ->
CONFIRMED` are structurally impossible, not just "usually prevented." Illegal transitions
raise `InvalidStateTransition` → HTTP 409.

## 7. Payment flow (simulated)

```
1. POST /bookings              -> booking PENDING, amount snapshotted from CENTRE_TESTS
2. POST /payments/              -> creates a Payment (PENDING), calls the *local* simulator
   3a. simulator returns SUCCESS/FAILED synchronously -> booking updated in the same call
   3b. simulator returns PENDING (`simulate_outcome: "PENDING"`) -> settled later by webhook
4. POST /payments/webhook/      -> provider's authoritative status, applied idempotently
```

`payment_service.settle_payment()` is the single function that applies a payment result
and the matching booking transition **together**, and it is called from both the
synchronous payment path and the webhook path — so the two can never disagree about the
rules, and an inconsistent state like `payment SUCCESS + booking FAILED` cannot arise.
There is no real payment gateway anywhere in this codebase; `PAYMENT_SUCCESS_RATE`
controls only the local simulator's random outcome (overridable per-request via
`simulate_outcome` for deterministic testing).

## 8. Webhook idempotency strategy

The idempotency key is the provider's `event_id`. `webhook_events.provider_event_id`
carries a **UNIQUE constraint enforced by PostgreSQL**, not an in-memory set — so it is
correct even across process restarts, multiple workers, or multiple containers.

```python
INSERT INTO webhook_events (provider_event_id, ...) VALUES (...)
ON CONFLICT (provider_event_id) DO NOTHING
RETURNING id;
```

- If the `INSERT` returns a row, this request **claimed** the event: it applies the
  payment/booking update in the *same transaction* and commits both together. A crash
  between the claim and the commit rolls back the whole transaction, so the event is
  simply unclaimed and the next retry is treated as the first delivery — no event is ever
  "half applied."
- If the `INSERT` returns nothing, another request already claimed this `event_id`
  (possibly seconds or months ago): this is a **retry**. It is reported back as
  `DUPLICATE` with zero side effects — no new payment, no new booking, no status change.
- Two concurrent identical deliveries race on the same unique index: PostgreSQL makes the
  second `INSERT` **block** until the first transaction commits or rolls back, then
  fails its own insert and falls into the duplicate path. This is proven directly by
  `test_concurrent_identical_webhooks_apply_exactly_once`, which fires 8 identical
  requests from 8 threads at once against the real test database and asserts exactly one
  `APPLIED` and seven `DUPLICATE`.
- **Same event id, different payload** (a provider bug or a forged retry) is detected by
  comparing a SHA-256 hash of the canonicalised payload against the one stored on first
  receipt, and rejected as `409 EVENT_PAYLOAD_MISMATCH` rather than silently treated as a
  duplicate.
- **Event for an unknown payment reference** rolls back the claim (via `db.rollback()`)
  before raising `404`, so the event id is *not* consumed — a later, legitimate delivery
  of the same event (after the payment exists) still applies normally.
- **Event that conflicts with an already-final payment** (e.g. a stray `payment.failed`
  after `payment.succeeded` was already applied) is recorded with outcome `IGNORED` and
  logged at ERROR for a human to look at, but the payment/booking state is **not**
  rewritten — a webhook is never allowed to un-confirm history.

## 9. Webhook security

Requests are authenticated by an **HMAC-SHA256 signature**, not JWT (the provider isn't a
logged-in user). The provider signs `"{timestamp}.{raw request body}"` with a shared
secret and sends:

- `X-Webhook-Timestamp`: unix seconds
- `X-Webhook-Signature`: hex HMAC-SHA256 of the string above

The server recomputes the same HMAC and compares it with `hmac.compare_digest`
(constant-time, to avoid a timing side-channel), and rejects the timestamp if it is more
than `WEBHOOK_TOLERANCE_SECONDS` (default 300s) away from "now" — a replay-protection
window, same idea Stripe/GitHub webhooks use. The secret lives only in `WEBHOOK_SECRET`
(env var), never in source. Signature verification happens **before** the JSON body is
even parsed, so malformed/oversized payloads from an unauthenticated caller are rejected
immediately.

## 10. Authentication / authorization model

- **Authentication** (`get_current_user`): is the JWT valid, unexpired, and does its
  subject match a real user? Failure → `401`.
- **Authorization** is enforced per-resource, not just per-role:
  - Centres/tests: public `GET`, admin-only `POST`/`PATCH`/`PUT` (`require_admin` → `403`
    for a non-admin).
  - Bookings/payments: every query is scoped with `WHERE user_id = :current_user_id` (or
    a join through the booking for payments). A booking or payment that exists but
    belongs to someone else is reported as **404, not 403** — this avoids confirming
    that a given booking ID exists at all to a non-owner (`test_user_cannot_see_or_cancel_another_users_booking`,
    `test_cannot_pay_for_someone_elses_booking`).
- Login timing is equalised (`auth_service.authenticate` always runs one password
  verification, even for an unknown email, against `DUMMY_HASH`) so response time cannot
  be used to enumerate registered emails.

## 11–13. API endpoints, examples & responses

Full interactive docs (with request/response schemas) are at **`/docs`** once the app is
running. Summary:

| Method | Path | Auth | Notes |
|---|---|---|---|
| POST | `/auth/signup` | — | |
| POST | `/auth/login` | — | OAuth2 form fields; `username` = email |
| GET | `/auth/me` | user | |
| GET | `/centres` | — | paginated |
| POST | `/centres` | admin | |
| GET | `/centres/{id}` | — | |
| PATCH | `/centres/{id}` | admin | |
| GET | `/centres/{id}/tests` | — | paginated; includes price |
| PUT | `/centres/{id}/tests/{test_id}` | admin | upsert price |
| GET | `/tests` | — | paginated |
| POST | `/tests` | admin | |
| GET | `/tests/{id}` | — | |
| POST | `/bookings` | user | amount taken from current price, not client input |
| GET | `/bookings` | user | paginated, `?status=` filter, owner-scoped |
| GET | `/bookings/{id}` | user (owner) | |
| POST | `/bookings/{id}/cancel` | user (owner) | |
| POST | `/payments/` | user (owner of booking) | simulated |
| GET | `/payments/{id}` | user (owner) | |
| POST | `/payments/webhook/` | HMAC signature | idempotent |
| GET | `/health` | — | liveness |
| GET | `/ready` | — | readiness (checks DB) |

### End-to-end example

```bash
# 1. Sign up and log in
curl -X POST localhost:8000/auth/signup -H 'Content-Type: application/json' \
  -d '{"email":"pat@example.com","password":"Passw0rd1","full_name":"Pat"}'

TOKEN=$(curl -s -X POST localhost:8000/auth/login \
  -d 'username=pat@example.com&password=Passw0rd1' | python3 -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 2. Browse centres and tests
curl localhost:8000/centres
curl localhost:8000/centres/<centre_id>/tests

# 3. Book a test (amount comes from the centre's current price)
curl -X POST localhost:8000/bookings -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"centre_id":"<centre_id>","test_id":"<test_id>","appointment_at":"2026-11-01T09:00:00+05:30"}'
# -> {"id": "<booking_id>", "status": "PENDING", "amount": "450.00", ...}

# 4. Pay (simulated)
curl -X POST localhost:8000/payments/ -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"booking_id":"<booking_id>","simulate_outcome":"SUCCESS"}'
# -> {"id": "<payment_id>", "status": "SUCCESS", "provider_reference": "sim_...", ...}

# 5. Booking is now CONFIRMED
curl localhost:8000/bookings/<booking_id> -H "Authorization: Bearer $TOKEN"

# 6. (Provider-side) webhook, HMAC-signed — see scripts below to compute the signature
curl -X POST localhost:8000/payments/webhook/ \
  -H 'Content-Type: application/json' -H "X-Webhook-Timestamp: <ts>" -H "X-Webhook-Signature: <sig>" \
  -d '{"event_id":"evt-1","event_type":"payment.succeeded","payment_reference":"sim_..."}'

# 7. Cancel (only PENDING/CONFIRMED can be cancelled)
curl -X POST localhost:8000/bookings/<booking_id>/cancel -H "Authorization: Bearer $TOKEN"
```

## 14. Error handling

Every error response has the same shape:

```json
{"error": {"code": "BOOKING_NOT_PAYABLE", "message": "Booking is CANCELLED and cannot be paid", "request_id": "..."}}
```

`code` is a stable machine-readable string (`NOT_FOUND`, `EMAIL_ALREADY_REGISTERED`,
`INVALID_STATE_TRANSITION`, `EVENT_PAYLOAD_MISMATCH`, ...); `message` is human-readable;
`request_id` matches the `X-Request-ID` response header and the structured log line for
that request, for support/debugging. Unhandled exceptions and raw `IntegrityError`s are
caught by global handlers, logged with a full traceback server-side, and returned to the
client as a generic `500`/`409` — stack traces are never exposed over the API.

## 15. Local setup (without Docker)

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements-dev.txt

createdb eve                       # requires a local PostgreSQL 16
cp .env.example .env               # then edit JWT_SECRET_KEY / WEBHOOK_SECRET
alembic upgrade head
python -m scripts.seed             # optional: sample centres/tests + an admin user
uvicorn app.main:app --reload
```

Swagger UI: http://localhost:8000/docs · ReDoc: http://localhost:8000/redoc

## 16. Docker setup

```bash
docker compose up --build
```

This starts `postgres`, runs `migrate` (Alembic, one-shot) to completion, then starts
`api` on `http://localhost:8000`. Override secrets via a `.env` file or exported
environment variables (`JWT_SECRET_KEY`, `WEBHOOK_SECRET`); sane development defaults are
provided so `up --build` works out of the box. Seed data is **not** run automatically —
`docker compose exec api python -m scripts.seed` after startup, if wanted.

> **Note on this submission:** Docker was not installed in the sandbox this project was
> built in, so `docker compose up --build` itself could not be executed here. The
> Dockerfile and compose file were reviewed carefully (multi-stage-free single build,
> non-root user, healthcheck, explicit service dependency ordering via
> `service_completed_successfully`) and their YAML was syntax-validated, but please run
> `docker compose up --build` yourself before/at submission to confirm the images build
> in your environment — see `FINAL_REVIEW.md` for the full list of what is and isn't
> independently verified.

## 17. Environment variables

See `.env.example` for the full list with defaults. Required with no default:
`DATABASE_URL`, `JWT_SECRET_KEY` (≥32 chars), `WEBHOOK_SECRET` (≥16 chars) — the app
refuses to start without them, by design (no silent insecure defaults in production).

## 18. Database migrations

Alembic-managed; `Base.metadata.create_all()` is never used outside the test suite's own
bootstrap. `alembic upgrade head` applies migrations; `alembic downgrade base` reverts
them. `alembic revision --autogenerate -m "..."` for future schema changes (review the
generated file before committing — see `alembic/versions/0001_initial_schema.py` for the
one included here).

## 19. Seed data

`python -m scripts.seed` inserts 3 centres, 6 test types, 11 centre/test/price offerings,
and one admin user (`admin@eve-healthcare.test` / `AdminPass123` — change immediately if
ever used somewhere real). It's idempotent-by-emptiness: it no-ops if any centre already
exists, so it's safe to run more than once.

## 20. Running tests

```bash
createdb eve_test   # a SEPARATE database from the dev one; tests TRUNCATE it between cases
pytest                              # 113 tests
pytest --cov=app --cov-report=term-missing   # with coverage
```

Integration tests run against a **real PostgreSQL** (not SQLite, not mocks) — this
matters specifically for the idempotency tests, which rely on PostgreSQL's `ON CONFLICT`
and row-locking semantics that SQLite doesn't replicate. `TEST_DATABASE_URL` overrides
the default (`postgresql+psycopg://postgres:postgres@localhost:5432/eve_test`), e.g. for
CI. The schema is built via `alembic upgrade head` in a session-scoped fixture (so the
migrations themselves are exercised, not just the models), and every table is truncated
between tests for isolation.

## 21. Test coverage / results

**113 passed, 0 failed**, 95% line coverage (`pytest --cov=app`), including:

- A genuine concurrency test (8 threads, same webhook event, real Postgres) proving
  exactly one `APPLIED` and seven `DUPLICATE`.
- All 12 "critical tests" called out in the assignment spec (see `FINAL_REVIEW.md` §C
  for the explicit checklist against that list).

Uncovered lines are almost entirely defensive/unreachable branches (e.g. the generic
500-handler body, a couple of `IntegrityError` backstops behind row locks that make the
race window essentially unreachable in a single-process test) — see `FINAL_REVIEW.md`.

## 22. CI pipeline

`.github/workflows/ci.yml` spins up a `postgres:16-alpine` service container, then runs
`ruff check`, `ruff format --check`, `alembic upgrade head`, and the full test suite with
coverage on every push/PR to `main`.

## 23. Design decisions

- **Why FastAPI?** Native Pydantic v2 validation, dependency injection that maps cleanly
  onto "authentication vs authorization" (`CurrentUser` vs `AdminUser` deps), and
  automatic OpenAPI docs — all directly useful for this assignment's requirements.
- **Why PostgreSQL?** The assignment requires it, and the idempotency design specifically
  needs a real unique constraint + row locking that survive process/container restarts —
  properties an in-memory store cannot offer.
- **Why SQLAlchemy 2.x?** Modern typed `Mapped[...]` models, first-class `ON CONFLICT`
  (`postgresql.insert`) for race-free upserts, and explicit `with_for_update()` for the
  locking this design relies on.
- **Why Alembic?** Migrations are how a real team evolves a schema safely; `create_all()`
  has no upgrade/downgrade story and was explicitly disallowed for production use.
- **Why JWT?** Stateless bearer auth is simple to reason about and test, and is what the
  assignment explicitly asks for.
- **Why a database-backed idempotency key instead of an in-memory set?** The assignment
  explicitly requires idempotency to survive process restarts and multiple
  workers/containers — a Python `dict` in one process cannot do that; a `UNIQUE`
  constraint in the shared database can.
- **Why unique event IDs specifically (vs. e.g. hashing the payload)?** The provider
  defines "this is the same delivery" by event id, not payload — hashing the payload
  would treat two genuinely different events with coincidentally identical content as
  duplicates, and would fail to catch a delivery whose payload was corrupted in transit.
  Both are checked here: event id for idempotency, payload hash for tamper/conflict
  detection.
- **Why transactions everywhere in the service layer?** Booking creation, payment
  settlement, and webhook processing each touch 1-2 rows that must change together or not
  at all; a partial write (e.g. payment SUCCESS but booking still PENDING) would be a
  silent data-integrity bug.
- **Why `Decimal`/`NUMERIC(10,2)` for money?** `float` cannot represent most currency
  values exactly (`0.1 + 0.2 != 0.3`); accumulating that error across bookings and
  payments is unacceptable for anything involving money.
- **Why does `Booking` store the charged amount instead of joining to `CENTRE_TESTS`
  for the price?** A centre's price can legitimately change over time; a booking must
  keep the price the patient actually agreed to, permanently — see the dedicated test in
  §5.
- **Why centralise status transitions in one module?** So "can X move to Y" has exactly
  one implementation, checked by exhaustive tests (`test_every_other_booking_transition_is_rejected`
  parametrizes *every* pair not on the allow-list) — instead of trusting every route/service
  author to remember every rule.
- **Why was Redis not used?** The only plausible use here (caching centre/test listings)
  adds cache-invalidation complexity for a dataset small enough that PostgreSQL alone
  comfortably serves it within a 3-4 hour assignment's scope; it wasn't worth the added
  moving part.
- **Why was Celery not used?** There is no genuinely long-running or scheduled work here
  — the "async" part of payments is handled by the webhook itself, which is a plain
  synchronous endpoint. Celery would add a broker and worker process with no matching job.
- **Why was a real payment gateway intentionally excluded?** The assignment explicitly
  forbids it; a local simulator + signed webhook is enough to demonstrate the same
  architectural problem (idempotent settlement of an asynchronous, authoritative event)
  without any external dependency, cost, or compliance surface.

## 24. Important assumptions

- A user cancelling a `CONFIRMED` (already-paid) booking triggers a **simulated** refund
  (`payment.status -> REFUNDED`); no money actually moves anywhere.
- `appointment_at` must be timezone-aware in the request and is normalised to UTC on
  input; a naive datetime is rejected rather than guessed at.
- One admin role is enough to demonstrate "authentication ≠ authorization"; a full RBAC
  system was explicitly out of scope per the assignment.
- The webhook is a single provider integration point in the URL scheme the assignment
  specifies (`POST /payments/webhook/`); a real system with multiple providers would
  likely namespace this per-provider.
- `PAYMENT_SUCCESS_RATE` and `simulate_outcome` exist purely to make the simulator
  demonstrable/testable; `ALLOW_SIMULATION_OVERRIDE=false` would disable client control
  of the outcome in a "hardened demo" setting.

## 25. Tradeoffs

- No repository layer: fewer files and less ceremony, at the cost of services talking to
  SQLAlchemy directly. Reasonable at this schema size; would revisit past ~10 tables or
  multiple swappable storage backends.
- No caching layer: simpler and one less moving part to explain, at the cost of every
  `GET /centres` hitting PostgreSQL directly. Fine at this scale.
- Booking cancellation blocks while a payment is `PENDING` (`PAYMENT_IN_PROGRESS`, 409)
  rather than trying to cancel-and-race the in-flight payment — simpler and safer, at the
  cost of the user having to wait or retry.
- Admin users are seeded directly into the database / test fixtures rather than exposed
  through a `POST /auth/signup?role=admin`-style endpoint, to avoid a self-service
  privilege-escalation surface that the assignment doesn't ask for.

## 26. What would be improved with more time

- Rate limiting on `/auth/login` and `/auth/signup` (brute-force / abuse protection).
- An admin-facing "list all bookings/payments" endpoint with filters, separate from the
  owner-scoped user endpoints.
- Soft-delete / audit history on catalog changes (currently a `PATCH`/`PUT` simply
  overwrites).
- A background reconciliation job that periodically re-queries the (simulated) provider
  for any payment stuck `PENDING` past a timeout, instead of relying solely on the
  webhook arriving.
- Structured log shipping (e.g. to a real log aggregator) instead of stdout JSON lines.

## 27. Known limitations

- Docker build/compose was written and reviewed but **not executed** in the environment
  this was built in (no Docker available there) — verify locally before submission.
- No rate limiting is implemented (see §26).
- The simulated payment provider is a local function, not a separate process — there is
  no network boundary to simulate provider latency/timeouts.
- Email verification is not implemented; any syntactically valid, unused email can sign up.

## 28. Example end-to-end workflow

See §11–13 above for the full curl sequence (signup → login → browse → book → pay →
webhook → query → cancel).
