import assert from 'node:assert/strict';
import { test } from 'node:test';
import { onRequest } from './functions/api/community.js';

const stableHost = 'hyrule-atlas.pages.dev';

test('the stable project alias can only check the binding without a user session', async () => {
  const sent = [];
  const env = {
    PAGES_PROJECT_HOST: stableHost,
    COMMUNITY: { async fetch(req) {
      sent.push(req);
      return Response.json({ configured: true, user: { id: 'fixture' }, turnstileSiteKey: 'fixture' },
        { headers: { 'Set-Cookie': 'fixture=test' } });
    } },
  };
  for (const [method, suffix, allowed] of [
    ['GET', '?op=status', true], ['HEAD', '?op=status', true],
    ['POST', '?op=status', false], ['GET', '?op=status&op=contact', false],
    ['GET', '?op=newsletter-confirm', false], ['GET', '?op=gallery', false],
  ]) {
    const request = new Request(`https://${stableHost}/api/community${suffix}`, {
      method, headers: { Cookie: 'member=private', Authorization: 'Bearer fixture' },
    });
    const response = await onRequest({ request, env });
    assert.equal(response.status, allowed ? 200 : 503);
    assert.equal(response.headers.has('set-cookie'), false);
    assert.equal(response.headers.get('X-Hyrule-Community'), allowed ? 'reached' : null);
    if (allowed && method === 'GET') assert.deepEqual(await response.json(), { configured: true });
    if (allowed && method === 'HEAD') assert.equal(await response.text(), '');
  }
  const preview = new Request(`https://candidate.${stableHost}/api/community?op=status`);
  for (const bindings of [env, {}]) {
    const response = await onRequest({ request: preview, env: bindings });
    assert.equal(response.status, 503);
    assert.equal(response.headers.has('X-Hyrule-Community'), false);
  }
  assert.equal(sent.length, 2);
  for (const req of sent) {
    assert.equal(req.url, 'https://hyruleatlas.com/api/community?op=status');
    assert.equal(req.method, 'GET');
    assert.equal([...req.headers].length, 0);
  }
});

test('the stable alias distinguishes a reachable unconfigured Worker from a broken binding', async () => {
  for (const method of ['GET', 'HEAD']) {
    const request = new Request(`https://${stableHost}/api/community?op=status`, { method });
    const respond = async fetch => onRequest({ request, env: { PAGES_PROJECT_HOST: stableHost, COMMUNITY: { fetch } } });
    for (const status of [200, 503]) {
      const reachable = await respond(async () => Response.json({ configured: false, user: 'ignored' }, { status }));
      assert.equal(reachable.status, 503);
      assert.equal(reachable.headers.get('X-Hyrule-Community'), 'reached');
      assert.equal(await reachable.text(), method === 'HEAD' ? '' : '{"configured":false}');
    }
    for (const makeResponse of [
      () => { throw new Error('binding unavailable'); },
      () => new Response('invalid JSON'),
      () => Response.json({ configured: 'false' }),
      () => Response.json(null),
      () => Response.json({ error: 'bad gateway' }, { status: 502 }),
    ]) {
      const failed = await respond(makeResponse);
      assert.equal(failed.status, 503);
      assert.equal(failed.headers.has('X-Hyrule-Community'), false);
    }
  }
});

test('the production binding passes the request, session cookies and API headers through', async () => {
  const request = new Request('https://hyruleatlas.com/api/community?op=contact', {
    method: 'POST', body: 'fixture', headers: { Cookie: 'session=fixture' },
  });
  const env = { COMMUNITY: { async fetch(req) {
    assert.equal(req, request);
    assert.equal(await req.text(), 'fixture');
    return new Response('ok', { headers: [
      ['Set-Cookie', 'a=1'], ['Set-Cookie', 'b=2'], ['Referrer-Policy', 'strict-origin'],
    ] });
  } } };
  const response = await onRequest({ request, env });
  assert.deepEqual(response.headers.getSetCookie(), ['a=1', 'b=2']);
  assert.equal(response.headers.get('referrer-policy'), 'strict-origin');
  assert.equal(response.headers.get('x-content-type-options'), 'nosniff');
});
