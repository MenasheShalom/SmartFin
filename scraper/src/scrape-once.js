// Scrape every account once now. With --dry-run, save the raw results to the output
// directory and send nothing to the backend.
import { loadSettings } from './config.js';
import { runAll } from './runner.js';
import { AccountStore } from './store.js';

const dryRun = process.argv.includes('--dry-run');

try {
  const settings = loadSettings(process.env, { requireIngest: !dryRun });
  const store = new AccountStore({
    file: settings.accountsFile,
    key: process.env.SCRAPER_ACCOUNTS_KEY,
    keyFile: settings.keyFile,
  });
  const accounts = await store.list();
  if (accounts.length === 0) throw new Error('No bank or card logins yet: add them in the web app');
  const ok = await runAll(accounts, settings, { dryRun });
  process.exitCode = ok ? 0 : 1;
} catch (err) {
  console.error(err.message);
  process.exitCode = 1;
}
