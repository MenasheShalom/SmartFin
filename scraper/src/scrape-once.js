// Scrape every account once now. With --dry-run, save the raw results to the output
// directory and send nothing to the backend.
import { loadAccounts, loadSettings } from './config.js';
import { runAll } from './runner.js';

const dryRun = process.argv.includes('--dry-run');

try {
  const settings = loadSettings(process.env, { requireIngest: !dryRun });
  const accounts = await loadAccounts(settings.accountsFile);
  const ok = await runAll(accounts, settings, { dryRun });
  process.exitCode = ok ? 0 : 1;
} catch (err) {
  console.error(err.message);
  process.exitCode = 1;
}
