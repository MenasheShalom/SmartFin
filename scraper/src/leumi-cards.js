// Leumi credit cards, read through the bank's own site right after the regular Leumi scrape.
// israeli-bank-scrapers only reads the checking account there; the card pages call the same
// Broker.svc endpoint with a session header the site adds itself, so that header (and the
// request format) is copied from the site's own requests and reused for the card modules.
import LeumiModule from 'israeli-bank-scrapers-core/lib/scrapers/leumi/leumi.js';

const LeumiScraper = LeumiModule.default ?? LeumiModule;

// Card accounts are stored under their own institution, so they become credit-card accounts
export const CARDS_COMPANY = 'leumiCards';

const BROKER_URL = 'https://hb2.bankleumi.co.il/ChannelWCF/Broker.svc/ProcessRequest';
const CARDS_MODULE = 'UC_SO_GetCreditCardsInfo';
const CARD_MODULE = 'UC_MS_125_CreditCardsInfo';
// UC_MS_125 operations, as the card page uses them
const OPERATION_MONTHS = 2;
const OPERATION_CHARGES = 3;
// The open bill is asked for as "current"; any other bill by its CycleDate
const PERIOD_CURRENT = 2;
const PERIOD_BY_DATE = 99;
const TZ = 'Asia/Jerusalem';
// Headers the browser sets itself (or refuses to let a page set)
const BROWSER_HEADERS = new Set(['cookie', 'host', 'content-length', 'origin', 'referer', 'user-agent', 'accept-encoding', 'connection']);

export function parseBrokerRequest(body, headers = {}) {
  try {
    const outer = JSON.parse(body);
    const inner = JSON.parse(outer.reqObj);
    if (!inner.SessionHeader) return undefined;
    return {
      version: outer.version,
      sessionHeader: inner.SessionHeader,
      stateName: inner.StateName,
      accountIndex: inner.AccountIndex ?? 1,
      headers: Object.fromEntries(
        Object.entries(headers).filter(([name]) => !BROWSER_HEADERS.has(name) && !name.startsWith('sec-') && !name.startsWith(':')),
      ),
    };
  } catch {
    return undefined;
  }
}

// Keep the latest request template the site itself sends while the bank scrape runs
function watchBrokerRequests(page) {
  const latest = {};
  page.on('request', (request) => {
    // Requests with ?moduleName= carry the same version string as the card modules
    if (request.method() !== 'POST' || !request.url().startsWith(`${BROKER_URL}?moduleName=`)) return;
    Object.assign(latest, parseBrokerRequest(request.postData(), request.headers()));
  });
  return latest;
}

export function brokerBody(template, moduleName, fields) {
  const reqObj = {
    StateName: template.stateName,
    ModuleName: moduleName,
    SessionHeader: template.sessionHeader,
    ...fields,
    AccountIndex: template.accountIndex,
  };
  return JSON.stringify({ moduleName, reqObj: JSON.stringify(reqObj), version: template.version });
}

// How the card module says a card or bill has no charges (the site itself just shows nothing)
const NO_DATA = /no data/i;

export function parseBrokerReply(moduleName, text) {
  const data = JSON.parse(JSON.parse(text).jsonResp);
  if (data.SOStatus?.Status === false) {
    const messages = (data.SOStatus.SOStatusItem ?? []).map((item) => item.Message).join('; ');
    const err = new Error(`${moduleName} was refused${messages ? `: ${messages}` : ''}`);
    err.noData = NO_DATA.test(messages);
    throw err;
  }
  return data;
}

// A bill with no charges (or a blocked card) is refused rather than answered empty
async function chargesOrNothing(call, fields) {
  try {
    return await call(CARD_MODULE, fields);
  } catch (err) {
    if (err.noData) return { Activity: null };
    throw err;
  }
}

async function callBroker(page, template, moduleName, fields) {
  if (!template.sessionHeader) throw new Error('no Leumi session header was seen');
  const [status, text] = await page.evaluate(
    async (url, body, headers) => {
      const response = await fetch(url, { method: 'POST', body, headers, credentials: 'include' });
      return [response.status, await response.text()];
    },
    `${BROKER_URL}?moduleName=${moduleName}`,
    brokerBody(template, moduleName, fields),
    template.headers,
  );
  if (status !== 200) throw new Error(`${moduleName} returned ${status}`);
  return parseBrokerReply(moduleName, text);
}

export function parseInstallments(text) {
  const match = /(\d+)\s*מ(?:תוך|-)?\s*(\d+)/.exec(text ?? '');
  if (!match) return undefined;
  const [number, total] = [Number(match[1]), Number(match[2])];
  return number >= 1 && number <= total ? { number, total } : undefined;
}

// Same day of the month, `months` later, in Israel time (clamped to the month's last day)
export function shiftMonths(iso, months) {
  const [y, m, d] = new Intl.DateTimeFormat('en-CA', { timeZone: TZ }).format(new Date(iso)).split('-').map(Number);
  const lastDay = new Date(Date.UTC(y, m - 1 + months + 1, 0)).getUTCDate();
  return `${new Date(Date.UTC(y, m - 1 + months, Math.min(d, lastDay))).toISOString().slice(0, 10)}T00:00:00`;
}

export function chargeFromItem(item, cycleDate) {
  const installments = parseInstallments(item.DealDescription);
  const charged = item.NextPaymentAmountDoubleSpecified === false ? item.AmountDouble : item.NextPaymentAmountDouble ?? item.AmountDouble;
  let date = item.DateDealUTC;
  if (installments) {
    // Like israeli-bank-scrapers: installment N is dated N-1 months after the purchase
    date = shiftMonths(item.DateDealUTC, installments.number - 1);
  } else if (charged !== item.AmountDouble) {
    // A partial charge without installment text: date it by its bill so it lands in the month paid
    date = item.DebitCardDebitPeriodUTC ?? date;
  }
  return {
    type: installments ? 'installments' : 'normal',
    // The same purchase shows up in every bill that charges part of it
    identifier: `${item.CardTransactionId}@${cycleDate.slice(0, 10)}`,
    date,
    processedDate: item.DebitCardDebitPeriodUTC,
    originalAmount: -item.AmountDouble,
    originalCurrency: 'ILS',
    chargedAmount: -charged,
    chargedCurrency: 'ILS',
    description: (item.DebitCardFirmName ?? '').trim(),
    memo: item.DealDescription?.trim() || undefined,
    installments,
    status: 'completed',
  };
}

export function pendingFromItem(item) {
  return {
    type: 'normal',
    identifier: item.CreditTransactionIdStr,
    date: item.DateDealUTC,
    originalAmount: -item.AmountDouble,
    originalCurrency: 'ILS',
    chargedAmount: -item.AmountDouble,
    description: (item.DebitCardFirmName ?? '').trim(),
    memo: item.MCC4Description?.trim() || undefined,
    status: 'pending',
  };
}

// Bills (newest first on the site) whose payment date is on or after the start date
export function cyclesSince(debitMonthItems, startDate) {
  const start = startDate.toISOString().slice(0, 10);
  return debitMonthItems.filter((cycle) => cycle.CycleDate && cycle.CycleDate.slice(0, 10) >= start);
}

export async function fetchCardAccounts(call, startDate, log = console) {
  const { CreditCardsItems } = await call(CARDS_MODULE, {});
  const accounts = [];
  for (const card of CreditCardsItems ?? []) {
    const base = { AccountIndexSpecified: true, CardIndex: card.CardIndex, OperationSpecified: true };
    const { Graph } = await call(CARD_MODULE, { ...base, Operation: OPERATION_MONTHS });
    const txns = [];
    const pending = new Map();
    let foreignSkipped = 0;
    for (const cycle of cyclesSince(Graph?.DebitMonthItems ?? [], startDate)) {
      const { Activity } = await chargesOrNothing(call, {
        ...base,
        Operation: OPERATION_CHARGES,
        CardPeriodType: cycle.DefaultMonth ? PERIOD_CURRENT : PERIOD_BY_DATE,
        CardPeriodTypeSpecified: true,
        CycleDate: cycle.CycleDate,
      });
      for (const table of Activity?.TabNisTransactionItems ?? []) {
        txns.push(...(table.NisTransactionItems ?? []).map((item) => chargeFromItem(item, cycle.CycleDate)));
      }
      for (const table of Activity?.TabForeignTransactionItems ?? []) {
        foreignSkipped += Object.values(table).filter(Array.isArray).reduce((sum, items) => sum + items.length, 0);
      }
      for (const item of Activity?.RealTimeTransItems ?? []) pending.set(item.CreditTransactionIdStr, pendingFromItem(item));
    }
    if (foreignSkipped > 0) {
      // No capture has shown this table's fields yet, so its charges are not guessed at
      log.warn(`[${CARDS_COMPANY}] card ${card.CardLast4Digits}: ${foreignSkipped} foreign-currency charges skipped`);
    }
    accounts.push({ accountNumber: card.CardLast4Digits, txns: [...txns, ...pending.values()] });
  }
  return accounts;
}

// The regular Leumi scraper, plus the cards' charges in `result.cards`
export class LeumiWithCardsScraper extends LeumiScraper {
  constructor(options, log = console) {
    super(options);
    this.log = log;
  }

  async fetchData() {
    const template = watchBrokerRequests(this.page);
    const result = await super.fetchData();
    if (!result.success) return result;
    try {
      const call = (moduleName, fields) => callBroker(this.page, template, moduleName, fields);
      const accounts = await fetchCardAccounts(call, this.options.startDate, this.log);
      // No cards on this login: nothing to record under leumiCards
      return accounts.length > 0 ? { ...result, cards: { success: true, accounts } } : result;
    } catch (err) {
      // The checking account is already in hand; a card failure is reported on its own
      return { ...result, cards: { success: false, errorType: 'GENERIC', errorMessage: err.message } };
    }
  }
}
