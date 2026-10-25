import assert from 'node:assert/strict';
import { test } from 'node:test';

import { maskString, maskUrl, maskValue, summarize } from '../src/har-summary.js';

const secrets = ['4580123412341234', 'Menashe', 'מנשה', 'abc123', 'SESSION=deadbeef', '12-345-678901', 'tok9f8e7d6c5b4a'];

const reply = {
  jsonResp: JSON.stringify({
    CardsList: [{ CardNumber: '4580123412341234', HolderName: 'Menashe', Owner: 'מנשה' }],
    Transactions: [
      { Date: '2026-10-12T00:00:00', Amount: -123.45, Currency: 'ILS', Merchant: 'שופרסל דיל' },
      { Date: '2026-10-13T00:00:00', Amount: -9.9, Currency: 'USD', Merchant: 'SPOTIFY' },
      { Date: '2026-10-14T00:00:00', Amount: -50, Currency: 'ILS', Merchant: 'רמי לוי' },
      { Date: '2026-10-15T00:00:00', Amount: -1, Currency: 'ILS', Merchant: 'x' },
    ],
    '12-345-678901': { balance: 1000 },
  }),
};

const har = {
  log: {
    entries: [
      {
        request: {
          method: 'POST',
          url: 'https://hb2.bankleumi.co.il/ChannelWCF/Broker.svc/ProcessRequest?moduleName=UC_SO_27_Cards&account=12-345-678901&sid=tok9f8e7d6c5b4a',
          headers: [{ name: 'Cookie', value: 'SESSION=deadbeef' }],
          cookies: [{ name: 'SESSION', value: 'deadbeef' }],
          postData: { text: JSON.stringify({ user: 'abc123', account: '12-345-678901' }) },
        },
        response: {
          status: 200,
          headers: [{ name: 'Set-Cookie', value: 'SESSION=deadbeef' }],
          content: { size: 999, encoding: 'base64', text: Buffer.from(JSON.stringify(reply)).toString('base64') },
        },
      },
      {
        request: { method: 'GET', url: 'https://hb2.bankleumi.co.il/app.js' },
        response: { status: 200, content: { text: 'var x = "Menashe";' } },
      },
    ],
  },
};

test('no secret survives, but field names and formats do', () => {
  const summary = summarize(har);
  const text = JSON.stringify(summary);
  for (const secret of secrets) assert.ok(!text.includes(secret), `leaked ${secret}`);

  assert.equal(summary.entries, 2);
  assert.equal(summary.calls, 1);
  const [call] = summary.json;
  assert.equal(call.url, 'hb2.bankleumi.co.il/ChannelWCF/Broker.svc/ProcessRequest?moduleName=UC_SO_27_Cards&account=99-999-999999&sid=xxx9x9x9x9x9x9x');
  const inner = call.response.jsonResp['(json string)'];
  assert.deepEqual(inner.Transactions[0], { Date: '9999-99-99x99:99:99', Amount: 'num:-999.99', Currency: 'ILS', Merchant: 'אאאאאא אאא' });
  assert.equal(inner.Transactions.at(-1), '…(+1 more)');
  assert.deepEqual(inner['99-999-999999'], { balance: 'num:9999' });
});

test('--keep-text keeps digit-free strings only', () => {
  assert.equal(maskString('שופרסל דיל', { keepText: true }), 'שופרסל דיל');
  assert.equal(maskString('abc123', { keepText: true }), 'xxx999');
  assert.deepEqual(maskValue({ a: true, b: null }), { a: true, b: null });
  assert.equal(maskUrl('https://x.co.il/a/1234567'), 'x.co.il/a/9999999');
});
