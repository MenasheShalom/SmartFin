import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { createScraper } from 'israeli-bank-scrapers-core';

import { maskAccountNumber } from './config.js';

export function defaultScrape(account, settings, startDate) {
  const scraper = createScraper({
    companyId: account.company,
    startDate,
    combineInstallments: false,
    executablePath: settings.executablePath,
    // Needed when Chromium runs as root inside a container
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  return scraper.scrape(account.credentials);
}

export async function postIngest(settings, payload) {
  const response = await fetch(new URL('/internal/ingest', settings.backendUrl), {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${settings.ingestToken}`,
    },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`ingest returned ${response.status}: ${await response.text()}`);
  }
  return response.json();
}

async function saveRaw(settings, company, result) {
  await mkdir(settings.outputDir, { recursive: true });
  const stamp = new Date().toISOString().replace(/[:.]/g, '-');
  const file = path.join(settings.outputDir, `${company}-${stamp}.json`);
  await writeFile(file, JSON.stringify(result, null, 2));
  return file;
}

// Build the backend's ingest payload; rawTransaction is bank-specific noise, so it stays behind.
export function toPayload(company, startedAt, finishedAt, result) {
  return {
    institution: company,
    started_at: startedAt.toISOString(),
    finished_at: finishedAt.toISOString(),
    success: Boolean(result.success),
    error_type: result.errorType ?? null,
    error_message: result.errorMessage ?? null,
    accounts: (result.accounts ?? []).map(({ txns = [], ...account }) => ({
      ...account,
      txns: txns.map(({ rawTransaction, ...txn }) => txn),
    })),
  };
}

// Scrape every account in turn (one Chromium at a time); one failure never stops the rest.
// Returns true when every account scraped and ingested cleanly.
export async function runAll(accounts, settings, {
  scrape = defaultScrape,
  ingest = postIngest,
  dryRun = false,
  log = console,
  now = () => new Date(),
} = {}) {
  const startDate = now();
  startDate.setDate(startDate.getDate() - settings.daysBack);
  let allOk = true;

  for (const account of accounts) {
    const startedAt = now();
    log.log(`[${account.company}] scraping since ${startDate.toISOString().slice(0, 10)}`);

    let result;
    try {
      result = await scrape(account, settings, startDate);
    } catch (err) {
      result = { success: false, errorType: 'EXCEPTION', errorMessage: err.message };
    }
    const payload = toPayload(account.company, startedAt, now(), result);

    if (payload.success) {
      for (const a of payload.accounts) {
        log.log(`[${account.company}] account ${maskAccountNumber(a.accountNumber)}: ${a.txns.length} transactions`);
      }
    } else {
      allOk = false;
      log.error(`[${account.company}] scrape failed: ${payload.error_type}${payload.error_message ? ` — ${payload.error_message}` : ''}`);
    }

    if (settings.saveRaw || dryRun) {
      log.log(`[${account.company}] raw result saved to ${await saveRaw(settings, account.company, result)}`);
    }
    if (dryRun) continue;

    try {
      const summary = await ingest(settings, payload);
      if (payload.success) {
        log.log(`[${account.company}] stored ${summary.added} new, ${summary.duplicates} already known, ${summary.pending_skipped} pending skipped`);
      }
    } catch (err) {
      allOk = false;
      log.error(`[${account.company}] could not send results to the backend: ${err.message}`);
    }
  }
  return allOk;
}
