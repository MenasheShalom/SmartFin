// Long-running scraper service: scrape every account nightly at SCRAPE_TIME.
import { loadAccounts, loadSettings } from './config.js';
import { runAll } from './runner.js';
import { msUntilNext } from './schedule.js';

const settings = loadSettings();
// Fail at startup, not at 3am, if the accounts file is missing or wrong.
await loadAccounts(settings.accountsFile);

function scheduleNext() {
  const delay = msUntilNext(settings.scrapeTime);
  console.log(`Next scrape at ${new Date(Date.now() + delay).toString()}`);
  setTimeout(async () => {
    try {
      // Re-read each night so edits to the accounts file apply without a restart.
      await runAll(await loadAccounts(settings.accountsFile), settings);
    } catch (err) {
      console.error(`Nightly scrape failed: ${err.message}`);
    }
    scheduleNext();
  }, delay);
}

scheduleNext();
