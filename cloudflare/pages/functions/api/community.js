import securityHeaders from '../../security-headers.json' with { type: 'json' };

const canonical = 'hyruleatlas.com';
const reads = new Map([
  ['?probe=threads', { query: '?op=threads&locale=fr',
    valid: data => Array.isArray(data?.threads) && Array.isArray(data.categories) &&
      data.categories.length > 0 && data.stats !== null && typeof data.stats === 'object' }],
  ['?probe=fan-art', { query: '?op=fan-art', valid: data => Array.isArray(data?.artworks) }],
]);
const probeHeaders = { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow',
  'X-Content-Type-Options': 'nosniff' };

function unavailable() {
  return Response.json({ configured: false, turnstileSiteKey: '', user: null }, {
    status: 503,
    headers: { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow' },
  });
}

export async function onRequest({ request, env }) {
  const url = new URL(request.url);
  if (url.hostname === canonical) {
    if (!env.COMMUNITY) return unavailable();
    const upstream = await env.COMMUNITY.fetch(request);
    const response = new Response(upstream.body, upstream);
    for (const { key, value } of securityHeaders) {
      if (!response.headers.has(key)) response.headers.set(key, value);
    }
    return response;
  }

  // Exact selectors on the stable alias issue fresh anonymous GETs, never
  // forwarding caller-supplied data or relaying published community records.
  if (url.hostname !== env.PAGES_PROJECT_HOST ||
      !['GET', 'HEAD'].includes(request.method)) return unavailable();
  const read = reads.get(url.search);
  if (!read && url.search !== '?op=status') return unavailable();
  try {
    const response = await env.COMMUNITY.fetch(
      new Request('https://hyruleatlas.com/api/community' + (read?.query || '?op=status'))
    );
    if (read) {
      const available = response.ok && read.valid(await response.json());
      return new Response(null, { status: available ? 204 : 503, headers: probeHeaders });
    }
    const info = await response.json();
    if (typeof info?.configured !== 'boolean') return unavailable();
    return new Response(request.method === 'HEAD' ? null : JSON.stringify({ configured: info.configured }), {
      status: info.configured ? 200 : 503,
      headers: {
        'Content-Type': 'application/json',
        ...probeHeaders,
        'X-Hyrule-Community': 'reached',
      },
    });
  } catch {
    if (read) return new Response(null, { status: 503, headers: probeHeaders });
    return unavailable();
  }
}
