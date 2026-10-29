// Scrape every account once now. With --dry-run, save the raw results to the output
// directory and send nothing to the backend. With --full-history, go back as far as a newly
// added login does (SCRAPER_FIRST_MONTHS_BACK), to fill in older history.
import { loadSettings } from './config.js';
import { runAll } from './runner.js';
import { AccountStore } from './store.js';

const dryRun = process.argv.includes('--dry-run');
const fullHistory = process.argv.includes('--full-history');

try {
  const settings = loadSettings(process.env, { requireIngest: !dryRun });
  const store = new AccountStore({
    file: settings.accountsFile,
    key: process.env.SCRAPER_ACCOUNTS_KEY,
    keyFile: settings.keyFile,
  });
  const accounts = await store.list();
  if (accounts.length === 0) throw new Error('No bank or card logins yet: add them in the web app');
  const runSettings = fullHistory ? { ...settings, monthsBack: settings.firstMonthsBack } : settings;
  const ok = await runAll(accounts, runSettings, { dryRun });
  process.exitCode = ok ? 0 : 1;
} catch (err) {
  console.error(err.message);
  process.exitCode = 1;
}
