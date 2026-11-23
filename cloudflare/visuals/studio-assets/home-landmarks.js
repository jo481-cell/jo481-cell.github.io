const placeKeys = ["castle", "village", "lake"];
const mapHref = "/series/a-link-to-the-past/#collectible-map";

function currentCopy() {
  const language = document.documentElement.lang.split("-")[0];
  return copy[language] ?? copy.en;
}

export function renderStudioLandmarks(jsx, jsxs, useState) {
  const [selected, selectPlace] = useState(0);
  const words = currentCopy();

  return jsxs("figure", {
    className: "field-chart studio-landmarks",
    children: [
      jsx("div", {
        className: "studio-landmarks__view",
        children: jsx("img", {
          ...images[placeKeys[selected]],
          alt: words.alt[selected],
          loading: "lazy",
          decoding: "async",
        }),
      }),
      jsxs("figcaption", {
        className: "studio-landmarks__controls",
        children: [
          jsx("div", {
            className: "field-chart__places",
            role: "group",
            "aria-label": words.choose,
            children: words.places.map((label, index) => jsx("button", {
              type: "button",
              "aria-pressed": selected === index,
              onClick: () => selectPlace(index),
              children: label,
            }, placeKeys[index])),
          }),
          jsx("a", { className: "studio-landmarks__map", href: mapHref, children: words.map }),
        ],
      }),
    ],
  });
}

export function renderStudioCompass(jsx, jsxs) {
  const words = currentCopy();
  return jsxs("div", {
    className: "atlas-triforce-stage studio-compass",
    children: [
      jsx("img", {
        className: "studio-compass__photo",
        ...images.compass,
        alt: words.compass,
        loading: "lazy",
        decoding: "async",
      }),
      jsx("a", {
        className: "studio-compass__credit",
        href: "/sources/#record-6",
        children: words.credit,
      }),
    ],
  });
}
