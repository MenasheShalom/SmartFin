import assert from 'node:assert/strict';
import { mkdir, mkdtemp, readFile, stat, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { test } from 'node:test';

import { newKey } from '../src/crypto.js';
import { AccountStore, NotFound, publicAccount } from '../src/store.js';

async function tempStore(options = {}) {
  const dir = await mkdtemp(path.join(tmpdir(), 'store-'));
  const file = path.join(dir, 'config', 'accounts.json');
  const keyFile = path.join(dir, 'keys', 'accounts.key');
  return { store: new AccountStore({ file, keyFile, ...options }), file, keyFile };
}

const leumi = { company: 'leumi', credentials: { username: ' me123456 ', password: ' סיסמה ' } };

test('starts empty, then adds, updates and removes logins, always encrypted', async () => {
  const { store, file, keyFile } = await tempStore();
  assert.deepEqual(await store.list(), []);

  const added = await store.add({ ...leumi, credentials: { ...leumi.credentials, extra: 'dropped' } });
  assert.match(added.id, /^[0-9a-f-]{36}$/);
  assert.deepEqual(added.credentials, { username: 'me123456', password: ' סיסמה ' });

  const sealed = await readFile(`${file}.enc`, 'utf8');
  assert.ok(!sealed.includes('me123456'));
  assert.ok((await stat(keyFile)).isFile());

  const [listed] = await store.list();
  assert.equal(listed.id, added.id);

  const updated = await store.update(added.id, { username: 'other', password: 'new' });
  assert.equal(updated.company, 'leumi');
  assert.equal(updated.addedAt, added.addedAt);
  assert.equal((await store.get(added.id)).credentials.username, 'other');

  await store.remove(added.id);
  assert.deepEqual(await store.list(), []);
  await assert.rejects(store.remove(added.id), NotFound);
});

test('rejects bad logins without saving them', async () => {
  const { store } = await tempStore();
  await assert.rejects(store.add({ company: 'nope', credentials: {} }), /company must be one of/);
  await assert.rejects(
    store.add({ company: 'isracard', credentials: { id: '1', password: 'p' } }),
    /missing credentials: card6Digits/,
  );
  await assert.rejects(
    store.add({ company: 'leumi', credentials: { username: 'u', password: 5 } }),
    /missing credentials: password/,
  );
  assert.deepEqual(await store.list(), []);
});

test('uses SCRAPER_ACCOUNTS_KEY when set, and folds a hand-written file into the encrypted one', async () => {
  const { store, file, keyFile } = await tempStore({ key: newKey() });
  await mkdir(path.dirname(file), { recursive: true });
  await writeFile(file, JSON.stringify([leumi]));
  const [handWritten] = await store.list();
  assert.equal(handWritten.id, 'file-0');

  await store.add({ company: 'max', credentials: { username: 'u', password: 'p' } });
  await assert.rejects(stat(file), { code: 'ENOENT' });
  await assert.rejects(stat(keyFile), { code: 'ENOENT' });
  assert.deepEqual((await store.list()).map((a) => a.company), ['leumi', 'max']);
});

test('concurrent changes all land', async () => {
  const { store } = await tempStore();
  await Promise.all(
    ['a1', 'b2', 'c3'].map((username) => store.add({ company: 'max', credentials: { username, password: 'p' } })),
  );
  assert.equal((await store.list()).length, 3);
});

test('the public view never carries a credential', () => {
  const view = publicAccount({
    id: 'x',
    company: 'isracard',
    addedAt: 't',
    credentials: { id: '123456789', card6Digits: '123456', password: 'secret' },
  });
  assert.deepEqual(view, { id: 'x', company: 'isracard', hint: '•••789', added_at: 't' });
});
