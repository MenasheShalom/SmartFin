// The scraper's own small API, so the web app can manage bank logins without them ever being
// stored outside this container. Only the backend calls it (with INGEST_TOKEN), over the internal
// Docker network; no port is published. Nothing it returns contains a credential.
import { timingSafeEqual } from 'node:crypto';
import { createServer } from 'node:http';

import { loginFields, SUPPORTED_COMPANIES } from './config.js';
import { NotFound, publicAccount } from './store.js';

const MAX_BODY = 16 * 1024;

class HttpError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

function authorized(header, token) {
  const expected = Buffer.from(`Bearer ${token}`);
  const given = Buffer.from(header ?? '');
  return given.length === expected.length && timingSafeEqual(given, expected);
}

async function readJson(request) {
  let size = 0;
  const chunks = [];
  for await (const chunk of request) {
    size += chunk.length;
    if (size > MAX_BODY) throw new HttpError(413, 'Body too large');
    chunks.push(chunk);
  }
  try {
    return JSON.parse(Buffer.concat(chunks).toString('utf8') || '{}');
  } catch {
    throw new HttpError(400, 'Body is not valid JSON');
  }
}

export function createApi({ store, queue, token, log = console }) {
  const view = (account) => ({
    ...publicAccount(account),
    sync: queue.state(account.id),
    last_sync: queue.results.get(account.id) ?? null,
  });

  async function route(method, path, request) {
    if (method === 'GET' && path === '/companies') {
      return [200, SUPPORTED_COMPANIES.map((id) => ({ id, login_fields: loginFields(id) }))];
    }
    if (method === 'GET' && path === '/accounts') {
      return [200, (await store.list()).map(view)];
    }
    if (method === 'POST' && path === '/accounts') {
      const { company, credentials } = await readJson(request);
      const account = await store.add({ company, credentials });
      log.log(`[${account.company}] login added from the web app; syncing it now`);
      queue.enqueue([account.id], { firstSync: true });
      return [201, view(account)];
    }
    if (method === 'POST' && path === '/sync') {
      await queue.enqueueAll();
      return [202, (await store.list()).map(view)];
    }
    const match = /^\/accounts\/([\w-]+)(\/sync)?$/.exec(path);
    if (match) {
      const [, id, sync] = match;
      if (method === 'POST' && sync) {
        await store.get(id);
        queue.enqueue([id]);
        return [202, view(await store.get(id))];
      }
      if (method === 'PUT' && !sync) {
        const { credentials } = await readJson(request);
        const account = await store.update(id, credentials);
        log.log(`[${account.company}] login updated from the web app; syncing it now`);
        queue.results.delete(id);
        queue.enqueue([id]);
        return [200, view(account)];
      }
      if (method === 'DELETE' && !sync) {
        await store.remove(id);
        queue.forget(id);
        return [204, null];
      }
    }
    throw new HttpError(404, 'Not found');
  }

  return createServer(async (request, response) => {
    let status;
    let body;
    try {
      if (!authorized(request.headers.authorization, token)) throw new HttpError(401, 'Unauthorized');
      const { pathname } = new URL(request.url, 'http://scraper');
      [status, body] = await route(request.method, pathname, request);
    } catch (err) {
      if (err instanceof HttpError) [status, body] = [err.status, { detail: err.message }];
      else if (err instanceof NotFound) [status, body] = [404, { detail: err.message }];
      // validateAccount's messages name the problem, never a credential's value
      else if (/must be|is missing credentials/.test(err.message)) [status, body] = [422, { detail: err.message }];
      else {
        log.error(`API error: ${err.message}`);
        [status, body] = [500, { detail: 'Internal error' }];
      }
    }
    if (body === null) {
      response.writeHead(status).end();
    } else {
      response.writeHead(status, { 'Content-Type': 'application/json' }).end(JSON.stringify(body));
    }
  });
}
