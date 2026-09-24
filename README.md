# SmartFin

A self-hosted personal finance dashboard for Israeli bank and credit-card accounts. It pulls in
transactions automatically, tracks spending against a budget, and sends alerts. It runs on a
home server or Raspberry Pi with Docker Compose.

Design doc: [SmartFin — Architecture & Build Strategy](https://claude.ai/artifact/5jAc5LqeFBF5DHjeyVLBMy)

## Layout

| Path | What it is |
|---|---|
| `backend/` | FastAPI API, SQLAlchemy models, Alembic migrations |
| `scraper/` | Node.js service using [israeli-bank-scrapers](https://github.com/eshaham/israeli-bank-scrapers) |
| `docker-compose.yml` | Postgres, backend and scraper on separate Docker networks |

## Status

- [x] **Phase 1: Foundation.** Compose skeleton, data model and migrations, one-shot manual scrape
- [x] **Phase 2: Sync.** Nightly scrape of every account into Postgres, de-duplication, scrape logging
- [x] **Phase 3: Categorization and budgets.** Rules, manual overrides, monthly budgets, spend-vs-budget
- [ ] Phase 4: Alerts (Telegram / email)
- [ ] Phase 5: Dashboard
- [ ] Phase 6: Hardening (backups, credential encryption, failure alerts)

## Running it

```sh
cp .env.example .env    # set POSTGRES_PASSWORD and INGEST_TOKEN (openssl rand -hex 32)
cp scraper/config/accounts.example.json scraper/config/accounts.json   # your bank logins
docker compose up -d --build
curl localhost:8000/health    # {"status":"ok","database":"ok"}
```

Create `accounts.json` before the first `up`, or Docker creates an empty directory in its
place. Each entry is `{"company": ..., "credentials": {...}}`, and the fields each company needs are:

| Company | Credentials |
|---|---|
| `leumi`, `mizrahi`, `max`, `visaCal`, `otsarHahayal`, `union`, `beinleumi`, `massad`, `pagi` | `username`, `password` |
| `hapoalim` | `userCode`, `password` |
| `discount`, `mercantile` | `id`, `password`, `num` |
| `isracard`, `amex` | `id`, `card6Digits`, `password` |
| `yahav` | `username`, `nationalID`, `password` |
| `beyahadBishvilha`, `behatsdaa` | `id`, `password` |

### How sync works

The scraper service logs into each account in turn every night at `SCRAPE_TIME` (Israel time)
and fetches the last `SCRAPER_DAYS_BACK` days. It sends the results to the backend's
`/internal/ingest` endpoint, authenticated with `INGEST_TOKEN`. The backend then:

- creates an `accounts` row for each account number it hasn't seen and updates its balance
- stores new transactions and skips ones it already has. A transaction's identity is a hash of
  its date, amount, description, memo, reference number and installment number, so the
  overlapping days re-scraped each night are not duplicated
- skips pending charges, which can still change, and stores them once they settle
- writes a `scrape_runs` row for every login, including failures and the error

Bank logins never leave the scraper container, and the scraper has no route to the database.

### Run a scrape now

```sh
docker compose run --rm scraper npm run scrape-once              # scrape and store
docker compose run --rm scraper npm run scrape-once -- --dry-run # save raw JSON to scraper/output/ only
docker compose logs scraper                                      # nightly run output
```

Use `--dry-run` for a first look at what a bank returns. If your bank texts a one-time code on
every login, scrapes of that account will fail until OTP support lands.

`.env`, `scraper/config/accounts.json` and `scraper/output/` hold your credentials and real
transactions. All three are gitignored; keep them that way.

## Categories, rules and budgets

The API lives under `/api`. Interactive docs are at http://localhost:8000/docs.

**Categories** have two levels (Food › Groceries) and a kind: `expense`, `income` or
`transfer`. A starter set is created on first start; rename, add or delete freely. Mark
money moving between your own accounts as a **transfer**, most importantly the monthly card bill
paid from your bank account. Otherwise every card purchase counts twice: once on the card
and again inside the bill.

**Rules** file transactions into categories as they arrive. A plain pattern matches anywhere
in the description or memo, ignoring case and extra spaces; set `is_regex` for a regular
expression. When several rules match, the higher `priority` wins, then the longer pattern
(so `PAYPAL *SPOTIFY` beats `PAYPAL`), then the older rule. Adding, changing or deleting a rule
re-runs all rules over existing transactions, except ones you categorized by hand.

```sh
curl localhost:8000/api/categories    # ids used below

# Everything from Shufersal is groceries
curl -X POST localhost:8000/api/rules -H 'content-type: application/json' \
  -d '{"match_pattern": "שופרסל", "category_id": 2}'

# What still needs a category this month?
curl 'localhost:8000/api/transactions?month=2026-09&uncategorized=true'

# Categorize one by hand, and remember it for this description from now on
curl -X PATCH localhost:8000/api/transactions/42 -H 'content-type: application/json' \
  -d '{"category_id": 7, "create_rule": true}'
```

A hand-picked category is never overwritten by rules. Send `"category_id": null` to hand the
transaction back to the rules.

**Budgets** are set per expense category per month. A budget on a parent (Food) covers its
subcategories.

```sh
curl -X PUT localhost:8000/api/budgets/2026-09/1 -H 'content-type: application/json' \
  -d '{"limit_amount": 2000}'
curl localhost:8000/api/budgets/summary               # current month to date
curl 'localhost:8000/api/budgets/summary?month=2026-08'
```

The summary gives spent, remaining and percent used for each budget, spending in categories
without a budget, and the count and total of uncategorized transactions. Spending is net:
refunds reduce it. Income and transfers never count as spending.

The API has no login yet. Only the machine itself (`127.0.0.1`) and SmartFin's own containers
can reach it, until the dashboard phase adds authentication and opens it to the LAN.

## Development

Backend (tests use in-memory SQLite by default; set `DATABASE_URL` to run them on Postgres):

```sh
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
pytest
```

After changing `app/models.py`, generate a migration against a running database:

```sh
alembic revision --autogenerate -m "describe the change"
alembic upgrade head
```

Scraper:

```sh
cd scraper
npm install
npm test
```

On a Raspberry Pi or other arm64 machine, run the scraper outside Docker with a system Chromium:
install `chromium` from apt and set `PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium`.
