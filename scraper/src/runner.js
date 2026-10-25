import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { createScraper } from 'israeli-bank-scrapers-core';

import { maskAccountNumber } from './config.js';
import { CARDS_COMPANY, LeumiWithCardsScraper } from './leumi-cards.js';

export function defaultScrape(account, settings, startDate) {
  const options = {
    companyId: account.company,
    startDate,
    combineInstallments: false,
    executablePath: settings.executablePath,
    // Needed when Chromium runs as root inside a container
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  };
  const scraper = account.company === 'leumi' ? new LeumiWithCardsScraper(options) : createScraper(options);
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
  onStart = () => {},
  onResult = () => {},
} = {}) {
  const startDate = now();
  startDate.setDate(startDate.getDate() - settings.daysBack);
  let allOk = true;

  // Log, save and ingest one company's result; true when it scraped and ingested cleanly
  async function report(company, result, payload) {
    let ok = true;
    if (payload.success) {
      for (const a of payload.accounts) {
        log.log(`[${company}] account ${maskAccountNumber(a.accountNumber)}: ${a.txns.length} transactions`);
      }
    } else {
      ok = false;
      log.error(`[${company}] scrape failed: ${payload.error_type}${payload.error_message ? ` — ${payload.error_message}` : ''}`);
    }

    if (settings.saveRaw || dryRun) {
      log.log(`[${company}] raw result saved to ${await saveRaw(settings, company, result)}`);
    }
    if (dryRun) return ok;

    try {
      const summary = await ingest(settings, payload);
      if (payload.success) {
        log.log(`[${company}] stored ${summary.added} new, ${summary.duplicates} already known, ${summary.pending_skipped} pending skipped`);
      }
    } catch (err) {
      ok = false;
      log.error(`[${company}] could not send results to the backend: ${err.message}`);
    }
    return ok;
  }

  for (const account of accounts) {
    onStart(account);
    const startedAt = now();
    log.log(`[${account.company}] scraping since ${startDate.toISOString().slice(0, 10)}`);

    let result;
    try {
      result = await scrape(account, settings, startDate);
    } catch (err) {
      result = { success: false, errorType: 'EXCEPTION', errorMessage: err.message };
    }
    const finishedAt = now();
    // A Leumi login also brings its credit cards, stored as their own institution
    const parts = [[account.company, result]];
    if (result.cards) parts.push([CARDS_COMPANY, result.cards]);

    for (const [company, part] of parts) {
      const payload = toPayload(company, startedAt, finishedAt, part);
      if (!(await report(company, part, payload))) allOk = false;
      // The login's status follows its own result; a card failure is reported on its own run
      if (company === account.company) onResult(account, payload);
    }
  }
  return allOk;
}
