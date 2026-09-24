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
- [ ] Phase 3: Categorization and budgets
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
