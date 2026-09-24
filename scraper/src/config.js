import { readFile } from 'node:fs/promises';

import { SCRAPERS } from 'israeli-bank-scrapers-core';

import { decrypt } from './crypto.js';

// Companies whose login needs an interactive OTP flow; handled in a later phase.
const UNSUPPORTED = new Set(['oneZero']);

export function validateAccount(entry, index = 0) {
  const where = `accounts[${index}]`;
  if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) {
    throw new Error(`${where} must be an object with "company" and "credentials"`);
  }
  const { company, credentials } = entry;
  if (!company || !SCRAPERS[company] || UNSUPPORTED.has(company)) {
    const supported = Object.keys(SCRAPERS).filter((c) => !UNSUPPORTED.has(c));
    throw new Error(`${where}.company must be one of: ${supported.join(', ')}`);
  }
  if (typeof credentials !== 'object' || credentials === null || Array.isArray(credentials)) {
    throw new Error(`${where}.credentials must be an object`);
  }
  const missing = SCRAPERS[company].loginFields.filter((field) => !credentials[field]);
  if (missing.length > 0) {
    throw new Error(`${where} (${company}) is missing credentials: ${missing.join(', ')}`);
  }
  return { company, credentials };
}

export function parseAccounts(text) {
  let entries;
  try {
    entries = JSON.parse(text);
  } catch {
    throw new Error('Accounts file is not valid JSON');
  }
  if (!Array.isArray(entries) || entries.length === 0) {
    throw new Error('Accounts file must be a non-empty JSON array');
  }
  return entries.map(validateAccount);
}

// The encrypted file wins when both exist
export async function loadAccounts(file, key = process.env.SCRAPER_ACCOUNTS_KEY) {
  let sealed = null;
  try {
    sealed = await readFile(`${file}.enc`, 'utf8');
  } catch {
    // no encrypted file
  }
  if (sealed !== null) {
    if (!key) throw new Error(`${file}.enc exists but SCRAPER_ACCOUNTS_KEY is not set`);
    return parseAccounts(decrypt(sealed, key));
  }
  let text;
  try {
    text = await readFile(file, 'utf8');
  } catch {
    throw new Error(`Cannot read accounts file ${file}; copy accounts.example.json there`);
  }
  return parseAccounts(text);
}

export function loadSettings(env = process.env, { requireIngest = true } = {}) {
  const daysBack = Number(env.SCRAPER_DAYS_BACK ?? 30);
  if (!Number.isInteger(daysBack) || daysBack < 1) {
    throw new Error('SCRAPER_DAYS_BACK must be a positive integer');
  }

  const scrapeTime = env.SCRAPE_TIME ?? '03:00';
  if (!/^([01]\d|2[0-3]):[0-5]\d$/.test(scrapeTime)) {
    throw new Error('SCRAPE_TIME must be HH:MM (24-hour)');
  }

  const backendUrl = env.BACKEND_URL;
  const ingestToken = env.INGEST_TOKEN;
  if (requireIngest && (!backendUrl || !ingestToken)) {
    throw new Error('BACKEND_URL and INGEST_TOKEN must be set');
  }

  return {
    accountsFile: env.SCRAPER_ACCOUNTS_FILE || 'config/accounts.json',
    backendUrl,
    ingestToken,
    daysBack,
    scrapeTime,
    executablePath: env.PUPPETEER_EXECUTABLE_PATH || undefined,
    saveRaw: env.SCRAPER_SAVE_RAW === 'true',
    outputDir: env.SCRAPER_OUTPUT_DIR || 'output',
  };
}

// Show only the last 4 digits of an account number in logs.
export function maskAccountNumber(accountNumber) {
  const s = String(accountNumber ?? '');
  return s.length <= 4 ? s : `…${s.slice(-4)}`;
}
