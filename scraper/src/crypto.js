// AES-256-GCM for the accounts file, so bank logins are not stored as plain text on disk.
import { createCipheriv, createDecipheriv, randomBytes } from 'node:crypto';

export function newKey() {
  return randomBytes(32).toString('base64');
}

function keyBytes(keyBase64) {
  const key = Buffer.from(keyBase64 ?? '', 'base64');
  if (key.length !== 32) throw new Error('SCRAPER_ACCOUNTS_KEY must be 32 bytes, base64-encoded');
  return key;
}

export function encrypt(plaintext, keyBase64) {
  const iv = randomBytes(12);
  const cipher = createCipheriv('aes-256-gcm', keyBytes(keyBase64), iv);
  const data = Buffer.concat([cipher.update(plaintext, 'utf8'), cipher.final()]);
  return JSON.stringify({
    v: 1,
    iv: iv.toString('base64'),
    tag: cipher.getAuthTag().toString('base64'),
    data: data.toString('base64'),
  });
}

export function decrypt(sealed, keyBase64) {
  let box;
  try {
    box = JSON.parse(sealed);
  } catch {
    throw new Error('The encrypted accounts file is damaged');
  }
  const decipher = createDecipheriv('aes-256-gcm', keyBytes(keyBase64), Buffer.from(box.iv, 'base64'));
  decipher.setAuthTag(Buffer.from(box.tag, 'base64'));
  try {
    return Buffer.concat([decipher.update(Buffer.from(box.data, 'base64')), decipher.final()]).toString('utf8');
  } catch {
    throw new Error('Cannot decrypt the accounts file: wrong SCRAPER_ACCOUNTS_KEY?');
  }
}
