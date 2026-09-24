import assert from 'node:assert/strict';
import { test } from 'node:test';

import { runAll, toPayload } from '../src/runner.js';

const settings = { daysBack: 30, saveRaw: false, outputDir: 'unused' };
const quiet = { log() {}, error() {} };
const accounts = [
  { company: 'leumi', credentials: { username: 'u', password: 'secret' } },
  { company: 'visaCal', credentials: { username: 'u', password: 'secret' } },
];
const ok = {
  success: true,
  accounts: [{ accountNumber: '123456', balance: 10, txns: [{ description: 'x', rawTransaction: { big: true } }] }],
};

test('toPayload drops rawTransaction and maps errors', () => {
  const t = new Date('2026-09-24T00:00:00Z');
  const payload = toPayload('leumi', t, t, ok);
  assert.deepEqual(payload.accounts[0].txns, [{ description: 'x' }]);
  assert.equal(payload.accounts[0].accountNumber, '123456');

  const failed = toPayload('leumi', t, t, { success: false, errorType: 'INVALID_PASSWORD' });
  assert.equal(failed.success, false);
  assert.equal(failed.error_type, 'INVALID_PASSWORD');
  assert.deepEqual(failed.accounts, []);
});

test('scrapes every account and ingests each result', async () => {
  const sent = [];
  const result = await runAll(accounts, settings, {
    scrape: async () => ok,
    ingest: async (_settings, payload) => {
      sent.push(payload);
      return { added: 1, duplicates: 0, pending_skipped: 0 };
    },
    log: quiet,
  });
  assert.equal(result, true);
  assert.deepEqual(sent.map((p) => p.institution), ['leumi', 'visaCal']);
  // Credentials never leave the scraper
  assert.ok(!JSON.stringify(sent).includes('secret'));
});

test('a failing account is logged and the rest still run', async () => {
  const sent = [];
  const result = await runAll(accounts, settings, {
    scrape: async (account) => {
      if (account.company === 'leumi') throw new Error('browser crashed');
      return ok;
    },
    ingest: async (_settings, payload) => {
      sent.push(payload);
      return { added: 0, duplicates: 0, pending_skipped: 0 };
    },
    log: quiet,
  });
  assert.equal(result, false);
  assert.equal(sent.length, 2);
  assert.equal(sent[0].success, false);
  assert.equal(sent[0].error_type, 'EXCEPTION');
  assert.equal(sent[0].error_message, 'browser crashed');
  assert.equal(sent[1].success, true);
});

test('a backend error is reported but does not stop the run', async () => {
  let calls = 0;
  const result = await runAll(accounts, settings, {
    scrape: async () => ok,
    ingest: async () => {
      calls += 1;
      throw new Error('connection refused');
    },
    log: quiet,
  });
  assert.equal(result, false);
  assert.equal(calls, 2);
});
