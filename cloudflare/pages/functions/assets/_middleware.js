import creditSections from '../credit-sections.json' with { type: 'json' };

const languages = new Set(['en', 'fr', 'es', 'ja', 'zh']);

function readerLanguage(request, origin) {
  const referer = request.headers.get('referer');
  if (referer) {
    try {
      const page = new URL(referer);
      if (page.origin === origin) {
        const prefix = page.pathname.split('/')[1];
        return languages.has(prefix) ? prefix : 'en';
      }
    } catch {
      // Fall back to the browser's preferences when its referrer is unavailable.
    }
  }
  const preferred = (request.headers.get('accept-language') || '').toLowerCase().split(',');
  return preferred.map(value => value.trim().split(/[-;]/, 1)[0]).find(value => languages.has(value)) || 'en';
}

export function onRequestGet({ request, next }) {
  const url = new URL(request.url);
  const section = creditSections[url.pathname];
  const document = request.headers.get('sec-fetch-mode') === 'navigate' ||
    (request.headers.get('accept') || '').includes('text/html');
  if (!section || !document) return next();

  const language = readerLanguage(request, url.origin);
  const prefix = language === 'en' ? '' : `/${language}`;
  return new Response(null, {
    status: 302,
    headers: {
      Location: `${prefix}/sources/#${section}`,
      'Cache-Control': 'private, no-store',
      Vary: 'Accept, Accept-Language, Sec-Fetch-Mode, Referer',
    },
  });
}
