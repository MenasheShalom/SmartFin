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
- [ ] Phase 2: Nightly sync into Postgres, de-duplication, scrape logging
- [ ] Phase 3: Categorization and budgets
- [ ] Phase 4: Alerts (Telegram / email)
- [ ] Phase 5: Dashboard
- [ ] Phase 6: Hardening (backups, credential encryption, failure alerts)

## Running it

```sh
cp .env.example .env          # set POSTGRES_PASSWORD and your scraper account
docker compose up -d --build  # Postgres + backend; migrations run on start
curl localhost:8000/health    # {"status":"ok","database":"ok"}
```

### Scrape one account (Phase 1)

```sh
docker compose run --rm scraper
```

This logs in with `SCRAPER_COMPANY` and `SCRAPER_CREDENTIALS` from `.env`, fetches the last
`SCRAPER_DAYS_BACK` days and saves the raw result to `scraper/output/`. Nothing goes into the
database yet. If your bank texts a one-time code on every login, this run will fail until
OTP support lands in a later phase.

`.env` and `scraper/output/` hold your credentials and real transactions. Both are gitignored;
keep them that way.

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
