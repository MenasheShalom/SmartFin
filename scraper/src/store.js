// The bank and card logins, kept encrypted in accounts.json.enc and managed from the web app.
import { randomUUID } from 'node:crypto';
import { mkdir, readFile, rename, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';

import { loadAccounts, loginFields, SUPPORTED_COMPANIES, validateAccount } from './config.js';
import { encrypt, newKey } from './crypto.js';

export class NotFound extends Error {}

// What the web app may see of a login: never a password or any other credential in full
export function publicAccount(account) {
  const [first] = Object.entries(account.credentials).filter(([field]) => field !== 'password');
  return {
    id: account.id,
    company: account.company,
    // e.g. "•••789", so two logins at the same bank can be told apart
    hint: first ? hint(first[1]) : null,
    added_at: account.addedAt ?? null,
  };
}

function hint(value) {
  const s = String(value);
  return s.length <= 4 ? '•••' : `•••${s.slice(-3)}`;
}

export class AccountStore {
  /**
   * @param {object} options
   * @param {string} options.file  the plain-text path; the encrypted file is `${file}.enc`
   * @param {string} [options.key]  SCRAPER_ACCOUNTS_KEY; otherwise read from, or created in, keyFile
   * @param {string} options.keyFile
   */
  constructor({ file, key, keyFile }) {
    this.file = file;
    this.envKey = key || null;
    this.keyFile = keyFile;
    // Writes run one at a time, each on top of the one before
    this.queue = Promise.resolve();
  }

  /** The encryption key; with create, a new one is made in keyFile when there is none */
  async key({ create = false } = {}) {
    if (this.envKey) return this.envKey;
    try {
      return (await readFile(this.keyFile, 'utf8')).trim();
    } catch (err) {
      if (err.code !== 'ENOENT') throw err;
    }
    if (!create) return null;
    const key = newKey();
    await mkdir(path.dirname(this.keyFile), { recursive: true });
    await writeFile(this.keyFile, key, { mode: 0o600 });
    return key;
  }

  /** Every login, with an id (hand-written entries get one on the next save) */
  async list() {
    const key = await this.key();
    const accounts = await loadAccounts(this.file, key ?? undefined);
    return accounts.map((a, i) => ({ id: a.id ?? `file-${i}`, ...a }));
  }

  async get(id) {
    const account = (await this.list()).find((a) => a.id === id);
    if (!account) throw new NotFound(`No login ${id}`);
    return account;
  }

  async add({ company, credentials }) {
    return this.#change((accounts) => {
      const account = {
        id: randomUUID(),
        addedAt: new Date().toISOString(),
        ...validateAccount({ company, credentials: cleanCredentials(company, credentials) }),
      };
      accounts.push(account);
      return account;
    });
  }

  /** Replace a login's credentials; the company stays */
  async update(id, credentials) {
    return this.#change((accounts) => {
      const index = accounts.findIndex((a) => a.id === id);
      if (index === -1) throw new NotFound(`No login ${id}`);
      const { company, addedAt } = accounts[index];
      accounts[index] = { id, addedAt, ...validateAccount({ company, credentials: cleanCredentials(company, credentials) }) };
      return accounts[index];
    });
  }

  async remove(id) {
    return this.#change((accounts) => {
      const index = accounts.findIndex((a) => a.id === id);
      if (index === -1) throw new NotFound(`No login ${id}`);
      accounts.splice(index, 1);
    });
  }

  #change(edit) {
    const run = this.queue.then(async () => {
      const accounts = await this.list();
      const result = edit(accounts);
      await this.#save(accounts);
      return result;
    });
    this.queue = run.catch(() => {});
    return run;
  }

  async #save(accounts) {
    const key = await this.key({ create: true });
    const sealed = `${this.file}.enc`;
    const temp = `${sealed}.tmp`;
    await mkdir(path.dirname(sealed), { recursive: true });
    await writeFile(temp, encrypt(JSON.stringify(accounts, null, 2), key), { mode: 0o600 });
    await rename(temp, sealed);
    // A hand-written plain file has now been folded into the encrypted one
    await rm(this.file, { force: true });
  }
}

// Just the company's login fields, trimmed (passwords are kept exactly as typed)
function cleanCredentials(company, credentials) {
  if (!SUPPORTED_COMPANIES.includes(company)) return credentials; // validateAccount names the problem
  if (typeof credentials !== 'object' || credentials === null || Array.isArray(credentials)) return credentials;
  return Object.fromEntries(
    loginFields(company)
      .filter((field) => typeof credentials[field] === 'string')
      .map((field) => [field, field === 'password' ? credentials[field] : credentials[field].trim()]),
  );
}
