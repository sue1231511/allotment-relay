import { state } from "../store.js?v=island-portchat1";
import { esc, toast } from "./modal.js?v=island-portchat1";
import { cropArt } from "./crops.js?v=island-portchat1";
import { popIn, popOut } from "./pop.js?v=island-portchat1";

const PAGE = 20;
const CROP_KEYS = new Set([
  "kale", "garlic", "lemongrass", "chili", "sweetpotato", "ginger",
  "kelp", "fogpea", "beet", "rye", "cotton", "hemp",
  "bramble", "blueberry", "pineapple",
  "lime", "orange", "papaya", "banana", "mango",
  "coconut", "durian",
]);

export function renderBag(sheet, { onEat, onVend, onClose } = {}) {
  const stock = expandStacks((state.me && state.me.stock) || []);
  const pages = Math.max(1, Math.ceil(stock.length / PAGE) || 1);
  if (state.bagPage >= pages) state.bagPage = pages - 1;
  if (state.bagPage < 0) state.bagPage = 0;
  const start = state.bagPage * PAGE;
  const pageItems = stock.slice(start, start + PAGE);
  const slots = Array.from({ length: PAGE }, (_, i) => pageItems[i] || null);
  const multi = pages > 1;

  const already = sheet.classList.contains("is-bag") && !sheet.hidden;
  sheet.classList.add("is-bag");
  document.body.classList.add("is-bag-open");
  sheet.innerHTML = `
    <section class="island-bag" role="dialog" aria-label="背包" style="background-image:url('/static/island/assets/bag-frame.png')">
      <button type="button" class="island-bag-x" data-close aria-label="关闭"></button>
      <div class="island-bag-grid" id="island-bag-grid">
        ${slots.map((it, i) => slotMarkup(it, start + i)).join("")}
      </div>
      <div class="island-bag-pager">
        <button type="button" class="island-bag-turn" data-page="-1" ${!multi || state.bagPage <= 0 ? "disabled" : ""} aria-label="上一页">‹</button>
        <p class="island-bag-count">${pageItems.length} / ${PAGE}</p>
        <button type="button" class="island-bag-turn" data-page="1" ${!multi || state.bagPage >= pages - 1 ? "disabled" : ""} aria-label="下一页">›</button>
      </div>
      <button type="button" class="island-bag-done" data-close aria-label="关闭"></button>
      <div class="island-bag-pop" id="island-bag-pop" hidden></div>
    </section>
  `;
  if (already) {
    sheet.hidden = false;
  } else {
    popIn(sheet);
  }

  sheet.querySelectorAll("[data-close]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      closeBag(sheet, onClose);
    });
  });
  sheet.querySelectorAll("[data-page]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      turnPage(Number(btn.getAttribute("data-page")) || 0, sheet, { onEat, onVend, onClose });
    });
  });
  sheet.querySelectorAll("[data-slot]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      const name = btn.getAttribute("data-slot");
      const row = stock.find((it) => (it.name || it.item) === name);
      if (row) tapSlot(sheet, row, { onEat, onVend });
    });
  });
  sheet.addEventListener("click", (ev) => {
    if (ev.target === sheet) closeBag(sheet, onClose);
  }, { once: true });
  bindSwipe(sheet.querySelector("#island-bag-grid"), {
    onLeft: () => turnPage(1, sheet, { onEat, onVend, onClose }),
    onRight: () => turnPage(-1, sheet, { onEat, onVend, onClose }),
  });
}

/** MC 式：总量按 stack_cap 拆成多格，例如 84@64 → 两格 64 与 20。 */
function expandStacks(stock) {
  const out = [];
  for (const it of stock || []) {
    const total = Math.max(0, Number(it.qty) || 0);
    if (total <= 0) continue;
    const cap = Math.max(1, Number(it.stack_cap) || 64);
    let left = total;
    while (left > 0) {
      const n = Math.min(cap, left);
      out.push({ ...it, qty: n, stack_total: total });
      left -= n;
    }
  }
  return out;
}

function closeBag(sheet, onClose) {
  if (onClose) {
    onClose();
    return;
  }
  popOut(sheet, () => {
    sheet.classList.remove("is-bag");
    document.body.classList.remove("is-bag-open");
    sheet.innerHTML = "";
  });
}

function turnPage(delta, sheet, handlers) {
  const stock = expandStacks((state.me && state.me.stock) || []);
  const pages = Math.max(1, Math.ceil(stock.length / PAGE) || 1);
  const next = state.bagPage + delta;
  if (next < 0 || next >= pages) return;
  state.bagPage = next;
  renderBag(sheet, handlers);
}

function tapSlot(sheet, it, { onEat, onVend }) {
  const name = it.name || it.item;
  const eat = !!it.can_eat;
  const vend = it.can_vend !== false;
  if (eat && vend) {
    showSlotPop(sheet, it, { onEat, onVend });
    return;
  }
  if (eat) {
    if (onEat) onEat(name);
    return;
  }
  if (vend) {
    if (onVend) onVend(it);
    return;
  }
  toast("这件不能从行囊吃或卖。");
}

function showSlotPop(sheet, it, { onEat, onVend }) {
  const pop = sheet.querySelector("#island-bag-pop");
  if (!pop) return;
  const name = it.name || it.item;
  const price = it.vend_price ? `${it.vend_price}票` : "";
  pop.innerHTML = `
    <p>${esc(name)} ×${esc(it.qty)}</p>
    <div class="island-bag-pop-acts">
      <button type="button" class="island-btn" data-eat="${esc(name)}">吃</button>
      <button type="button" class="island-btn primary" data-vend="${esc(name)}">卖${price ? ` ${esc(price)}` : ""}</button>
    </div>
  `;
  popIn(pop);
  pop.querySelector("[data-eat]").addEventListener("click", (ev) => {
    ev.stopPropagation();
    popOut(pop, () => { if (onEat) onEat(name); });
  });
  pop.querySelector("[data-vend]").addEventListener("click", (ev) => {
    ev.stopPropagation();
    popOut(pop, () => { if (onVend) onVend(it); });
  });
}

function slotMarkup(it, index) {
  if (!it) {
    return `<button type="button" class="island-bag-slot is-empty" tabindex="-1" aria-hidden="true"></button>`;
  }
  const name = it.name || it.item;
  const acts = [];
  if (it.can_eat) acts.push("吃");
  if (it.can_vend !== false) acts.push("卖");
  return `
    <button type="button" class="island-bag-slot" data-slot="${esc(name)}" data-index="${index}" ${it.can_eat ? `data-eat="${esc(name)}"` : ""} ${it.can_vend !== false ? `data-vend="${esc(name)}"` : ""} aria-label="${esc(name)} ×${esc(it.qty)}${acts.length ? `，${acts.join("或")}` : ""}">
      ${itemGlyph(it)}
      <span class="island-bag-qty">${esc(it.qty)}</span>
    </button>
  `;
}

function itemGlyph(it) {
  const key = String(it.item || "");
  const crop = key.replace(/^(crop_|seed_)/, "");
  if (CROP_KEYS.has(crop)) return cropArt(crop, "ripe");
  const name = String(it.name || it.item || "·");
  return `<span class="island-bag-glyph">${esc(Array.from(name)[0] || "·")}</span>`;
}

function bindSwipe(el, { onLeft, onRight }) {
  if (!el) return;
  let x0 = 0;
  el.addEventListener("touchstart", (ev) => {
    x0 = ev.changedTouches[0].clientX;
  }, { passive: true });
  el.addEventListener("touchend", (ev) => {
    const dx = ev.changedTouches[0].clientX - x0;
    if (dx > 40) onRight();
    if (dx < -40) onLeft();
  }, { passive: true });
}
