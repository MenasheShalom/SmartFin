// Runs syncs one at a time (one Chromium at a time), for the nightly run and for "sync now" or a
// newly added login from the web app, and remembers how each login's last sync went.
import { runAll } from './runner.js';

export class SyncQueue {
  constructor({ store, settings, run = runAll, log = console }) {
    this.store = store;
    this.settings = settings;
    this.run = run;
    this.log = log;
    this.waiting = []; // [{ id, firstSync }]
    this.current = null;
    this.results = new Map(); // id -> { ok, error_type, finished_at }
    this.draining = false;
    this.idle = Promise.resolve();
  }

  /** Queue logins by id and return at once; ones already waiting keep their place */
  enqueue(ids, { firstSync = false } = {}) {
    for (const id of ids) {
      const waiting = this.waiting.find((w) => w.id === id);
      if (waiting) waiting.firstSync ||= firstSync;
      else this.waiting.push({ id, firstSync });
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
  }

  async #drain() {
    this.draining = true;
    try {
      while (this.waiting.length > 0) {
        const { id, firstSync } = this.waiting.shift();
        let account;
        try {
          account = (await this.store.list()).find((a) => a.id === id);
        } catch (err) {
          this.log.error(`Cannot read the logins: ${err.message}`);
          continue;
        }
        if (!account) continue; // removed while it waited
        this.current = id;
        const settings = firstSync ? { ...this.settings, daysBack: this.settings.firstDaysBack } : this.settings;
        try {
          await this.run([account], settings, {
            log: this.log,
            onResult: (_, payload) =>
              this.results.set(id, {
                ok: payload.success,
                error_type: payload.success ? null : payload.error_type,
                finished_at: payload.finished_at,
              }),
          });
        } catch (err) {
          this.log.error(`[${account.company}] sync failed: ${err.message}`);
          this.results.set(id, { ok: false, error_type: 'GENERIC', finished_at: new Date().toISOString() });
        } finally {
          this.current = null;
        }
      }
    } finally {
      this.draining = false;
    }
  }
}
