import assert from 'node:assert/strict';
import { test } from 'node:test';

import { isRetryable } from '../src/retry.js';
import { runAll } from '../src/runner.js';
import { SyncQueue } from '../src/sync.js';

const quiet = { log() {}, error() {} };
const fail = (error_type) => ({ success: false, error_type });

test('only passing card failures are retried', () => {
  assert.equal(isRetryable('isracard', fail('GENERIC')), true);
  assert.equal(isRetryable('leumiCards', fail('TIMEOUT')), true);
  assert.equal(isRetryable('isracard', fail('EXCEPTION')), true);
  assert.equal(isRetryable('isracard', fail('INVALID_PASSWORD')), false);
  assert.equal(isRetryable('max', fail('ACCOUNT_BLOCKED')), false);
  assert.equal(isRetryable('leumi', fail('GENERIC')), false);
  assert.equal(isRetryable('isracard', { success: true }), false);
});

function store(accounts) {
  return { list: async () => accounts };
}

/** A queue whose fake scrapes go by `outcomes[id]`: one result per attempt, the last repeating */
function setup(accounts, outcomes, settings = { retries: 10, retryMinutes: 10 }) {
  const attempts = {};
  const ingested = [];
  const scrape = async (account) => {
    const n = (attempts[account.id] = (attempts[account.id] ?? 0) + 1);
    const list = outcomes[account.id];
    return list[Math.min(n, list.length) - 1];
  };
  const run = (accs, s, options) =>
    runAll(accs, s, {
      ...options,
      scrape,
      ingest: async (_s, payload) => {
        ingested.push([payload.institution, payload.success, payload.error_type]);
        return { added: 0, duplicates: 0, pending_skipped: 0 };
      },
      log: quiet,
    });
  const sleeps = [];
  const queue = new SyncQueue({ store: store(accounts), settings: { daysBack: 30, ...settings }, run, log: quiet });
  const nightly = () => queue.runNightly({ sleep: async (ms) => sleeps.push(ms) });
  return { queue, nightly, attempts, ingested, sleeps };
}

const OK = { success: true, accounts: [] };
const BLOCKED = { success: false, errorType: 'GENERIC', errorMessage: '403' };

test('a card that fails is retried until it works, and its earlier failures are not reported', async () => {
  const accounts = [
    { id: 'bank', company: 'leumi', credentials: {} },
    { id: 'card', company: 'isracard', credentials: {} },
  ];
  const { nightly, attempts, ingested, sleeps } = setup(accounts, {
    bank: [OK],
    card: [BLOCKED, BLOCKED, BLOCKED, OK],
  });
  await nightly();
  assert.deepEqual(attempts, { bank: 1, card: 4 });
  assert.deepEqual(sleeps, [600_000, 600_000, 600_000]);
  // No alert-raising failure reached the backend: the card got through in the end
  assert.deepEqual(ingested, [['leumi', true, null], ['isracard', true, null]]);
});

test('a card that keeps failing is tried 1 + 10 times and only the last failure is reported', async () => {
  const accounts = [{ id: 'card', company: 'isracard', credentials: {} }];
  const { queue, nightly, attempts, ingested, sleeps } = setup(accounts, { card: [BLOCKED] });
  await nightly();
  assert.equal(attempts.card, 11);
  assert.equal(sleeps.length, 10);
  assert.deepEqual(ingested, [['isracard', false, 'GENERIC']]);
  assert.equal(queue.results.get('card').ok, false);
  assert.equal(queue.retries.size, 0);
});

test('a wrong password is never retried, and a bank is not retried', async () => {
  const accounts = [
    { id: 'card', company: 'max', credentials: {} },
    { id: 'bank', company: 'hapoalim', credentials: {} },
  ];
  const { nightly, attempts, ingested, sleeps } = setup(accounts, {
    card: [{ success: false, errorType: 'INVALID_PASSWORD' }],
    bank: [BLOCKED],
  });
  await nightly();
  assert.deepEqual(attempts, { card: 1, bank: 1 });
  assert.deepEqual(sleeps, []);
  assert.deepEqual(ingested, [['max', false, 'INVALID_PASSWORD'], ['hapoalim', false, 'GENERIC']]);
});

test('Leumi cards that fail are retried through the Leumi login', async () => {
  const accounts = [{ id: 'leumi', company: 'leumi', credentials: {} }];
  const withCards = (cards) => ({ success: true, accounts: [], cards });
  const { nightly, attempts, ingested } = setup(accounts, {
    leumi: [withCards(BLOCKED), withCards(OK)],
  });
  await nightly();
  assert.equal(attempts.leumi, 2);
  assert.deepEqual(ingested, [
    ['leumi', true, null],
    ['leumi', true, null],
    ['leumiCards', true, null],
  ]);
});

test('the retry wait shows on the login, and retries can be turned off', async () => {
  const accounts = [{ id: 'card', company: 'isracard', credentials: {} }];
  const { queue, attempts } = setup(accounts, { card: [BLOCKED, OK] });
  let seen;
  await queue.runNightly({
    now: () => Date.parse('2026-11-04T01:00:00Z'),
    sleep: async () => {
      seen = queue.retries.get('card');
    },
  });
  assert.deepEqual(seen, { attempt: 1, of: 10, at: '2026-11-04T01:10:00.000Z' });
  assert.equal(attempts.card, 2);

  const off = setup(accounts, { card: [BLOCKED] }, { retries: 0 });
  await off.nightly();
  assert.equal(off.attempts.card, 1);
  assert.deepEqual(off.ingested, [['isracard', false, 'GENERIC']]);
});

test('a sync run by hand during the wait stops the retries', async () => {
  const accounts = [{ id: 'card', company: 'isracard', credentials: {} }];
  const { queue, attempts } = setup(accounts, { card: [BLOCKED, OK, BLOCKED] });
  await queue.runNightly({
    sleep: async () => {
      queue.enqueue(['card']);
      await queue.idle;
    },
  });
  assert.equal(attempts.card, 2);
  assert.equal(queue.results.get('card').ok, true);
});
