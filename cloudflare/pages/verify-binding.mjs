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

test('public read probes validate each anonymous response and discard all returned records and headers', async () => {
  const cases = [
    ['threads', '?op=threads&locale=fr', { threads: [{ title: 'private fixture' }], categories: ['help'], stats: {} }],
    ['fan-art', '?op=fan-art', { artworks: [{ displayName: 'private fixture' }] }],
  ];
  for (const [probe, query, data] of cases) {
    for (const method of ['GET', 'HEAD']) {
      const request = new Request(`https://${stableHost}/api/community?probe=${probe}`, {
        method, headers: { Cookie: 'secret=fixture', Authorization: 'Bearer fixture' },
      });
      const statuses = [200, 503, 'malformed', 'throw'];
      for (const upstream of statuses) {
        let calls = 0;
        const env = { PAGES_PROJECT_HOST: stableHost, COMMUNITY: { async fetch(req) {
          calls++;
          assert.equal(req.method, 'GET');
          assert.equal(req.url, 'https://hyruleatlas.com/api/community' + query);
          assert.deepEqual([...req.headers], []);
          if (upstream === 'throw') throw new Error('fixture');
          return Response.json(upstream === 'malformed' ? {} : data, {
            status: upstream === 503 ? 503 : 200, headers: { 'Set-Cookie': 'fixture=x' },
          });
        } } };
        const response = await onRequest({ request, env });
        assert.equal(calls, 1);
        assert.equal(response.status, upstream === 200 ? 204 : 503);
        assert.equal(await response.text(), '');
        assert.equal(response.headers.has('set-cookie'), false);
        assert.equal(response.headers.get('Cache-Control'), 'no-store');
      }
    }
    let calls = 0;
    const env = { PAGES_PROJECT_HOST: stableHost, COMMUNITY: { fetch() { calls++; } } };
    for (const [host, method, queryString] of [
      [`branch.${stableHost}`, 'GET', `?probe=${probe}`],
      [stableHost, 'POST', `?probe=${probe}`], [stableHost, 'GET', `?probe=${probe}&locale=en`],
      [stableHost, 'GET', `?probe=${probe}&op=contact`], [stableHost, 'GET', query],
    ]) {
      const response = await onRequest({ request: new Request(`https://${host}/api/community${queryString}`, { method }), env });
      assert.equal(response.status, 503);
    }
    assert.equal(calls, 0);
  }
});
