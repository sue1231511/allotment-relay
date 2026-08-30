export function showEvent(event) {
  if (!event) return;
  const root = document.getElementById("island-modal");
  if (!root) return;
  root.hidden = false;
  root.innerHTML = `
    <article class="island-card">
      <h3>${esc(event.title || "岛上")}</h3>
      <p>${esc(event.narrative || "")}</p>
      <button type="button" class="island-btn primary wide" data-close-modal>收下</button>
    </article>
  `;
  root.querySelector("[data-close-modal]").addEventListener("click", hideModal);
  root.addEventListener("click", (ev) => {
    if (ev.target === root) hideModal();
  }, { once: true });
}

export function careActs(plot) {
  const acts = [];
  if (!plot) return acts;
  if (plot.state === "growing" || plot.state === "tending") {
    if (!plot.tended) acts.push({ id: "tend", label: "打理" });
    if (!plot.watered) acts.push({ id: "water", label: "浇水" });
    if (!plot.fertilized) acts.push({ id: "fertilize", label: "施肥" });
  }
  if (plot.state === "ready") {
    acts.push({
      id: "harvest",
      label: (plot.orchard || plot.shake) ? "收果" : "收菜",
      primary: true,
    });
    if (plot.shake) acts.push({ id: "shake", label: "摇一摇" });
  }
  if (plot.state === "overripe") {
    acts.push({ id: "compost", label: "堆肥" });
    acts.push({ id: "harvest", label: "清果", primary: true });
  }
  return acts;
}

export function showCareSheet(plot, { onAct, onClose } = {}) {
  const root = document.getElementById("island-modal");
  if (!root) return;
  const acts = careActs(plot);
  const title = plot.token && /[园棚]/.test(String(plot.token))
    ? String(plot.token)
    : `#${plot.slot}`;
  const crop = plot.name || "作物";
  root.hidden = false;
  root.innerHTML = `
    <article class="island-card island-care">
      <h3>${esc(title)} · ${esc(crop)}</h3>
      <p>${esc(plot.detail || "选一项。")}</p>
      <div class="island-care-acts">
        ${acts.map((a) => `<button type="button" class="island-btn ${a.primary ? "primary" : ""} wide" data-care="${esc(a.id)}">${esc(a.label)}</button>`).join("")}
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
    </article>
  `;
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelectorAll("[data-care]").forEach((btn) => {
    btn.addEventListener("click", () => {
      hideModal();
      if (onAct) onAct(btn.getAttribute("data-care"));
    });
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function hideModal() {
  const root = document.getElementById("island-modal");
  if (!root) return;
  root.hidden = true;
  root.innerHTML = "";
}

export function toast(text) {
  if (window.__islandBoot && typeof window.__islandBoot.toast === "function") {
    window.__islandBoot.toast(text);
    return;
  }
  const el = document.getElementById("island-toast");
  if (!el) return;
  el.hidden = false;
  el.removeAttribute("hidden");
  el.textContent = text;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, 3200);
}

export function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
