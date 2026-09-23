import { SCRAPERS } from 'israeli-bank-scrapers-core';

// Companies whose login needs an interactive OTP flow; handled in a later phase.
const UNSUPPORTED = new Set(['oneZero']);

export function loadConfig(env = process.env) {
  const company = env.SCRAPER_COMPANY;
  if (!company || !SCRAPERS[company] || UNSUPPORTED.has(company)) {
    const supported = Object.keys(SCRAPERS).filter((c) => !UNSUPPORTED.has(c));
    throw new Error(`SCRAPER_COMPANY must be one of: ${supported.join(', ')}`);
  }

  let credentials;
  try {
    credentials = JSON.parse(env.SCRAPER_CREDENTIALS ?? '');
  } catch {
    throw new Error('SCRAPER_CREDENTIALS must be a JSON object');
  }
  if (typeof credentials !== 'object' || credentials === null || Array.isArray(credentials)) {
    throw new Error('SCRAPER_CREDENTIALS must be a JSON object');
  }
  const missing = SCRAPERS[company].loginFields.filter((field) => !credentials[field]);
  if (missing.length > 0) {
    throw new Error(`SCRAPER_CREDENTIALS for ${company} is missing: ${missing.join(', ')}`);
  }

  const daysBack = Number(env.SCRAPER_DAYS_BACK ?? 30);
  if (!Number.isInteger(daysBack) || daysBack < 1) {
    throw new Error('SCRAPER_DAYS_BACK must be a positive integer');
  }

  return {
    company,
    credentials,
    daysBack,
    executablePath: env.PUPPETEER_EXECUTABLE_PATH || undefined,
    outputDir: env.SCRAPER_OUTPUT_DIR || 'output',
  };
}

// Show only the last 4 digits of an account number in logs.
export function maskAccountNumber(accountNumber) {
  const s = String(accountNumber ?? '');
  return s.length <= 4 ? s : `…${s.slice(-4)}`;
}
