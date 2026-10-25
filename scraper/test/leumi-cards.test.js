import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  brokerBody,
  chargeFromItem,
  cyclesSince,
  fetchCardAccounts,
  parseBrokerReply,
  parseBrokerRequest,
  parseInstallments,
  shiftMonths,
} from '../src/leumi-cards.js';

const quiet = { warn() {} };
const session = { SessionID: 'abc', FIID: 'LEUMI' };

// Shaped like the card page's own replies (values made up)
const item = (fields = {}) => ({
  DateDealUTC: '2026-09-14T21:00:00.000Z',
  AmountDouble: 120.5,
  DebitCardFirmName: 'שופרסל דיל                       ',
  TransactionCurrency: '-1',
  TypeOfTransaction: 111,
  DealDescription: '',
  NextPaymentAmountDouble: 120.5,
  NextPaymentAmountDoubleSpecified: true,
  CardTransactionId: '111',
  DebitCardDebitPeriodUTC: '2026-10-01T21:00:00.000Z',
  ...fields,
});

test('the session template is copied from the site, without browser headers', () => {
  const body = JSON.stringify({
    moduleName: 'UC_SO_GetAccounts',
    reqObj: JSON.stringify({ StateName: 'TsSummary', ModuleName: 'UC_SO_GetAccounts', SessionHeader: session, AccountIndex: 1 }),
    version: 'V1.0',
  });
  const template = parseBrokerRequest(body, { 'content-type': 'application/json', cookie: 's=1', 'sec-fetch-mode': 'cors', 'x-token': 't' });
  assert.deepEqual(template, {
    version: 'V1.0',
    sessionHeader: session,
    stateName: 'TsSummary',
    accountIndex: 1,
    headers: { 'content-type': 'application/json', 'x-token': 't' },
  });
  assert.equal(parseBrokerRequest('not json'), undefined);
  assert.equal(parseBrokerRequest(JSON.stringify({ reqObj: '{}' })), undefined);

  const sent = JSON.parse(brokerBody(template, 'UC_MS_125_CreditCardsInfo', { CardIndex: 8, Operation: 2 }));
  assert.equal(sent.moduleName, 'UC_MS_125_CreditCardsInfo');
  assert.equal(sent.version, 'V1.0');
  assert.deepEqual(JSON.parse(sent.reqObj), {
    StateName: 'TsSummary',
    ModuleName: 'UC_MS_125_CreditCardsInfo',
    SessionHeader: session,
    CardIndex: 8,
    Operation: 2,
    AccountIndex: 1,
  });
});

test('replies are unwrapped and refusals raise', () => {
  const reply = (data) => JSON.stringify({ ProcessRequestResult: 0, jsonResp: JSON.stringify(data) });
  assert.deepEqual(parseBrokerReply('M', reply({ SOStatus: { Status: true }, A: 1 })), { SOStatus: { Status: true }, A: 1 });
  assert.throws(
    () => parseBrokerReply('M', reply({ SOStatus: { Status: false, SOStatusItem: [{ Message: 'שגיאה' }] } })),
    /M was refused: שגיאה/,
  );
});

test('installments are read from the deal text and dated like israeli-bank-scrapers', () => {
  assert.deepEqual(parseInstallments('תשלום 2 מתוך 6'), { number: 2, total: 6 });
  assert.deepEqual(parseInstallments('3 מ-10'), { number: 3, total: 10 });
  assert.equal(parseInstallments(''), undefined);
  assert.equal(parseInstallments(null), undefined);
  assert.equal(parseInstallments('7 מתוך 6'), undefined);

  // Israel time: 2026-01-30T22:00Z is Jan 31; a month later clamps to Feb 28
  assert.equal(shiftMonths('2026-01-30T22:00:00.000Z', 1), '2026-02-28T00:00:00');
  // Across the end of summer time the local day stays the same
  assert.equal(shiftMonths('2026-09-14T21:00:00.000Z', 2), '2026-11-15T00:00:00');

  const charge = chargeFromItem(item({ AmountDouble: 600, NextPaymentAmountDouble: 100, DealDescription: 'תשלום 2 מתוך 6' }), '2026-11-02T00:00:00');
  assert.equal(charge.type, 'installments');
  assert.deepEqual(charge.installments, { number: 2, total: 6 });
  assert.equal(charge.date, '2026-10-15T00:00:00');
  assert.equal(charge.chargedAmount, -100);
  assert.equal(charge.originalAmount, -600);
});

test('a charge maps to a SmartFin transaction', () => {
  assert.deepEqual(chargeFromItem(item(), '2026-10-02T00:00:00'), {
    type: 'normal',
    identifier: '111@2026-10-02',
    date: '2026-09-14T21:00:00.000Z',
    processedDate: '2026-10-01T21:00:00.000Z',
    originalAmount: -120.5,
    originalCurrency: 'ILS',
    chargedAmount: -120.5,
    chargedCurrency: 'ILS',
    description: 'שופרסל דיל',
    memo: undefined,
    installments: undefined,
    status: 'completed',
  });
  // A partial charge with no installment text is dated by its bill
  const partial = chargeFromItem(item({ AmountDouble: 600, NextPaymentAmountDouble: 100 }), '2026-10-02T00:00:00');
  assert.equal(partial.date, '2026-10-01T21:00:00.000Z');
  // A refund comes back as money in
  assert.equal(chargeFromItem(item({ AmountDouble: -50, NextPaymentAmountDouble: -50 }), '2026-10-02T00:00:00').chargedAmount, 50);
});

test('only bills paid since the start date are fetched', () => {
  const cycles = [{ CycleDate: '2026-11-02T00:00:00' }, { CycleDate: '2026-10-02T00:00:00' }, { CycleDate: '2026-09-02T00:00:00' }];
  assert.deepEqual(cyclesSince(cycles, new Date('2026-10-01T00:00:00Z')), cycles.slice(0, 2));
});

test('every card and bill is fetched; pending charges come from the open bill', async () => {
  const calls = [];
  const replies = {
    UC_SO_GetCreditCardsInfo: () => ({ CreditCardsItems: [{ CardIndex: 8, CardLast4Digits: '1234' }, { CardIndex: 9, CardLast4Digits: '5678' }] }),
    2: () => ({
      Graph: {
        DebitMonthItems: [
          { CycleDate: '2026-11-02T00:00:00', DefaultMonth: true },
          { CycleDate: '2026-10-02T00:00:00', DefaultMonth: false },
          { CycleDate: '2025-01-02T00:00:00', DefaultMonth: false },
        ],
      },
    }),
    3: (fields) =>
      fields.CardIndex === 9
        ? { Activity: null }
        : {
            Activity: {
              TabNisTransactionItems: [{ NisTransactionItems: [item({ CardTransactionId: fields.CycleDate })] }],
              TabForeignTransactionItems: [],
              RealTimeTransItems: fields.CardPeriodType === 2
                ? [{ CreditTransactionIdStr: '77', DebitCardFirmName: 'קפה  ', AmountDouble: 18, DateDealUTC: '2026-10-24T21:00:00.000Z', MCC4Description: ' מסעדות ' }]
                : null,
            },
          },
  };
  const call = async (moduleName, fields) => {
    calls.push([moduleName, fields]);
    return (replies[moduleName] ?? replies[fields.Operation])(fields);
  };

  const accounts = await fetchCardAccounts(call, new Date('2026-09-01T00:00:00Z'), quiet);
  assert.deepEqual(accounts.map((a) => [a.accountNumber, a.txns.length]), [['1234', 3], ['5678', 0]]);
  const [current, older, pending] = accounts[0].txns;
  assert.equal(current.identifier, '2026-11-02T00:00:00@2026-11-02');
  assert.equal(older.identifier, '2026-10-02T00:00:00@2026-10-02');
  assert.deepEqual(pending, {
    type: 'normal',
    identifier: '77',
    date: '2026-10-24T21:00:00.000Z',
    originalAmount: -18,
    originalCurrency: 'ILS',
    chargedAmount: -18,
    description: 'קפה',
    memo: 'מסעדות',
    status: 'pending',
  });

  // The open bill is asked for as "current", older ones by date, and the 2025 bill not at all
  const charges = calls.filter(([, f]) => f.Operation === 3 && f.CardIndex === 8).map(([, f]) => [f.CardPeriodType, f.CycleDate]);
  assert.deepEqual(charges, [[2, '2026-11-02T00:00:00'], [99, '2026-10-02T00:00:00']]);
});

test('foreign-currency charges are counted and skipped, not guessed at', async () => {
  const warnings = [];
  const call = async (moduleName, fields) => {
    if (moduleName === 'UC_SO_GetCreditCardsInfo') return { CreditCardsItems: [{ CardIndex: 1, CardLast4Digits: '1234' }] };
    if (fields.Operation === 2) return { Graph: { DebitMonthItems: [{ CycleDate: '2026-11-02T00:00:00', DefaultMonth: true }] } };
    return { Activity: { TabNisTransactionItems: [], TabForeignTransactionItems: [{ ForeignItems: [{}, {}] }] } };
  };
  const accounts = await fetchCardAccounts(call, new Date('2026-09-01T00:00:00Z'), { warn: (m) => warnings.push(m) });
  assert.deepEqual(accounts, [{ accountNumber: '1234', txns: [] }]);
  assert.deepEqual(warnings, ['[leumiCards] card 1234: 2 foreign-currency charges skipped']);
});
