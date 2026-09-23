// Phase 1: scrape one account once and save the raw result for inspection.
// Nothing is written to the database yet; that comes in Phase 2.
import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { createScraper } from 'israeli-bank-scrapers-core';

import { loadConfig, maskAccountNumber } from './config.js';

async function main() {
  const config = loadConfig();
  const startDate = new Date();
  startDate.setDate(startDate.getDate() - config.daysBack);

  console.log(`Scraping ${config.company} since ${startDate.toISOString().slice(0, 10)}…`);
  const scraper = createScraper({
    companyId: config.company,
    startDate,
    combineInstallments: false,
    executablePath: config.executablePath,
    // Needed when Chromium runs as root inside a container
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });

  const result = await scraper.scrape(config.credentials);
  if (!result.success) {
    console.error(`Scrape failed: ${result.errorType}${result.errorMessage ? ` — ${result.errorMessage}` : ''}`);
    process.exitCode = 1;
    return;
  }

  for (const account of result.accounts ?? []) {
    console.log(`  account ${maskAccountNumber(account.accountNumber)}: ${account.txns.length} transactions`);
  }

  await mkdir(config.outputDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const file = path.join(config.outputDir, `${config.company}-${stamp}.json`);
  await writeFile(file, JSON.stringify(result, null, 2));
  console.log(`Raw result saved to ${file}`);
}

main().catch((err) => {
  console.error(err.message);
  process.exitCode = 1;
});
