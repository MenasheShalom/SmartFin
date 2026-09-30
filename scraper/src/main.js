// Long-running scraper service: scrape every login nightly at SCRAPE_TIME, and serve the small
// API the web app uses to add logins and sync on demand.
import { createApi } from './api.js';
import { loadSettings } from './config.js';
import { msUntilNext } from './schedule.js';
import { AccountStore } from './store.js';
import { SyncQueue } from './sync.js';

const settings = loadSettings();
const store = new AccountStore({
  file: settings.accountsFile,
  key: process.env.SCRAPER_ACCOUNTS_KEY,
  keyFile: settings.keyFile,
});
// Fail at startup, not at 3am, if the logins file can't be read or decrypted.
const accounts = await store.list();
console.log(accounts.length ? `${accounts.length} bank and card logins` : 'No bank or card logins yet: add them in the web app');

const queue = new SyncQueue({ store, settings });

createApi({ store, queue, token: settings.ingestToken }).listen(settings.apiPort, () => {
  console.log(`Listening for the backend on port ${settings.apiPort}`);
});

function scheduleNext() {
  const delay = msUntilNext(settings.scrapeTime);
  console.log(`Next scrape at ${new Date(Date.now() + delay).toString()}`);
  setTimeout(async () => {
    try {
      await queue.enqueueAll();
      await queue.idle;
    } catch (err) {
      console.error(`Nightly scrape failed: ${err.message}`);
    }
    scheduleNext();
  }, delay);
}

scheduleNext();
