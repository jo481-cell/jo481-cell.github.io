// Reuses the home page pause and range controls, without a GPU context.
export async function createTriforceScene(host, options) {
  const rose = document.createElement("img");
  rose.src = "/assets/editorial/compass.svg";
  rose.alt = "";
  rose.className = "atlas-editorial-compass";
  Object.assign(rose.style, {width:"70%",height:"70%",objectFit:"contain",position:"absolute",left:"15%",top:"15%"});
  host.replaceChildren(rose);
  const state = {
    setPaused(paused) { rose.style.transition = paused ? "none" : "transform 180ms ease-out"; },
    setIntensity(amount) { rose.style.transform = "rotate(" + (Math.max(0, Math.min(1, amount)) * 270) + "deg)"; },
    dispose() { rose.remove(); }
  };
  state.setPaused(options.paused);
  state.setIntensity(options.intensity);
  return state;
}
