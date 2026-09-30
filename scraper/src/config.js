import { readFile } from 'node:fs/promises';

import { SCRAPERS } from 'israeli-bank-scrapers-core';

import { decrypt } from './crypto.js';

// Companies whose login needs an interactive OTP flow; handled in a later phase.
const UNSUPPORTED = new Set(['oneZero']);

export const SUPPORTED_COMPANIES = Object.keys(SCRAPERS).filter((c) => !UNSUPPORTED.has(c));

export function loginFields(company) {
  return SCRAPERS[company].loginFields;
}

export function validateAccount(entry, index = 0) {
  const where = `accounts[${index}]`;
  if (typeof entry !== 'object' || entry === null || Array.isArray(entry)) {
    throw new Error(`${where} must be an object with "company" and "credentials"`);
  }
  const { id, addedAt, company, credentials } = entry;
  if (!company || !SUPPORTED_COMPANIES.includes(company)) {
    throw new Error(`${where}.company must be one of: ${SUPPORTED_COMPANIES.join(', ')}`);
  }
  if (typeof credentials !== 'object' || credentials === null || Array.isArray(credentials)) {
    throw new Error(`${where}.credentials must be an object`);
  }
  const missing = loginFields(company).filter((field) => typeof credentials[field] !== 'string' || !credentials[field]);
  if (missing.length > 0) {
    throw new Error(`${where} (${company}) is missing credentials: ${missing.join(', ')}`);
  }
  // id and addedAt are set when a login is added from the web app; hand-written files have neither
  return { ...(id ? { id } : {}), ...(addedAt ? { addedAt } : {}), company, credentials };
}

export function parseAccounts(text) {
  let entries;
  try {
    entries = JSON.parse(text);
  } catch {
    throw new Error('Accounts file is not valid JSON');
  }
  if (!Array.isArray(entries)) {
    throw new Error('Accounts file must be a JSON array');
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
    if (!key) {
      throw new Error(
        `${file}.enc exists but SCRAPER_ACCOUNTS_KEY is not set and there is no generated key ` +
          '(was the scraper-keys volume removed?). Set the key, or delete the file and add the logins again.',
      );
    }
    return parseAccounts(decrypt(sealed, key));
  }
  let text;
  try {
    text = await readFile(file, 'utf8');
  } catch (err) {
    // No file yet: logins are added from the web app
    if (err.code === 'ENOENT') return [];
    throw new Error(`Cannot read accounts file ${file}: ${err.message}`);
  }
  return parseAccounts(text);
}

export function loadSettings(env = process.env, { requireIngest = true } = {}) {
  const daysBack = Number(env.SCRAPER_DAYS_BACK ?? 30);
  if (!Number.isInteger(daysBack) || daysBack < 1) {
    throw new Error('SCRAPER_DAYS_BACK must be a positive integer');
  }

  const firstDaysBack = Number(env.SCRAPER_FIRST_DAYS_BACK ?? 365);
  if (!Number.isInteger(firstDaysBack) || firstDaysBack < 1) {
    throw new Error('SCRAPER_FIRST_DAYS_BACK must be a positive integer');
  }
  const apiPort = Number(env.SCRAPER_API_PORT ?? 8080);
  if (!Number.isInteger(apiPort) || apiPort < 1 || apiPort > 65535) {
    throw new Error('SCRAPER_API_PORT must be a port number');
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
    // Where the generated encryption key lives when SCRAPER_ACCOUNTS_KEY is not set
    keyFile: env.SCRAPER_KEY_FILE || 'keys/accounts.key',
    backendUrl,
    // Also guards the scraper's own API, which only the backend calls
    ingestToken,
    apiPort,
    daysBack,
    // How far back the first sync of a newly added login goes, so the history fills in
    firstDaysBack,
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
