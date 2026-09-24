import assert from 'node:assert/strict';
import { test } from 'node:test';

import { loadSettings, maskAccountNumber, parseAccounts } from '../src/config.js';

const leumi = { company: 'leumi', credentials: { username: 'u', password: 'p' } };

test('parses a valid accounts file', () => {
  assert.deepEqual(parseAccounts(JSON.stringify([leumi])), [leumi]);
});

test('rejects malformed or empty accounts files', () => {
  assert.throws(() => parseAccounts('not json'), /not valid JSON/);
  assert.throws(() => parseAccounts('[]'), /non-empty JSON array/);
  assert.throws(() => parseAccounts('{}'), /non-empty JSON array/);
  assert.throws(() => parseAccounts('[1]'), /accounts\[0\] must be an object/);
});

test('rejects unknown and OTP-only companies', () => {
  for (const company of ['nope', 'oneZero']) {
    assert.throws(
      () => parseAccounts(JSON.stringify([{ ...leumi, company }])),
      /accounts\[0\]\.company must be one of/,
    );
  }
});

test('names the missing login fields and which entry has them', () => {
  const accounts = [leumi, { company: 'isracard', credentials: { id: '1' } }];
  assert.throws(
    () => parseAccounts(JSON.stringify(accounts)),
    /accounts\[1\] \(isracard\) is missing credentials: card6Digits, password/,
  );
});

test('loads settings with defaults', () => {
  const settings = loadSettings({ BACKEND_URL: 'http://backend:8000', INGEST_TOKEN: 't' });
  assert.equal(settings.daysBack, 30);
  assert.equal(settings.scrapeTime, '03:00');
  assert.equal(settings.saveRaw, false);
  assert.equal(settings.accountsFile, 'config/accounts.json');
});

test('requires the backend unless ingest is off', () => {
  assert.throws(() => loadSettings({}), /BACKEND_URL and INGEST_TOKEN/);
  assert.doesNotThrow(() => loadSettings({}, { requireIngest: false }));
});

test('rejects bad numbers and times', () => {
  const opts = { requireIngest: false };
  assert.throws(() => loadSettings({ SCRAPER_DAYS_BACK: '0' }, opts), /positive integer/);
  assert.throws(() => loadSettings({ SCRAPER_DAYS_BACK: 'abc' }, opts), /positive integer/);
  assert.throws(() => loadSettings({ SCRAPE_TIME: '3am' }, opts), /HH:MM/);
  assert.throws(() => loadSettings({ SCRAPE_TIME: '24:00' }, opts), /HH:MM/);
});

test('masks account numbers to the last 4 digits', () => {
  assert.equal(maskAccountNumber('12-345-678901'), '…8901');
  assert.equal(maskAccountNumber('123'), '123');
});
