import securityHeaders from '../../security-headers.json' with { type: 'json' };

const canonical = 'hyruleatlas.com';

function unavailable() {
  return Response.json({ configured: false, turnstileSiteKey: '', user: null }, {
    status: 503,
    headers: { 'Cache-Control': 'no-store', 'X-Robots-Tag': 'noindex, nofollow' },
  });
}

export async function onRequest({ request, env }) {
  const url = new URL(request.url);
  if (!env.COMMUNITY) return unavailable();
  if (url.hostname === canonical) {
    const upstream = await env.COMMUNITY.fetch(request);
    const response = new Response(upstream.body, upstream);
    for (const { key, value } of securityHeaders) {
      if (!response.headers.has(key)) response.headers.set(key, value);
    }
    return response;
  }

  // Exercise the production binding before DNS cutover, without touching a member session.
  if (url.hostname !== env.PAGES_PROJECT_HOST ||
      !['GET', 'HEAD'].includes(request.method) ||
      url.search !== '?op=status') return unavailable();
  try {
    const response = await env.COMMUNITY.fetch(
      new Request('https://hyruleatlas.com/api/community?op=status')
    );
    const info = await response.json();
    if (typeof info?.configured !== 'boolean') return unavailable();
    return new Response(request.method === 'HEAD' ? null : JSON.stringify({ configured: info.configured }), {
      status: info.configured ? 200 : 503,
      headers: {
        'Content-Type': 'application/json',
        'Cache-Control': 'no-store',
        'X-Robots-Tag': 'noindex, nofollow',
        'X-Content-Type-Options': 'nosniff',
        'X-Hyrule-Community': 'reached',
      },
    });
  } catch {
    return unavailable();
  }
}
