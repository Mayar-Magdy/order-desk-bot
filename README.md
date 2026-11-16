# Order Desk

A Telegram bot with a backend for small sellers on Instagram and WhatsApp. It
records orders, tracks shipping status, imports courier reports and reconciles
cash-on-delivery payments, so a seller can see exactly what each courier owes.

**Status:** milestone 0 of 6 is complete (project skeleton). The full design,
business rules and milestone plan are in [docs/PLAN.md](docs/PLAN.md). This
README will be completed in the final milestone.

## Run it

Requires Docker with Compose.

```bash
docker compose up --build
```

This starts PostgreSQL 18, applies the migrations and starts the API. Check it:

```bash
curl http://127.0.0.1:8000/healthz
# {"status":"ok"}
```

The default passwords are for local development only. For anything else, copy
`.env.example` to `.env` and set your own.

## Develop

Requires [uv](https://docs.astral.sh/uv/) and a running database.

```bash
docker compose up -d db      # PostgreSQL with both roles and a test database
uv sync                      # install dependencies from the lock file

uv run pytest                # tests
uv run ruff check .          # lint
uv run ruff format --check . # formatting
uv run mypy                  # type check (strict)
```

### Database roles

| Role | Used by | Powers |
|---|---|---|
| `orderdesk_owner` | Migrations | Owns the tables |
| `orderdesk_app` | The application and the tests | Not a superuser, owns nothing, cannot bypass row-level security |

Tests always connect as `orderdesk_app`. If the test connection is a superuser,
a table owner or able to bypass row-level security, the run stops before any
test executes. This keeps the security tests honest.

### Migrations

```bash
export ORDERDESK_MIGRATIONS_DATABASE_URL=postgresql+psycopg://orderdesk_owner:owner-dev-only@127.0.0.1:5432/orderdesk
uv run alembic upgrade head
```
