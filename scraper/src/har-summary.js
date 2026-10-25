// Shrink a browser HAR capture to a shareable map of the site's JSON calls.
// Nothing personal survives: headers and cookies are dropped, every digit becomes 9 and
// every letter becomes x (Hebrew: א), so only field names and value formats remain.
//
// Usage: node src/har-summary.js capture.har [--keep-text] > summary.json
//   --keep-text  keep strings that contain no digits (merchant names, Hebrew labels)
import { readFile } from 'node:fs/promises';
import { pathToFileURL } from 'node:url';

const ARRAY_SAMPLE = 3;
const MAX_STRING = 60;
// Currency codes (ILS, USD) say what an amount means and are never personal
const CURRENCY = /^[A-Z]{3}$/;
// Endpoint names in URLs (Broker.svc, UC_SO_27_GetBusinessAccountTrx) are needed to find the calls
const URL_WORD = /^[A-Za-z][A-Za-z0-9_.-]{0,59}$/;
// Small code numbers (which list to fetch, transaction type, currency) are the same for every
// customer and are needed to make the requests; account and card numbers never match these keys
const CODE_KEY = /(Index|Operation|Type|Code|Flag|Status|Indication|^TypeOf\w+|^PaymentsNumber)$/;
const CODE_VALUE = /^-?\d{1,4}$/;
// The bank's own labels (transaction type, merchant category, installment text)
const LABEL_KEY = /(Desc|Description)$/;

function keepAsIs(key, value) {
  if (CODE_KEY.test(key) && (typeof value === 'number' || typeof value === 'string') && CODE_VALUE.test(String(value))) {
    return true;
  }
  return LABEL_KEY.test(key) && typeof value === 'string' && parseJson(value) === undefined;
}

export function maskString(value, { keepText = false } = {}) {
  if (CURRENCY.test(value)) return value;
  if (keepText && !/\d/.test(value)) return value.slice(0, MAX_STRING);
  const masked = value
    .slice(0, MAX_STRING)
    .replace(/\d/g, '9')
    .replace(/[A-Za-z]/g, 'x')
    .replace(/[֐-׿]/g, 'א');
  return value.length > MAX_STRING ? `${masked}…(${value.length} chars)` : masked;
}

function parseJson(text) {
  if (typeof text !== 'string') return undefined;
  const trimmed = text.trim();
  if (!trimmed.startsWith('{') && !trimmed.startsWith('[')) return undefined;
  try {
    return JSON.parse(trimmed);
  } catch {
    return undefined;
  }
}

export function maskValue(value, options = {}) {
  if (value === null || typeof value === 'boolean') return value;
  if (typeof value === 'number') return `num:${maskString(String(value))}`;
  if (typeof value === 'string') {
    // Leumi wraps its real answer as a JSON string inside the JSON reply
    const nested = parseJson(value);
    return nested === undefined ? maskString(value, options) : { '(json string)': maskValue(nested, options) };
  }
  if (Array.isArray(value)) {
    const sample = value.slice(0, ARRAY_SAMPLE).map((item) => maskValue(item, options));
    return value.length > ARRAY_SAMPLE ? [...sample, `…(+${value.length - ARRAY_SAMPLE} more)`] : sample;
  }
  return Object.fromEntries(
    // A key with digits in it can itself be an account or card number
    Object.entries(value).map(([key, item]) => [
      /\d{4}/.test(key) ? maskString(key) : key,
      keepAsIs(key, item) ? (typeof item === 'string' ? item.trim().slice(0, MAX_STRING) : item) : maskValue(item, options),
    ]),
  );
}

function maskUrlPart(part) {
  // Account, card and session numbers carry many digits; endpoint names carry at most a few
  return URL_WORD.test(part) && (part.match(/\d/g) ?? []).length <= 3 ? part : maskString(part);
}

export function maskUrl(raw) {
  const url = new URL(raw);
  const path = url.pathname.split('/').map((part) => maskUrlPart(decodeURIComponent(part))).join('/');
  const query = [...url.searchParams].map(([key, value]) => `${maskUrlPart(key)}=${maskUrlPart(value)}`).join('&');
  return `${url.host}${path}${query ? `?${query}` : ''}`;
}

function bodyText(content = {}) {
  if (typeof content.text !== 'string') return undefined;
  return content.encoding === 'base64' ? Buffer.from(content.text, 'base64').toString('utf8') : content.text;
}

export function summarize(har, options = {}) {
  const calls = [];
  for (const entry of har.log?.entries ?? []) {
    const response = parseJson(bodyText(entry.response?.content));
    if (response === undefined) continue; // scripts, styles, images, HTML pages
    const request = parseJson(entry.request?.postData?.text);
    calls.push({
      method: entry.request.method,
      url: maskUrl(entry.request.url),
      status: entry.response.status,
      bytes: entry.response.content?.size ?? null,
      ...(request === undefined ? {} : { request: maskValue(request, options) }),
      response: maskValue(response, options),
    });
  }
  return { calls: calls.length, entries: har.log?.entries?.length ?? 0, json: calls };
}

async function main([file, ...flags]) {
  if (!file) {
    console.error('usage: node src/har-summary.js capture.har [--keep-text] > summary.json');
    process.exit(2);
  }
  const har = JSON.parse(await readFile(file, 'utf8'));
  console.log(JSON.stringify(summarize(har, { keepText: flags.includes('--keep-text') }), null, 1));
}

if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  await main(process.argv.slice(2));
}
