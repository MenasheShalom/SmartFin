import assert from 'node:assert/strict';
import { mkdtemp, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { loadAccounts } from '../src/config.js';
import { decrypt, encrypt, newKey } from '../src/crypto.js';

const accounts = JSON.stringify([{ company: 'leumi', credentials: { username: 'u', password: 'סיסמה' } }]);

test('round trip, and a wrong key is refused', () => {
  const key = newKey();
  const sealed = encrypt(accounts, key);
  assert.ok(!sealed.includes('סיסמה'));
  assert.equal(decrypt(sealed, key), accounts);
  assert.throws(() => decrypt(sealed, newKey()), /wrong SCRAPER_ACCOUNTS_KEY/);
  assert.throws(() => encrypt(accounts, 'short'), /32 bytes/);
});

test('tampering is detected', () => {
  const key = newKey();
  const box = JSON.parse(encrypt(accounts, key));
  box.data = Buffer.from('x' + Buffer.from(box.data, 'base64').toString('latin1').slice(1), 'latin1').toString('base64');
  assert.throws(() => decrypt(JSON.stringify(box), key));
});

test('loadAccounts prefers the encrypted file', async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'accounts-'));
  const file = path.join(dir, 'accounts.json');
  await writeFile(file, '[{"company":"max","credentials":{"username":"a","password":"b"}}]');
  assert.equal((await loadAccounts(file))[0].company, 'max');

  const key = newKey();
  await writeFile(`${file}.enc`, encrypt(accounts, key));
  assert.equal((await loadAccounts(file, key))[0].company, 'leumi');
  await assert.rejects(loadAccounts(file, undefined), /SCRAPER_ACCOUNTS_KEY is not set/);
});
