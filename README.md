# SmartFin

A self-hosted cash-flow app for Israeli bank and credit-card accounts, in Hebrew. Every night it
pulls in your transactions, files them into categories, and shows you where the month stands:
how much is left for this week, what the end of the month looks like, and how the past months
went. It runs on a home server or Raspberry Pi with Docker Compose, and your bank logins never
leave that machine.

Design doc: [SmartFin — Architecture & Build Strategy](https://claude.ai/artifact/5jAc5LqeFBF5DHjeyVLBMy) ·
Screens: [design canvas](https://claude.ai/artifact/2dtCTS8E84pz3M2MhyQhAg)

## What it does

- **תזרים (cash flow):** the forecast for the end of the month, what is left to spend this week,
  and the month's income, fixed bills and day-to-day spending.
- **שבועי (weekly):** day-to-day spending week by week (Sunday to Saturday) against a weekly
  allowance.
- **היסטוריה (history):** income, expenses and end-of-month bank balance for every month, with a
  chart you can page or swipe through.
- **תנועות (transactions):** a queue of transactions waiting for a category, one tap each, with
  "remember for next time"; and a searchable list of everything.
- **תוכנית (plan):** expected income, fixed bills, a savings goal, and what that leaves for
  day-to-day spending.
- Alerts over Telegram or email: budget levels, low balance, large charges, failed or stalled
  syncs.
- Works on a phone (add it to your home screen), a tablet or a computer; follows the system
  light/dark setting.

## Layout

| Path | What it is |
|---|---|
| `backend/` | FastAPI API, SQLAlchemy models, Alembic migrations; serves the web app |
| `frontend/` | The web app: React, TypeScript, Vite |
| `scraper/` | Node.js service using [israeli-bank-scrapers](https://github.com/eshaham/israeli-bank-scrapers) |
| `ops/` | Backup script |
| `docker-compose.yml` | Postgres, backend, scraper and backups on separate Docker networks |

## Status

- [x] **Phase 1: Foundation.** Compose skeleton, data model and migrations, one-shot manual scrape
- [x] **Phase 2: Sync.** Nightly scrape of every account into Postgres, de-duplication, scrape logging
- [x] **Phase 3: Categorization and budgets.** Rules, manual overrides, monthly budgets, spend-vs-budget
- [x] **Phase 4: Alerts.** Budget, low balance, large charge and failed sync alerts over Telegram / email
- [x] **Phase 5: The app.** Login, cash-flow plan, weekly view, history, categorizing, settings
- [x] **Phase 6: Hardening.** Backups, encrypted bank logins, stalled-sync alerts, non-root image
- [x] **Phase 7: Set up from the app.** Username and password, and bank and card logins, managed in the web app

## Setting it up

You need Docker with Docker Compose on the machine that will run SmartFin.

1. **Configuration.**

   ```sh
   cp .env.example .env
   ```

   In `.env`, set `POSTGRES_PASSWORD` and `INGEST_TOKEN` (for each: `openssl rand -hex 32`).

2. **Build and start.**

   ```sh
   docker compose build
   docker compose up -d
   ```

3. **Create your login.** Open `http://<server address>:8000`. The first time, it asks you to
   choose a username and password; do this right away, since until then anyone who can reach the
   page could claim it. You can change both later under הגדרות.

4. **Connect your banks and credit cards.** In הגדרות › חשבונות וסנכרון, tap
   "הוספת בנק או כרטיס אשראי", pick the bank or card company and enter the details you use on its
   website. SmartFin logs in right away and fetches the last year, which can take a few minutes;
   the list shows how it went. After that, every login syncs nightly at `SCRAPE_TIME` (03:00 by
   default), and "סנכרון עכשיו" syncs on demand.

5. **Sort the first transactions.** Open תנועות: each transaction waits for a category. With
   "remember for next time" ticked, the next ones from the same place are filed automatically.
   Most important: mark the monthly credit-card bill paid from your bank account as
   **העברות בין חשבונות**, or every card purchase counts twice.

6. **Check the plan.** In תוכנית, see that the fixed bills (rent, insurance, subscriptions) look
   right and set a savings goal. Expected income is the average of the last three months unless
   you set it.

### Bank and card logins

Logins are added, updated and removed in the app (הגדרות › חשבונות וסנכרון). Where they go:

- The app sends them to the backend, which passes them straight on to the scraper's small API
  and keeps nothing. That API listens only on the internal Docker network the backend and scraper
  share, has no published port, and needs `INGEST_TOKEN`.
- The scraper saves them in `scraper/config/accounts.json.enc`, encrypted with AES-256-GCM. They
  are never in the database or the backups, and the app never gets them back: it shows the bank
  and the end of the ID or username (`•••789`), and updating a login means entering it again.
- The key is `SCRAPER_ACCOUNTS_KEY` if you set it in `.env`; otherwise the scraper generates one
  in its own Docker volume (`scraper-keys`), apart from the config folder. The encryption
  protects the file if it is copied or backed up somewhere. The key is on the same machine, so it
  does not protect against someone with access to the server itself. If the key is lost, delete
  `accounts.json.enc` and add the logins again.

What each company asks for:

| Company | Credentials |
|---|---|
| `leumi`, `mizrahi`, `max`, `visaCal`, `otsarHahayal`, `union`, `beinleumi`, `massad`, `pagi` | `username`, `password` |
| `hapoalim` | `userCode`, `password` |
| `discount`, `mercantile` | `id`, `password`, `num` |
| `isracard`, `amex` | `id`, `card6Digits`, `password` |
| `yahav` | `username`, `nationalID`, `password` |
| `beyahadBishvilha`, `behatsdaa` | `id`, `password` |

Banks that ask for a one-time SMS code on every login (One Zero) are not supported.

You can still write logins by hand in `scraper/config/accounts.json` (a list of
`{"company": ..., "credentials": {...}}`, see `accounts.example.json`): the scraper reads it, and
the first change made in the app folds it into the encrypted file and deletes it.

## Using it on your phone

On the same Wi-Fi, open `http://<server address>:8000`, log in, and add it to the home screen
(Safari: Share → Add to Home Screen; Chrome: menu → Install app). It opens full screen like an
app.

From outside the home, use [Tailscale](https://tailscale.com) rather than opening a port on your
router: install it on the server and the phone, then on the server run
`tailscale serve --bg 8000`. That gives the app an HTTPS address on your tailnet; set
`COOKIE_SECURE=true` in `.env` so the login cookie is only ever sent over HTTPS. To make SmartFin
reachable only through Tailscale, also set `BIND_ADDRESS=127.0.0.1`.

## Backups

The `backup` service writes a gzipped database dump to `./backups` when the stack starts and every
24 hours after, keeping `BACKUP_KEEP_DAYS` (14) days. Copy that folder somewhere else from time
to time: it holds all your financial history. To restore one:

```sh
gunzip -c backups/smartfin-YYYYMMDD-HHMM.sql.gz | docker compose exec -T db psql -U smartfin smartfin
```

## How it works

### Sync

The scraper logs into each account in turn every night at `SCRAPE_TIME` (Israel time) and
fetches the last `SCRAPER_DAYS_BACK` days. A login just added in the app is synced right away,
`SCRAPER_FIRST_DAYS_BACK` (365) days back, and "סנכרון עכשיו" queues every login; syncs run one
at a time. It sends the results to the backend's
`/internal/ingest` endpoint, authenticated with `INGEST_TOKEN`. The backend then:

- creates an `accounts` row for each account number it hasn't seen, updates its balance, and
  keeps one balance snapshot per day for the history
- stores new transactions and skips ones it already has. A transaction's identity is a hash of
  its date, amount, description, memo, reference number and installment number, so the
  overlapping days re-scraped each night are not duplicated
- skips pending charges, which can still change, and stores them once they settle
- files each new transaction by the categorization rules
- writes a `scrape_runs` row for every login, including failures and the error, then checks for
  alerts

Bank logins are stored only by the scraper, encrypted. The backend passes them through when you
add one in the app and never stores them, and the scraper has no route to the database.

```sh
docker compose run --rm scraper npm run scrape-once              # scrape and store now
docker compose run --rm scraper npm run scrape-once -- --dry-run # save raw JSON to scraper/output/ only
docker compose logs scraper                                      # nightly run output
```

`.env`, `scraper/config/` (`accounts.json.enc`, and `accounts.json` if you wrote one) and
`scraper/output/` hold your credentials and real transactions. All are gitignored; keep them that
way.

### The cash-flow plan

For each month:

- **Expected income** is what you set in תוכנית, or else the average of the last three months'
  income (never less than what already arrived).
- **Fixed bills** are the categories marked fixed (rent, insurance, subscriptions, ...). Each is
  expected at its budget for the month, or else at last month's amount, and shows as paid,
  partly paid or still expected.
- **Day-to-day spending** gets what is left: expected income, minus fixed bills, minus the
  savings goal. It is split into Sunday-to-Saturday weeks by their number of days.
- **The end-of-month forecast** projects day-to-day spending from the pace so far, blended with
  the plan early in the month (the pace counts more as the month goes on).

Income and transfers never count as spending. Uncategorized transactions are left out of the
plan, and the app says how much is waiting to be sorted.

### History

Income and expenses per month come from categorized transactions, and from ones not sorted yet by
their direction: money out of any account is an expense, money into a card is a refund (it
reduces expenses), and money into a bank account is income. A card bill paid from the bank counts
twice until it is filed as a transfer. The end-of-month balance is the
total of your bank accounts: the balance snapshot from that month where there is one, otherwise
worked back from today's balance through the transactions since. Months before an account's data
starts show no balance rather than a wrong one.

### Security

- One login: a username and password, created in the web app on first start and stored in the
  database as a scrypt hash. Changing the password under הגדרות logs out every other device. If
  you forget it, reset it on the server with `docker compose exec backend python -m app.password`.
  Sessions are random tokens in an
  HttpOnly, SameSite=Strict cookie, stored hashed, valid 30 days; logging out ends them. After 5
  wrong passwords, each further try waits longer (up to 15 minutes).
- Changes need an `X-Requested-With` header, which other sites cannot send.
- The web app is served with a strict Content-Security-Policy and no third-party requests: the
  font is bundled.
- The backend runs as a non-root user; the database has no route to the internet.

## Alerts

After every sync the backend checks for:

| Alert | When | How often |
|---|---|---|
| Budget | a budget reaches each level in `BUDGET_ALERT_LEVELS` (default 80% and 100%); not for fixed bills | once per level per budget per month |
| Low balance | a bank account is below `LOW_BALANCE_THRESHOLD` | at most weekly while it stays low |
| Large charge | a new expense is at or above `LARGE_TRANSACTION_THRESHOLD` | once per transaction |
| Failed sync | a bank login or scrape fails | once per bank per day |
| Stalled sync | no sync has finished for 30 hours (checked hourly) | once a day |

Leave a threshold empty to turn that check off. Alerts show in the app (the bell on the home
screen) and are sent over Telegram and/or email when configured in `.env`; a send that fails is
retried after the next sync, for up to three days. Settings → Alerts, or
`POST /api/alerts/test`, checks the setup.

## API

The API lives under `/api`. Interactive docs are at `/docs`.

### Categories, rules and budgets

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

Every `/api` call needs the login session cookie (and, for changes, an `X-Requested-With:
smartfin` header). The curl examples assume you have logged in with `-c`/`-b` cookie files;
they are here to document the API rather than as the way to use SmartFin.

### Alerts API

```sh
curl -X POST localhost:8000/api/alerts/test    # {"channels":["telegram"],"delivered":true}
curl localhost:8000/api/alerts?unacknowledged=true
curl -X POST localhost:8000/api/alerts/3/acknowledge
```

### Cash flow, history and accounts

```sh
curl localhost:8000/api/cashflow?month=2026-09     # the plan and where it stands
curl -X PUT localhost:8000/api/plans/2026-09 -H 'content-type: application/json' \
  -d '{"expected_income": 15000, "savings_goal": 1000}'
curl localhost:8000/api/history                    # every month: income, expenses, balance
curl localhost:8000/api/accounts                   # balances, masked account numbers
curl localhost:8000/api/sync-status                # the latest sync per bank
```

### Bank logins and your own login

```sh
curl localhost:8000/api/connections              # connected banks and cards, and the companies on offer
curl -X POST localhost:8000/api/connections -H 'content-type: application/json' \
  -d '{"company": "leumi", "credentials": {"username": "...", "password": "..."}}'
curl -X PUT localhost:8000/api/connections/<id> ...  # replace a login's credentials
curl -X DELETE localhost:8000/api/connections/<id>
curl -X POST localhost:8000/api/connections/sync     # sync every login now

curl localhost:8000/api/auth/status              # {"setup_required": true} until the first sign-up
curl -X PUT localhost:8000/api/auth/account -H 'content-type: application/json' \
  -d '{"current_password": "...", "username": "me", "new_password": "..."}'
```

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

Web app, with the backend running on port 8000 (Vite forwards `/api` to it):

```sh
cd frontend
npm install
npm run dev        # http://localhost:5173
npm test           # unit and component tests
npm run typecheck
```

Sample data, for trying the app or taking screenshots. Only on an empty database: it refuses to
run if there are transactions already.

```sh
docker compose run --rm backend python -m app.demo --yes
```

### End-to-end tests

The Playwright tests log in and click through every screen on a phone-sized browser, check that
nothing scrolls sideways, and run an accessibility scan (axe). They change data, so run them
against a fresh database with the sample data, never your real one. On a database with no login
yet, the first test creates it through the sign-up screen with `E2E_USERNAME` and `E2E_PASSWORD`:

```sh
cd frontend
npx playwright install chromium
E2E_BASE_URL=http://localhost:8000 E2E_USERNAME=demo E2E_PASSWORD=demo-pass-123 npm run e2e
```

The test that connects a bank is skipped unless `E2E_CONNECTIONS=1`: adding a login makes the
scraper try it against the real site. Run it only with a scraper that has no internet, e.g. with
a compose override that sets `networks: !override [ingest]` on the `scraper` service. The fake
login then fails at once, which is what the test expects.

Scraper:

```sh
cd scraper
npm install
npm test
```

On a Raspberry Pi or other arm64 machine, run the scraper outside Docker with a system Chromium:
install `chromium` from apt and set `PUPPETEER_EXECUTABLE_PATH=/usr/bin/chromium`.
