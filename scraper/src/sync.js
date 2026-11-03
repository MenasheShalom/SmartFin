// Runs syncs one at a time (one Chromium at a time), for the nightly run and for "sync now" or a
// newly added login from the web app, and remembers how each login's last sync went.
import { isRetryable } from './retry.js';
import { runAll } from './runner.js';

const sleepFor = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

export class SyncQueue {
  constructor({ store, settings, run = runAll, log = console }) {
    this.store = store;
    this.settings = settings;
    this.run = run;
    this.log = log;
    this.waiting = []; // [{ id, firstSync, holdRetryable }]
    this.current = null;
    this.results = new Map(); // id -> { ok, error_type, finished_at }
    // Logins whose last run had a card failure worth another attempt
    this.needsRetry = new Set();
    // id -> { attempt, of, at } while the nightly run waits to try a login again
    this.retries = new Map();
    this.draining = false;
    this.idle = Promise.resolve();
  }

  /**
   * Queue logins by id and return at once; ones already waiting keep their place.
   * holdRetryable: don't report a card failure that will be retried (the nightly run's attempts
   * before its last); a sync someone asked for always reports.
   */
  enqueue(ids, { firstSync = false, holdRetryable = false } = {}) {
    for (const id of ids) {
      const waiting = this.waiting.find((w) => w.id === id);
      if (waiting) {
        waiting.firstSync ||= firstSync;
        waiting.holdRetryable &&= holdRetryable;
      } else this.waiting.push({ id, firstSync, holdRetryable });
    }
    // `idle` settles once everything queued has run
    if (!this.draining) this.idle = this.#drain();
  }

  async enqueueAll() {
    const accounts = await this.store.list();
    this.enqueue(accounts.map((a) => a.id));
  }

  /** "running", "queued" or null */
  state(id) {
    if (this.current === id) return 'running';
    return this.waiting.some((w) => w.id === id) ? 'queued' : null;
  }

  forget(id) {
    this.waiting = this.waiting.filter((w) => w.id !== id);
    this.results.delete(id);
    this.retries.delete(id);
  }

  /**
   * The nightly run: every login once, then the card logins that failed with a passing error
   * again, up to `retries` more times, `delayMs` apart. A failure is reported (scrape log and
   * alert) only when it is the last attempt.
   */
  async runNightly({
    retries = this.settings.retries ?? 0,
    delayMs = (this.settings.retryMinutes ?? 10) * 60_000,
    sleep = sleepFor,
    now = () => Date.now(),
  } = {}) {
    let ids = (await this.store.list()).map((a) => a.id);
    for (let attempt = 0; ids.length > 0; attempt++) {
      const last = attempt >= retries;
      this.enqueue(ids, { holdRetryable: !last });
      await this.idle;
      for (const id of ids) this.retries.delete(id);
      if (last) break;
      ids = ids.filter((id) => this.needsRetry.has(id));
      if (ids.length === 0) break;
      const at = new Date(now() + delayMs).toISOString();
      for (const id of ids) this.retries.set(id, { attempt: attempt + 1, of: retries, at });
      this.log.log(
        `${ids.length} card login(s) failed; retry ${attempt + 1} of ${retries} in ${Math.round(delayMs / 60_000)} minutes`,
      );
      await sleep(delayMs);
      // A sync someone ran meanwhile may have fixed it
      ids = ids.filter((id) => this.needsRetry.has(id));
    }
  }

  async #drain() {
    this.draining = true;
    try {
      while (this.waiting.length > 0) {
        const { id, firstSync, holdRetryable } = this.waiting.shift();
        let account;
        try {
          account = (await this.store.list()).find((a) => a.id === id);
        } catch (err) {
          this.log.error(`Cannot read the logins: ${err.message}`);
          continue;
        }
        if (!account) continue; // removed while it waited
        this.current = id;
        this.retries.delete(id);
        this.needsRetry.delete(id);
        const settings = firstSync ? { ...this.settings, monthsBack: this.settings.firstMonthsBack } : this.settings;
        try {
          await this.run([account], settings, {
            log: this.log,
            onResult: (_, payload) =>
              this.results.set(id, {
                ok: payload.success,
                error_type: payload.success ? null : payload.error_type,
                finished_at: payload.finished_at,
              }),
            onPart: (_, company, payload) => {
              if (isRetryable(company, payload)) this.needsRetry.add(id);
            },
            withhold: (company, payload) => holdRetryable && isRetryable(company, payload),
          });
        } catch (err) {
          this.log.error(`[${account.company}] sync failed: ${err.message}`);
          this.results.set(id, { ok: false, error_type: 'GENERIC', finished_at: new Date().toISOString() });
          if (isRetryable(account.company, { success: false, error_type: 'GENERIC' })) this.needsRetry.add(id);
        } finally {
          this.current = null;
        }
      }
    } finally {
      this.draining = false;
    }
  }
}
