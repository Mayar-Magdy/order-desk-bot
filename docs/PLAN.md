# Order Desk: plan

This is the approved design. It is updated as milestones are completed.

## Status

| # | Milestone | Status |
|---|---|---|
| 0 | Project skeleton, Docker Compose, CI, database roles | Done. CI green on all three jobs. |
| 1 | Sellers, isolation, webhook, language, couriers | Not started |
| 2 | Orders, state machine, transition log, lists | Not started |
| 3 | Ledger | Not started |
| 4 | Courier report import | Not started |
| 5 | Reconciliation and Excel export | Not started |
| 6 | Full-flow test, README, CV bullets | Not started |

## Product

Small sellers on Instagram and WhatsApp track orders in notebooks and lose
money on cash on delivery (COD), because what the courier collected does not
match what they shipped.

Order Desk is a Telegram bot with a backend. A seller records orders, tracks
shipping status, imports courier reports and reconciles courier payments. Each
Telegram user is a separate seller and must never see another seller's data.

**In scope, in priority order**

1. Record an order: customer name, phone, address, items, COD amount, courier,
   tracking number.
2. Update and view order status; list orders by status.
3. Import a courier report (CSV or Excel sent to the bot) and match rows to
   orders by tracking number.
4. Reconciliation: what the courier owes, what they paid and every
   discrepancy, as a summary message plus an Excel file.

**Out of scope:** web dashboard, courier APIs, online payments, inventory,
partial deliveries, anything customer-facing.

## Stack and versions

Versions were checked against PyPI and the official sites on 2026-11-16. Exact
versions are pinned in `uv.lock`.

| Part | Choice | Note |
|---|---|---|
| Language | Python 3.14 | 3.15.0 was five weeks old; 3.14 is the stable line every dependency supports |
| Web | FastAPI 0.163, Uvicorn 0.54 | Receives the Telegram webhook |
| Bot | aiogram 3.32 (from milestone 1) | Webhook mode in production, polling switch for local runs |
| Database | PostgreSQL 18 | Row-level security, two roles |
| ORM and migrations | SQLAlchemy 2.1, Alembic 1.20 | |
| Driver | psycopg 3.3 | One driver for the async app and for migrations |
| Excel | openpyxl 3.1 (from milestone 4) | Read and write; no pandas |
| Tests | pytest 9, Hypothesis 6 (from milestone 3) | |
| Quality | ruff 0.17, mypy 2.4 (strict) | |
| Packaging | uv | Lock file, reproducible installs |
| Runtime | Docker Compose, GitHub Actions | |

Decisions taken from the official docs:

- aiogram ships conversation-state storages for memory, Redis and MongoDB
  only. A small PostgreSQL storage class is written instead of adding Redis.
- aiogram's own webhook server is tied to aiohttp, so FastAPI receives the
  request and passes it to `Dispatcher.feed_update`.
- Translations use gettext `.po` files with Babel, which is what aiogram's
  i18n tools are built on.
- The PostgreSQL 18 Docker image stores data under `/var/lib/postgresql`, so
  the volume is mounted there.
- Starlette's test client now expects `httpx2`, so that is the test dependency.

## Order state machine

One explicit transition table. Anything not listed is rejected, including
same-state pairs.

| From | To | Who | Rule and effect |
|---|---|---|---|
| new | confirmed | seller | |
| new | cancelled | seller | |
| confirmed | handed_to_courier | seller | Needs courier and tracking number. Courier fees are copied onto the order. |
| confirmed | cancelled | seller | |
| handed_to_courier | delivered | seller or report row | Ledger: COD and delivery fee |
| handed_to_courier | delivery_failed | seller or report row | No money |
| handed_to_courier | returned | seller or report row | Ledger: return fee |
| delivery_failed | delivered | seller or report row | Ledger: COD and delivery fee |
| delivery_failed | returned | seller or report row | Ledger: return fee |
| delivered | settled | system only | When the order's balance with the courier reaches zero |
| delivered | handed_to_courier | seller (correction) | Reason required; only before a confirmed settlement; ledger reversed |
| delivery_failed | handed_to_courier | seller (correction) | Reason required |
| returned | handed_to_courier | seller (correction) | Reason required; only before a confirmed settlement; ledger reversed |

That is 13 legal pairs out of 64. `settled` and `cancelled` are final. Nobody
can set `settled` by hand.

Every transition writes a row to an append-only log: from, to, time, cause
(seller action, report row, settlement, correction) and a link to the cause.

## Data model

| Table | Main columns | Notes |
|---|---|---|
| sellers | telegram_user_id (unique), language, next_order_number | One per Telegram user |
| couriers | name, delivery_fee, return_fee, report_format (JSON) | Column mapping and status words |
| orders | order_number, customer name/phone/address, cod_amount, courier_id, tracking_number, fee snapshots, status | Tracking number unique per seller and courier |
| order_items | description, quantity | |
| order_transitions | from, to, cause, cause link, note, time | Append-only |
| settlements | courier_id, file hash, file name, cut-off date, actual_payout, status | One report file plus one payout. Status: draft, confirmed, closed |
| settlement_rows | row number, raw data, tracking number, reported status, amounts, matched order, classification | One per file row |
| discrepancies | type, order, row, signed amount, status, resolution, ledger link | |
| ledger_transactions | kind, idempotency_key (unique), links to order, settlement, discrepancy | Append-only |
| ledger_entries | account, courier, order, signed amount | Append-only |
| fsm_states | chat, user, state, data | Bot conversation state |
| telegram_updates | update_id | Ignores repeated webhook deliveries |

All amounts are integer piastres (EGP x 100). Floats are never used. No
balance or total is stored, except the actual payout, which is a fact the
seller types in.

### Seller isolation

Three layers:

1. Every table has `seller_id`, and all queries go through one scoped
   data-access layer.
2. Foreign keys include `seller_id`, so an order cannot point at another
   seller's courier.
3. PostgreSQL row-level security blocks cross-seller rows even if application
   code has a bug.

### Database roles

| Role | Used by | Powers |
|---|---|---|
| orderdesk_owner | Migrations only | Owns the tables |
| orderdesk_app | The running application and the tests | Not a superuser, owns nothing, cannot bypass row-level security. Gets privileges table by table in migrations. No UPDATE or DELETE on ledger and transition tables. |

## Ledger

Double-entry bookkeeping with signed integers. Every transaction's lines add
up to zero. Rows are never updated or deleted; a mistake is fixed by posting
the opposite lines.

| Account | Meaning |
|---|---|
| COURIER_RECEIVABLE | What the courier owes the seller |
| CASH | Money actually received |
| COD_SALES | COD value of delivered orders |
| COURIER_FEES | Delivery and return fees |
| DISCREPANCY | Money written off or gained, always with a reason code |

| Event | Lines |
|---|---|
| Order delivered | RECEIVABLE +COD, COD_SALES -COD; COURIER_FEES +fee, RECEIVABLE -fee |
| Order returned | COURIER_FEES +return fee, RECEIVABLE -return fee |
| Correction | The exact opposite of the original lines |
| Payout | CASH +paid, RECEIVABLE -paid (split per order) |
| Write-off | DISCREPANCY +x, RECEIVABLE -x |
| Courier pays a difference later | CASH +x, RECEIVABLE -x |

- "What the courier owes" is the sum of that courier's RECEIVABLE lines.
- An order becomes `settled` when its own RECEIVABLE lines sum to zero.
- Each transaction has a unique idempotency key, so a retry cannot post twice.

**Settlement rule.**

```
expected payout = COD of delivered orders
                  minus delivery fees
                  minus return fees

expected payout minus actual payout = sum of named discrepancies
```

If the second line does not hold, the settlement cannot be confirmed. Nothing
is left unexplained.

**Example.** Order A: COD 500, fee 50. Order B: returned, fee 30. The report
says A collected 450, and the courier paid 370. Expected is 420, actual is
370. The difference of 50 is an amount mismatch on A. If the seller accepts
it, a write-off of 50 is posted and A becomes settled.

## Import and reconciliation

Import has two steps. First the file is parsed and every row is classified;
nothing changes. Then the seller enters the payout and confirms.

- Re-importing the same file (same hash, same courier) returns the earlier
  result and changes nothing.
- Nothing is auto-corrected. Clean rows are applied on confirmation; every
  other row becomes a discrepancy that the seller resolves.
- **A row whose status matches the order's current state is a clean match.**
  For example, "delivered" for an order the seller already marked delivered.
  It makes no transition and simply joins the settlement.

| Discrepancy | Meaning | Seller's choices |
|---|---|---|
| amount_mismatch | Row COD differs from order COD | Accept and write off, or record a later payment |
| fee_mismatch | Row fee differs from the agreed fee (only if the file has a fee column) | Same |
| unknown_tracking | Row matches no order | Link to an order, or record as unidentified money |
| duplicate | Tracking number repeated, or already settled | Pick the valid row; the others become unidentified |
| status_conflict | Row status is illegal for the order's state | Correct the order, or reject the row |
| missing_from_report | Shipped before the cut-off date, not in the file | Carry over, or update the order |
| payout_difference | Report total differs from money received | Record a later payment, or write off |

Every resolution that moves money writes a ledger transaction. **A carry-over
writes no ledger entry**, because no money has moved; it is recorded on the
discrepancy.

Two synthetic sample reports are used as test fixtures: one CSV with English
headers and one Excel file with Arabic headers, both with deliberate
discrepancies.

## Order lists

Lists are filtered by status. A returned order whose return fee has not been
cleared by a settlement is marked "return fee unpaid". The flag is derived
from the ledger, never stored.

## Testing rules

- Every legal and illegal state pair is tested (all 64).
- Money invariants are tested with Hypothesis: every transaction sums to
  zero, balances equal a full recount, and the settlement rule holds.
- Both sample reports are imported, and imported again to prove nothing
  changes.
- A report row that matches the order's current state is tested as a clean
  match with no transition.
- **Seller-isolation tests and ledger no-update tests run as `orderdesk_app`,
  never as the table owner or a superuser**, locally and in CI. A session
  guard in `tests/conftest.py` aborts the run if the test connection is a
  superuser, can bypass row-level security, owns any object or is a member of
  another role.
- Tests only run against a database whose name ends with `_test`.

## Business rules assumed (all accepted)

1. Fees are flat per courier, not per zone, and are copied to the order at
   handover.
2. A delivered order pays only the delivery fee. A returned order pays only
   the return fee.
3. A failed attempt costs nothing by itself, and a retry adds no second
   delivery fee.
4. There are no returns after delivery.
5. Cancelling is allowed only before handover. After that the parcel must come
   back as returned.
6. An order must be confirmed before handover.
7. COD can be zero (paid another way) but never negative.
8. Items are description and quantity only. COD is typed as one total.
9. Customer details live on the order. There is no customers table.
10. Phones are Egyptian mobile numbers, stored as +20. Arabic digits are
    accepted for phones and amounts.
11. Tracking numbers match exactly after trimming spaces and ignoring letter
    case. There is no fuzzy matching.
12. One file is one courier, one settlement and one payout. The seller types
    the amount actually received.
13. A report must have tracking number, status and COD collected. A fee column
    is optional.
14. The seller sets up a format by sending a sample file and choosing columns
    and status meanings with buttons.
15. The seller confirms a cut-off date at import. That date decides which
    orders count as missing.
16. Clean rows are applied when the seller confirms. This is not
    auto-correcting.
17. For a duplicated tracking number, no row is applied until the seller picks
    one.
18. Amounts with more than two decimals, and CSV files that are not UTF-8, are
    rejected with a clear message.
19. Lost parcels are not modelled (see known gaps).
20. Times are stored in UTC and shown in Cairo time.
21. One Telegram account is one seller, in private chat only. There are no
    staff accounts.
22. Orders are never deleted, only cancelled.

## Agreed differences from the first brief

- A carry-over writes no ledger entry.
- A correction transition exists, because sellers will tap the wrong button.
- Returned orders stay `returned`. Only delivered orders become `settled`. The
  return fee is cleared through the ledger and shown in lists while unpaid.
- A polling switch exists for local runs, because a webhook needs a public
  HTTPS address. Production stays on webhook.

## Known gaps for a later version

- **Lost parcels.** There is no `lost` state and no courier compensation. A
  lost order stays open and appears as missing in every reconciliation until
  the seller records an outcome.

## Milestones

| # | Content | Key tests |
|---|---|---|
| 0 | Repo, Docker Compose, FastAPI health check, Alembic, ruff, mypy, pytest, CI, pinned versions, database roles | Health check, role guard, migration round trip |
| 1 | Sellers, isolation, webhook, language choice, translations, couriers with fees | One seller cannot read another's data (as `orderdesk_app`) |
| 2 | Record order, validation, state machine, transition log, view and list by status | All 64 state pairs |
| 3 | Ledger, postings on delivered and returned, corrections, "courier owes", unpaid return fee flag | Property tests: zero-sum, balances match a full recount; no UPDATE or DELETE as `orderdesk_app` |
| 4 | Report format setup, CSV and Excel parsers, two synthetic fixtures, matching, draft preview | Both fixtures, re-import, same-status clean match |
| 5 | Confirm settlement, discrepancies, resolutions, summary message, Excel file | Property tests for the settlement rule |
| 6 | Full-flow test, README with diagram, new courier format guide, CV bullets | Whole flow from one compose command |

## Milestone notes

### Milestone 0

- `docker compose up --build` starts PostgreSQL, runs migrations as the owner
  role, then starts the API as the application role.
- `docker/postgres/init-roles.sh` creates both roles. The same script is used
  by Compose, by CI and for local setup, so the roles are always identical.
- Migration `0001` removes default access to the `public` schema and grants
  the application role lookup access only.
- CI has three jobs: lint and type check, tests against PostgreSQL 18 as the
  restricted role, and a Compose start with a health check.
- Verified in CI on 2026-11-16: lint and types, 11 tests against PostgreSQL
  18.7 as the restricted role, and the Compose stack starting and answering
  `/healthz`. The Docker image and Compose start are verified only in CI,
  because the build environment has no access to image registries.
- Commits use GitHub's no-reply address as author.
