import assert from 'node:assert/strict';

const origin = new URL(process.argv[2] ?? 'https://hyruleatlas.com');
const local = ['localhost', '127.0.0.1', '[::1]'].includes(origin.hostname);
if ((origin.protocol !== 'https:' && !(local && origin.protocol === 'http:')) ||
    origin.username || origin.password || origin.search || origin.hash || origin.pathname !== '/') {
  throw new Error('Provide a bare HTTPS origin or a local HTTP origin.');
}

// All checks use anonymous GET requests. Production currently normalizes the
// trailing slash. Only follow that same-origin redirect with its query intact.
// Public forum data can include author names; do not log or retain response bodies.
const checks = [
  {
    name: 'anonymous service configuration',
    query: { op: 'status' },
    status: 200,
    verify(data) {
      assert.equal(data.configured, true, 'database, mail and bot protection must be configured');
      assert.equal(data.user, null, 'anonymous session required');
      assert.ok(typeof data.turnstileSiteKey === 'string' && data.turnstileSiteKey.length > 0,
        'missing public widget key');
    },
  },
  {
    name: 'public French forum',
    query: { op: 'threads', locale: 'fr' },
    status: 200,
    verify(data) {
      assert.ok(Array.isArray(data.threads), 'missing threads list');
      assert.ok(Array.isArray(data.categories) && data.categories.length > 0, 'missing categories');
      assert.ok(data.stats !== null && typeof data.stats === 'object', 'missing public statistics');
    },
  },
  {
    name: 'public fan-art gallery',
    query: { op: 'fan-art' },
    status: 200,
    verify(data) {
      assert.ok(Array.isArray(data.artworks), 'missing artwork list');
    },
  },
  {
    name: 'anonymous access to moderation',
    query: { op: 'admin-queue' },
    status: 401,
    verify(data) {
      assert.ok(typeof data.error === 'string', 'missing authentication response');
    },
  },
];

for (const check of checks) {
  const url = new URL('/api/community', origin);
  url.search = new URLSearchParams(check.query);
  try {
    const options = {
      redirect: 'manual',
      headers: { Accept: 'application/json', 'User-Agent': 'HyruleAtlas-ReadOnly-Check/1.0' },
      signal: AbortSignal.timeout(25000),
    };
    let response = await fetch(url, options);
    if ([307, 308].includes(response.status)) {
      const canonical = new URL(response.headers.get('Location') ?? '', url);
      const expected = new URL(url);
      expected.pathname += '/';
      assert.ok(canonical.href === expected.href, 'unexpected redirect target or query');
      response = await fetch(canonical, options);
    }
    assert.equal(response.status, check.status, 'unexpected HTTP status ' + response.status);
    assert.match(response.headers.get('Content-Type') ?? '', /application\/json/i, 'JSON required');
    assert.match(response.headers.get('Cache-Control') ?? '', /\bno-store\b/i, 'no-store required');
    assert.match(response.headers.get('X-Robots-Tag') ?? '', /\bnoindex\b/i, 'noindex required');
    const data = await response.json().catch(() => { throw new Error('invalid JSON response'); });
    check.verify(data);
    console.log('PASS', check.name);
  } catch (error) {
    // Node assertion messages can include compared values. Only print the first,
    // author-controlled line so an unexpected response cannot print user records.
    console.error('FAIL', check.name, String(error.message).split('\n')[0]);
    process.exitCode = 1;
  }
}
