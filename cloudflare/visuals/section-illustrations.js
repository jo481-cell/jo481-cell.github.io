
function sectionLanguage(preferred) {
  if (languages.includes(preferred)) return preferred;

  const lang = document.documentElement.lang.split('-')[0];
  return languages.includes(lang) ? lang : 'en';
}

function imageFor(slug, preferred) {
  if (!Object.hasOwn(covers, slug)) return undefined;

  const lang = sectionLanguage(preferred);
  const row = covers[slug];
  const prefix = lang === 'en' ? '' : `/${lang}`;
  return {
    src: row.src,
    width: row.width,
    height: row.height,
    alt: row.alt[lang],
    slug,
    kind: 'artwork',
    type: 'image/webp',
    source: `${prefix}/sources/#record-3`,
    credit: credit[lang],
  };
}

export function sectionCover(path, preferred) {
  const logical = path.replace(/^\/(fr|es|ja|zh)(?=\/|$)/, '').replace(/\/+$/, '');
  return imageFor(routes[logical], preferred);
}

export function sectionDirectoryCover(section) {
  return imageFor(directory[section]);
}

export function lakeGuideCover(locale) {
  return imageFor('alttp-lake', locale);
}

export function withSectionShare(head, path) {
  const image = sectionCover(path);
  const address = host + image.src;
  const openGraph = {
    'og:image': address,
    'og:image:width': String(image.width),
    'og:image:height': String(image.height),
    'og:image:type': image.type,
    'og:image:alt': image.alt,
  };
  const twitter = { 'twitter:image': address, 'twitter:image:alt': image.alt };
  const remaining = (head.meta ?? []).filter(entry => entry && !Object.hasOwn(openGraph, entry.property) && !Object.hasOwn(twitter, entry.name));
  return {
    ...head,
    meta: [
      ...remaining,
      ...Object.entries(openGraph).map(([property, content]) => ({ property, content })),
      ...Object.entries(twitter).map(([name, content]) => ({ name, content })),
    ],
  };
}
