function displayFontLicense(text) {
  const disclosure = text.closest('.archive-font-license');
  if (!disclosure) return;

  disclosure.open = true;
  requestAnimationFrame(() => {
    if (!disclosure.isConnected || location.hash !== `#${text.id}`) return;
    disclosure.querySelector('summary').focus({ preventScroll: true });
    disclosure.scrollIntoView({ block: 'start', behavior: 'instant' });
  });
}

function licenseForHash(hash) {
  return hash.startsWith('#font-license-') ? document.getElementById(hash.slice(1)) : null;
}

export function revealLinkedFontLicense(text) {
  if (text && location.hash === `#${text.id}`) displayFontLicense(text);
}

document.addEventListener('click', event => {
  if (event.defaultPrevented || event.button !== 0 || event.ctrlKey || event.metaKey || event.altKey || event.shiftKey) return;
  if (!(event.target instanceof Element)) return;
  const link = event.target.closest('#sources a[href^="#font-license-"]');
  if (!link) return;
  const hash = link.getAttribute('href');
  const text = licenseForHash(hash);
  if (!text) return;

  event.preventDefault();
  if (location.hash !== hash) history.pushState(history.state, '', hash);
  displayFontLicense(text);
});

window.addEventListener('hashchange', () => {
  const text = licenseForHash(location.hash);
  if (text) displayFontLicense(text);
});
