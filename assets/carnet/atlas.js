(() => {
  "use strict";
  if (window.atlasCarnetInstalled) return;
  window.atlasCarnetInstalled = true;
  recoverImageLoads();

  function recoverImageLoads() {
    const states = new WeakMap();
    const delays = [500, 2000, 8000, 30000];
    let retryAt = 0;
    const visible = window.IntersectionObserver && new IntersectionObserver(entries => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        visible.unobserve(entry.target);
        retry(entry.target, states.get(entry.target));
      }
    }, {rootMargin:"240px"});

    function selected(img) {
      // Unrequested native lazy images have no currentSrc.
      if (!img.currentSrc) return "";
      const url = new URL(img.currentSrc);
      return url.origin === location.origin && url.pathname.startsWith("/assets/") ? url.href : "";
    }
    function waitFor(response) {
      const value = response.headers.get("Retry-After");
      if (!value) return 0;
      if (/^\d+$/.test(value)) return Date.now() + Number(value) * 1000;
      return Date.parse(value) || 0;
    }
    function consider(img) {
      if (!(img instanceof HTMLImageElement) || !img.isConnected || !img.complete || img.naturalWidth) return;
      const url = selected(img);
      if (!url) return;
      let state = states.get(img);
      if (!state || state.url !== url) {
        state = {url, attempts:0, pending:false};
        states.set(img,state);
      }
      if (state.pending || state.permanent || state.attempts >= delays.length) return;
      const last = performance.getEntriesByName(url).filter(entry=>entry.initiatorType==="img").pop();
      if (last?.responseStatus >= 400 && last.responseStatus < 500 && ![408,429].includes(last.responseStatus)) return;
      state.pending = true;
      if (visible && img.loading === "lazy") visible.observe(img);
      else retry(img,state);
    }
    function retry(img,state) {
      if (!state) return;
      const delay = delays[state.attempts++];
      setTimeout(async () => {
        if (!img.isConnected || selected(img) !== state.url || img.naturalWidth || !state.pending) {
          state.pending = false;
          return;
        }
        if (Date.now() < retryAt) {
          // All the failed images on this page share the server's cooldown.
          state.attempts--;
          retry(img,state);
          return;
        }
        try {
          const response = await fetch(state.url,{
            method:"HEAD",mode:"same-origin",redirect:"error",cache:"no-store",
            signal:window.AbortSignal?.timeout?.(8000)
          });
          if (response.status === 429 || response.status === 503) retryAt = Math.max(retryAt,waitFor(response));
          if (response.ok) {
            state.pending = false;
            if (!img.isConnected || selected(img) !== state.url || img.naturalWidth) return;
            // A new assignment asks the native picker to try the same source
            // again. <picture>, srcset, sizes and loading retain their meaning.
            img.setAttribute("src",img.getAttribute("src") || state.url);
            return;
          }
          if (response.status < 500 && ![408,429].includes(response.status)) {
            state.pending = false;
            state.permanent = true;
            return;
          }
        } catch { /* A broken connection can recover on the next attempt. */ }
        state.pending = false;
        consider(img);
      },Math.max(delay,retryAt - Date.now()));
    }
    function scan(resetTransient) {
      for (const img of document.images) {
        const state = states.get(img);
        if (resetTransient && state && !state.pending && !state.permanent) state.attempts = 0;
        consider(img);
      }
    }
    document.addEventListener("error",event=>consider(event.target),true);
    document.addEventListener("load",event=>{ if (event.target instanceof HTMLImageElement) states.delete(event.target); },true);
    window.addEventListener("online",()=>scan(true));
    window.addEventListener("pageshow",()=>scan(false));
    scan(false);
  }
  const words = {
    fr: ["L’ocarina bleu", "Douze trous percent la céramique. Retournez l’instrument pour trouver les deux trous de pouce, puis essayez un doigté dans l’atelier.", "Examiner en 3D", "Jouer une note", "Ocarina à douze trous", "Fermer", "Recentrer", "Tourner à gauche", "Tourner à droite", "Activer la 3D", "Ouverture…", "Revoir l’image", "Faites glisser l’ocarina ou utilisez les quatre flèches du clavier pour le tourner.", "La vue fixe du même instrument est affichée. Vous pouvez réessayer la 3D.", "Ocarina en céramique bleue, vu de trois quarts."],
    en: ["The blue ocarina", "Twelve holes pierce the ceramic shell. Turn the instrument over to find the two thumb holes, then try a fingering in the workshop.", "Examine in 3D", "Play a note", "Twelve-hole ocarina", "Close", "Reset view", "Turn left", "Turn right", "Enable 3D", "Opening…", "Show still image", "Drag the ocarina or use the four arrow keys to turn it.", "A still image of the same instrument is displayed. You can try 3D again.", "A blue ceramic ocarina seen from a three-quarter angle."],
    es: ["La ocarina azul", "Doce orificios atraviesan la cerámica. Gira el instrumento para encontrar los dos orificios de los pulgares y prueba una digitación en el taller.", "Examinar en 3D", "Tocar una nota", "Ocarina de doce orificios", "Cerrar", "Centrar", "Girar a la izquierda", "Girar a la derecha", "Activar 3D", "Abriendo…", "Ver imagen fija", "Arrastra la ocarina o usa las cuatro flechas del teclado para girarla.", "Se muestra una imagen fija del mismo instrumento. Puedes volver a probar la vista 3D.", "Ocarina de cerámica azul vista en tres cuartos."],
    ja: ["青いオカリナ", "陶器の胴には十二の穴があります。楽器を回して親指の穴を二つ見つけたら、工房で指使いを試してみましょう。", "3Dで見る", "音を鳴らす", "十二穴のオカリナ", "閉じる", "向きを戻す", "左に回す", "右に回す", "3Dを起動", "読み込み中…", "静止画を見る", "ドラッグするか、キーボードの矢印キーで楽器を回せます。", "同じ楽器の静止画を表示しています。3D表示はもう一度試せます。", "斜めから見た青い陶器のオカリナ。"],
    zh: ["蓝色陶笛", "陶质笛身上有十二个孔。转动陶笛，找到背面的两个拇指孔，再到工坊试试指法。", "查看三维模型", "演奏一个音符", "十二孔陶笛", "关闭", "恢复初始视角", "向左旋转", "向右旋转", "开启三维视图", "正在打开…", "查看静态图", "拖动陶笛或使用键盘上的四个方向键即可旋转。", "当前显示同一件乐器的静态图像。你可以重新尝试三维视图。", "从斜前方观看的蓝色陶笛。"],
  };
  const keys = ["title","description","inspect","play","object","close","reset","left","right","activate","loading","still","hint","fallback","alt"];
  const reduced = matchMedia("(prefers-reduced-motion: reduce)");
  const posterURL = "/assets/models/ocarina-12-hole-poster.webp";
  let locationKey, sheet, trigger, displayed = false, turn = 0, transition;
  let setup = Promise.resolve(), queued = false;
  const node = (tag, cls, text) => {
    const el = document.createElement(tag);
    if (cls) el.className = cls;
    if (text) el.textContent = text;
    return el;
  };
  const button = (text, cls = "") => {
    const el = node("button", cls, text);
    el.type = "button";
    return el;
  };
  function context() {
    const segments = location.pathname.split("/").filter(Boolean);
    const lang = /^(fr|es|ja|zh)$/.test(segments[0] || "") ? segments.shift() : "en";
    const route = segments.filter(s => s !== "index.html").join("/");
    return {route, prefix:lang === "en" ? "" : "/"+lang, copy:Object.fromEntries(keys.map((k,i) => [k,words[lang][i]]))};
  }
  function poster(copy) {
    const img = node("img");
    img.src = posterURL; img.alt = copy.alt; img.width = 1600; img.height = 1000; img.loading = "lazy";
    return img;
  }
  function attribution(tag) {
    const line = node(tag,"carnet-model-credit");
    const source = node("a","","RobSoundtrack");
    source.href = "https://commons.wikimedia.org/wiki/File:Updated_12_Hole_Ocarina.stl";
    const licence = node("a","","CC BY 4.0");
    licence.href = "https://creativecommons.org/licenses/by/4.0/";
    const details = node("a","","Hyrule Atlas (GLB)");
    details.href = "/assets/models/ocarina-12-hole.provenance.json";
    line.append(source," · ",licence," · ",details);
    return line;
  }
  function move(show, copy, sourceImg) {
    if (show === displayed) return;
    displayed = show;
    const currentTurn = ++turn;
    transition?.skipTransition();
    const stage = sheet.querySelector("[data-stage]");
    if (!show) sheet.dispatchEvent(new Event("relique:fermer"));
    const apply = () => {
      if (currentTurn !== turn) return;
      sourceImg?.classList.toggle("atlas-shared-object", !show);
      stage.classList.toggle("atlas-shared-object", show);
      document.body.classList.toggle("carnet-inspecting",show);
      if (show && !sheet.open) {
        sheet.showModal();
        sheet.querySelector(".carnet-close").focus({preventScroll:true});
      } else if (!show && sheet.open) {
        sheet.close();
        if (trigger?.isConnected) trigger.focus({preventScroll:true});
      }
    };
    const begin3D = async () => {
      if (!show || currentTurn !== turn || !sheet.open) return;
      try {
        await setup;
        if (currentTurn !== turn || !sheet.open) return;
        const start = sheet.querySelector("[data-activate]");
        if (!start.hidden && !start.disabled && sheet.dataset.render !== "live") start.click();
      } catch { sheet.querySelector("[data-status]").textContent = copy.fallback; }
    };
    if (!document.startViewTransition || reduced.matches) { apply(); void begin3D(); return; }
    const active = document.startViewTransition(apply);
    transition = active;
    active.ready.catch(() => {});
    active.finished.then(begin3D, () => {}).finally(() => { if (transition === active) transition = undefined; });
  }
  function createSheet(copy, sourceImg) {
    sheet = node("dialog","carnet-dialog");
    sheet.setAttribute("aria-labelledby","carnet-specimen-title");
    const top = node("div","carnet-dialog__head"), title = node("h2","",copy.object), close = button(copy.close+" ×","carnet-close");
    title.id = "carnet-specimen-title"; top.append(title,close);
    const stage = node("div"); stage.dataset.stage = "";
    const img = poster(copy); img.loading = "eager"; img.dataset.poster = "";
    const canvas = node("canvas"); canvas.dataset.canvas = ""; canvas.hidden = true; canvas.tabIndex = 0; canvas.setAttribute("aria-label", copy.hint);
    stage.append(img,canvas);
    const controls = node("div","carnet-dialog__tools"), start = button(copy.activate), orient = node("div"), status = node("p");
    start.dataset.activate = ""; start.hidden = true; orient.dataset.orbit = ""; orient.hidden = true;
    const left = button("←"), right = button("→"), reset = button(copy.reset);
    left.dataset.turn = "-1"; right.dataset.turn = "1"; reset.dataset.reset = "";
    left.setAttribute("aria-label",copy.left); right.setAttribute("aria-label",copy.right);
    orient.append(left,reset,right); status.dataset.status = ""; status.setAttribute("role","status");
    controls.append(start,orient,status); sheet.append(top,stage,controls,attribution("small")); document.body.append(sheet);
    close.addEventListener("click", () => move(false,copy,sourceImg));
    sheet.addEventListener("cancel", e => { e.preventDefault(); move(false,copy,sourceImg); });
    sheet.addEventListener("click", e => {
      if (e.target !== sheet) return;
      const box = sheet.getBoundingClientRect();
      if (e.clientX < box.left || e.clientX > box.right || e.clientY < box.top || e.clientY > box.bottom) move(false,copy,sourceImg);
    });
    const dialog = sheet;
    setup = import("/assets/carnet/instrument.js").then(module => { if (dialog.isConnected) module.connect(dialog,copy); });
    setup.catch(() => { status.textContent = copy.fallback; });
  }
  function attach() {
    const {route,prefix,copy} = context();
    const main = document.querySelector("main");
    if (!main || typeof HTMLDialogElement === "undefined" || typeof HTMLDialogElement.prototype.showModal !== "function") return;
    if (locationKey !== location.pathname) {
      if (sheet) { ++turn; sheet.dispatchEvent(new Event("relique:fermer")); sheet.remove(); sheet = undefined; displayed = false; document.body.classList.remove("carnet-inspecting"); }
      locationKey = location.pathname;
    }
    if (!["","ocarina-of-time-remake","ocarina-of-time-switch-2","ocarina"].includes(route) || main.querySelector(".carnet-open")) return;
    const slot = main.querySelector("[data-exhibit-slot][data-exhibit-ready]");
    if (document.documentElement.hasAttribute("data-exhibit-slots") && !slot) return;
    const workshop = route === "ocarina";
    const anchor = workshop ? main.querySelector(".ocarina-atelier__visual") :
      main.querySelector(".atlas-living-map,.atlas-lead") || main.firstElementChild;
    if (!anchor) return;
    const launch = button(copy.inspect+" ↗","carnet-open"); launch.setAttribute("aria-haspopup","dialog");
    let sourceImg;
    if (workshop) {
      const wrap = node("div","carnet-workshop-action"); wrap.append(launch); (slot || anchor).append(wrap);
      sourceImg = anchor.querySelector('img[src*="ocarina-12-hole-poster"]');
    } else {
      const feature = node("section","carnet-object"), text = node("div","carnet-object__text"), plate = node("figure","carnet-object__plate");
      const title = node("h2","",copy.title); title.id="carnet-object-title";feature.setAttribute("aria-labelledby",title.id);
      const play = node("a","carnet-play",copy.play+" →"); play.href = prefix+"/ocarina/";
      text.append(title,node("p","",copy.description),launch,play);
      sourceImg = poster(copy); plate.append(sourceImg,attribution("figcaption")); feature.append(text,plate);
      if (slot) slot.append(feature);
      else if (route && main.querySelector(".atlas-content")) main.querySelector(".atlas-content").append(feature);
      else anchor.after(feature);
    }
    sourceImg?.classList.add("atlas-shared-object");
    launch.addEventListener("click", () => {
      trigger = launch;
      if (!sheet) createSheet(copy,sourceImg);
      move(true,copy,sourceImg);
    });
  }
  function schedule() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => { queued = false; attach(); });
  }
  function boot() {
    schedule();
    document.addEventListener("atlas:exhibit-ready",schedule);
    window.addEventListener("pageshow",schedule);
    window.addEventListener("popstate",schedule);
    if (window.navigation) navigation.addEventListener("navigatesuccess",schedule);
    new MutationObserver(records => {
      if (locationKey !== location.pathname || records.some(r => [...r.addedNodes].some(n => n.nodeType === 1 && (n.matches("main,.atlas-frontier,.ocarina-atelier__visual") || n.querySelector("main"))))) schedule();
    }).observe(document.body,{childList:true,subtree:true});
  }
  // The published React bundle hydrates asynchronously, even after window.load.
  // Mount the exhibit only once React has claimed the server-rendered main.
  let started = false, retry;
  function onMount() {
    if (started) return;
    started = true;
    clearTimeout(retry);
    document.removeEventListener("atlas:carnet-ready",onMount);
    boot();
  }
  function checkLegacyMain() {
    if (started) return;
    const main = document.querySelector("main");
    if (main && Object.keys(main).some(key => key.startsWith("__reactProps$"))) onMount();
    else retry = setTimeout(checkLegacyMain,250);
  }
  if (document.documentElement.hasAttribute("data-exhibit-slots")) {
    if (document.body) onMount(); else document.addEventListener("DOMContentLoaded",onMount,{once:true});
  } else {
    document.addEventListener("atlas:carnet-ready",onMount,{once:true});
    if (document.readyState === "complete") checkLegacyMain();
    else window.addEventListener("load",checkLegacyMain,{once:true});
  }
})();
