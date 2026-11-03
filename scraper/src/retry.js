// Which failed syncs the nightly run tries again.
//
// Only card companies: their sites (Isracard above all) often refuse a login at night with a
// passing error, and a later attempt gets through. Never a wrong or expired password or a
// blocked user: trying those again and again is how a site locks you out.

// Matches CARD_COMPANIES in the backend (app/labels.py)
export const CARD_COMPANIES = new Set([
  'max',
  'visaCal',
  'isracard',
  'amex',
  'beyahadBishvilha',
  'behatsdaa',
  'leumiCards',
]);

const NEVER_RETRY = new Set([
  'INVALID_PASSWORD',
  'CHANGE_PASSWORD',
  'ACCOUNT_BLOCKED',
  'TWO_FACTOR_RETRIEVER_MISSING',
]);

/** A failed result worth another attempt: a card, and not a problem with the login itself */
export function isRetryable(company, payload) {
  return !payload.success && CARD_COMPANIES.has(company) && !NEVER_RETRY.has(payload.error_type);
}
