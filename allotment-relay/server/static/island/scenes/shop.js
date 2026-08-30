import { sceneArt } from "../ui/art.js";
import { esc } from "../ui/modal.js";
import { state } from "../store.js";

export function renderShop(root, { onBuy, onSwitchTab, onOpenShelf, onCloseShelf }) {
  const shop = state.shop || {};
  root.innerHTML = `
    <div class="island-shop${state.shopShelf ? " is-shelf" : ""}">
      <div class="island-shop-stage">${sceneArt("shop")}</div>
      ${state.shopShelf ? shelfMarkup(shop) : talkMarkup(shop)}
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
  const open = root.querySelector("[data-act=shelf]");
  if (open) open.addEventListener("click", () => onOpenShelf && onOpenShelf());
  const close = root.querySelector("[data-act=talk]");
  if (close) close.addEventListener("click", () => onCloseShelf && onCloseShelf());
  root.querySelectorAll("[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => onSwitchTab && onSwitchTab(btn.getAttribute("data-tab")));
  });
  root.querySelectorAll("[data-sku]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-sku");
      const row = (shop.items || []).find((item) => item.id === id);
      if (row && onBuy) onBuy(row);
    });
  });
}

function talkMarkup(shop) {
  return `
    <article class="island-shop-talk">
      <header>
        <b>Tt酱</b>
        <small>${esc(shop.heart_bar || "")} · ${esc(shop.zhe_label || "原价")}</small>
      </header>
      <p>你有什么心事吗</p>
      <button type="button" class="island-btn primary wide" data-act="shelf">看看货架</button>
    </article>
  `;
}

function shelfMarkup(shop) {
  const tabs = shop.tabs || [];
  const tab = state.shopTab || (tabs[0] && tabs[0].key) || "seed";
  const items = (shop.items || []).filter((row) => row.tab === tab);
  return `
    <div class="island-shop-shelf">
      <div class="island-shop-shelf-head">
        <div>
          <b>货架</b>
          <small>${esc(shop.heart_bar || "")} · ${esc(shop.zhe_label || "原价")}</small>
        </div>
        <button type="button" class="island-shop-x" data-act="talk" aria-label="收起货架">收起</button>
      </div>
      <div class="island-shop-tabs" role="tablist" aria-label="货架">
        ${tabs.map((row) => (
          `<button type="button" role="tab" class="${row.key === tab ? "is-on" : ""}" data-tab="${esc(row.key)}" aria-selected="${row.key === tab ? "true" : "false"}">${esc(row.label)}</button>`
        )).join("")}
      </div>
      <div class="island-shop-list" id="island-shop-list">
        ${items.map((row) => skuMarkup(row)).join("") || `<p class="island-shop-empty">这栏现在没货。</p>`}
      </div>
    </div>
  `;
}

function skuMarkup(row) {
  const locked = !row.can_buy;
  const note = row.note || (locked ? "现在买不了" : `${row.price} 票`);
  return `<button type="button" class="island-shop-sku ${locked ? "is-off" : ""}" data-sku="${esc(row.id)}" ${locked ? "disabled" : ""}>
    <span class="island-shop-emoji">${esc(row.emoji || "·")}</span>
    <span class="island-shop-name"><b>${esc(row.label || row.name)}</b><small>${esc(note)}</small></span>
    <span class="island-shop-price">${row.can_buy ? `${row.price} 票` : "—"}</span>
  </button>`;
}
