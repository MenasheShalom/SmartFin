// Encrypt config/accounts.json into config/accounts.json.enc:  npm run encrypt-accounts
import { readFile, writeFile } from 'node:fs/promises';

import { parseAccounts } from './config.js';
import { encrypt, newKey } from './crypto.js';

const file = process.env.SCRAPER_ACCOUNTS_FILE || 'config/accounts.json';

try {
  const text = await readFile(file, 'utf8');
  parseAccounts(text); // refuse to encrypt a broken file
  let key = process.env.SCRAPER_ACCOUNTS_KEY;
  if (!key) {
    key = newKey();
    console.log(`New key. Add this line to .env:\n\nSCRAPER_ACCOUNTS_KEY=${key}\n`);
  }
  await writeFile(`${file}.enc`, encrypt(text, key), { mode: 0o600 });
  console.log(`Wrote ${file}.enc. Check that the scraper starts, then delete ${file}.`);
} catch (err) {
  console.error(err.message);
  process.exitCode = 1;
}
