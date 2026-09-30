import assert from 'node:assert/strict';
import { mkdtemp } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { after, before, test } from 'node:test';

import { createApi } from '../src/api.js';
import { AccountStore } from '../src/store.js';
import { SyncQueue } from '../src/sync.js';

const quiet = { log() {}, error() {} };
const TOKEN = 'test-token';
let server;
let base;
let queue;
const runs = [];

before(async () => {
  const dir = await mkdtemp(path.join(tmpdir(), 'api-'));
  const store = new AccountStore({ file: path.join(dir, 'accounts.json'), keyFile: path.join(dir, 'key') });
  const settings = { daysBack: 30, firstDaysBack: 365 };
  // A fake run: the password "wrong" fails the way a bank would
  const run = async (accounts, runSettings, { onResult }) => {
    for (const account of accounts) {
      runs.push({ company: account.company, daysBack: runSettings.daysBack });
      const ok = account.credentials.password !== 'wrong';
      onResult(account, { success: ok, error_type: ok ? null : 'INVALID_PASSWORD', finished_at: 'now' });
    }
    return true;
  };
  queue = new SyncQueue({ store, settings, run, log: quiet });
  server = createApi({ store, queue, token: TOKEN, log: quiet }).listen(0);
  await new Promise((resolve) => server.once('listening', resolve));
  base = `http://127.0.0.1:${server.address().port}`;
});

after(() => server.close());

function call(method, url, body, token = TOKEN) {
  return fetch(base + url, {
    method,
    headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}

async function listed(id) {
  return (await (await call('GET', '/accounts')).json()).find((a) => a.id === id);
}

test('needs the token', async () => {
  assert.equal((await call('GET', '/accounts', undefined, 'wrong')).status, 401);
  assert.equal((await fetch(`${base}/accounts`)).status, 401);
});

test('lists the supported companies and their login fields', async () => {
  const companies = await (await call('GET', '/companies')).json();
  assert.deepEqual(companies.find((c) => c.id === 'isracard').login_fields, ['id', 'card6Digits', 'password']);
  assert.ok(!companies.some((c) => c.id === 'oneZero'));
});

test('adding a login syncs it a year back, and nothing returned holds a credential', async () => {
  const response = await call('POST', '/accounts', {
    company: 'leumi',
    credentials: { username: 'me123456', password: 'secret-pw' },
  });
  assert.equal(response.status, 201);
  const text = await response.text();
  assert.ok(!text.includes('secret-pw') && !text.includes('me123456'));
  const added = JSON.parse(text);
  assert.equal(added.hint, '•••456');
  await queue.idle;
  assert.deepEqual(runs.at(-1), { company: 'leumi', daysBack: 365 });

  const after = await listed(added.id);
  assert.deepEqual(after.last_sync, { ok: true, error_type: null, finished_at: 'now' });
  assert.equal(after.sync, null);
});

test('a wrong password shows on the login, and fixing it syncs again', async () => {
  const added = await (
    await call('POST', '/accounts', { company: 'max', credentials: { username: 'u', password: 'wrong' } })
  ).json();
  await queue.idle;
  assert.equal((await listed(added.id)).last_sync.error_type, 'INVALID_PASSWORD');

  const updated = await call('PUT', `/accounts/${added.id}`, { credentials: { username: 'u', password: 'right' } });
  assert.equal(updated.status, 200);
  await queue.idle;
  assert.equal((await listed(added.id)).last_sync.ok, true);
  assert.deepEqual(runs.at(-1), { company: 'max', daysBack: 30 });
});

test('sync now runs every login', async () => {
  const before = runs.length;
  assert.equal((await call('POST', '/sync')).status, 202);
  await queue.idle;
  assert.equal(runs.length - before, 2);
});

test('validation, unknown ids and removal', async () => {
  const bad = await call('POST', '/accounts', { company: 'leumi', credentials: { username: 'u' } });
  assert.equal(bad.status, 422);
  assert.match((await bad.json()).detail, /missing credentials: password/);
  assert.equal((await call('PUT', '/accounts/nope', { credentials: {} })).status, 404);
  assert.equal((await call('POST', '/accounts/nope/sync')).status, 404);
  assert.equal((await call('GET', '/nothing')).status, 404);

  const accounts = await (await call('GET', '/accounts')).json();
  for (const a of accounts) assert.equal((await call('DELETE', `/accounts/${a.id}`)).status, 204);
  assert.deepEqual(await (await call('GET', '/accounts')).json(), []);
});

test('bad bodies are refused', async () => {
  const notJson = await fetch(`${base}/accounts`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${TOKEN}` },
    body: 'not json',
  });
  assert.equal(notJson.status, 400);
  const big = await call('POST', '/accounts', {
    company: 'leumi',
    credentials: { username: 'x'.repeat(20000), password: 'p' },
  });
  assert.equal(big.status, 413);
});
