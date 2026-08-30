export function showEvent(event) {
  if (!event) return;
  const root = document.getElementById("island-modal");
  if (!root) return;
  root.hidden = false;
  root.innerHTML = cardMarkup(`
      <h3>${esc(event.title || "岛上")}</h3>
      <p>${esc(event.narrative || "")}</p>
      <button type="button" class="island-btn primary wide" data-close-modal>收下</button>
  `);
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
  root.innerHTML = cardMarkup(`
      <h3>${esc(title)} · ${esc(crop)}</h3>
      <p>${esc(plot.detail || "选一项。")}</p>
      <div class="island-care-acts">
        ${acts.map((a) => `<button type="button" class="island-btn ${a.primary ? "primary" : ""} wide" data-care="${esc(a.id)}">${esc(a.label)}</button>`).join("")}
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care");
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

export function showExpandSheet(snap, { onConfirm, onClose } = {}) {
  const root = document.getElementById("island-modal");
  if (!root) return;
  const offer = (snap && snap.offer) || {};
  const token = offer.token || "";
  const word = (snap && snap.next_word) || "下一块";
  root.hidden = false;
  root.innerHTML = cardMarkup(`
      <h3>开垦草地</h3>
      <p>${esc(word)} ${esc(token)} · ${esc(offer.cost)} 票 · 开垦 ${esc(offer.clear_eta || "一会儿")}</p>
      <div class="island-care-acts">
        <button type="button" class="island-btn primary wide" data-act="confirm">确认开垦</button>
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care");
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelector("[data-act=confirm]").addEventListener("click", () => {
    hideModal();
    if (onConfirm) onConfirm();
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showVendSheet(item, { onConfirm, onClose } = {}) {
  const root = document.getElementById("island-modal");
  if (!root) return;
  const label = (item && (item.label || item.name || item.item)) || "这件";
  const price = item && item.vend_price != null ? item.vend_price : "—";
  root.hidden = false;
  root.innerHTML = cardMarkup(`
      <h3>卖掉</h3>
      <p>${esc(label)} · 回收 ${esc(price)} 票</p>
      <div class="island-care-acts">
        <button type="button" class="island-btn primary wide" data-act="confirm">确认卖</button>
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care");
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelector("[data-act=confirm]").addEventListener("click", () => {
    hideModal();
    if (onConfirm) onConfirm();
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showActSheet({ title, body, confirm, onConfirm, onClose } = {}) {
  const root = document.getElementById("island-modal");
  if (!root) return;
  root.hidden = false;
  root.innerHTML = cardMarkup(`
      <h3>${esc(title || "确认")}</h3>
      <p>${esc(body || "做这一下？")}</p>
      <div class="island-care-acts">
        <button type="button" class="island-btn primary wide" data-act="confirm">${esc(confirm || "确认")}</button>
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care");
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelector("[data-act=confirm]").addEventListener("click", () => {
    hideModal();
    if (onConfirm) onConfirm();
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

export function showBuySheet(item, { onConfirm, onClose } = {}) {
  const root = document.getElementById("island-modal");
  if (!root) return;
  const label = (item && (item.label || item.name)) || "这件";
  const price = item && item.price != null ? item.price : "—";
  root.hidden = false;
  root.innerHTML = cardMarkup(`
      <h3>买下来</h3>
      <p>${esc(label)} · ${esc(price)} 票</p>
      <div class="island-care-acts">
        <button type="button" class="island-btn primary wide" data-act="confirm">确认买</button>
      </div>
      <button type="button" class="island-btn wide" data-close-modal>先不忙</button>
  `, "island-care");
  const close = () => {
    hideModal();
    if (onClose) onClose();
  };
  root.querySelector("[data-close-modal]").addEventListener("click", close);
  root.querySelector("[data-act=confirm]").addEventListener("click", () => {
    hideModal();
    if (onConfirm) onConfirm();
  });
  root.addEventListener("click", (ev) => {
    if (ev.target === root) close();
  }, { once: true });
}

function cardMarkup(inner, extraClass) {
  const cls = extraClass ? `island-card ${extraClass}` : "island-card";
  return `<article class="${cls}" role="dialog">
    <div class="island-card-inner">${inner}</div>
  </article>`;
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
