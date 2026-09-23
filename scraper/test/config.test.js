import assert from 'node:assert/strict';
import { test } from 'node:test';

import { loadConfig, maskAccountNumber } from '../src/config.js';

const valid = {
  SCRAPER_COMPANY: 'leumi',
  SCRAPER_CREDENTIALS: '{"username": "u", "password": "p"}',
};

test('loads a valid config with defaults', () => {
  const config = loadConfig(valid);
  assert.equal(config.company, 'leumi');
  assert.deepEqual(config.credentials, { username: 'u', password: 'p' });
  assert.equal(config.daysBack, 30);
  assert.equal(config.outputDir, 'output');
});

test('rejects unknown and OTP-only companies', () => {
  assert.throws(() => loadConfig({ ...valid, SCRAPER_COMPANY: 'nope' }), /must be one of/);
  assert.throws(() => loadConfig({ ...valid, SCRAPER_COMPANY: 'oneZero' }), /must be one of/);
});

test('rejects malformed credentials', () => {
  assert.throws(() => loadConfig({ ...valid, SCRAPER_CREDENTIALS: 'not json' }), /JSON object/);
  assert.throws(() => loadConfig({ ...valid, SCRAPER_CREDENTIALS: '[]' }), /JSON object/);
});

test('names the missing login fields for the company', () => {
  assert.throws(
    () => loadConfig({ SCRAPER_COMPANY: 'isracard', SCRAPER_CREDENTIALS: '{"id": "1"}' }),
    /missing: card6Digits, password/,
  );
});

test('rejects a bad SCRAPER_DAYS_BACK', () => {
  assert.throws(() => loadConfig({ ...valid, SCRAPER_DAYS_BACK: '0' }), /positive integer/);
  assert.throws(() => loadConfig({ ...valid, SCRAPER_DAYS_BACK: 'abc' }), /positive integer/);
});

test('masks account numbers to the last 4 digits', () => {
  assert.equal(maskAccountNumber('12-345-678901'), '…8901');
  assert.equal(maskAccountNumber('123'), '123');
});
