import { sceneArt } from "../ui/art.js";
import { esc } from "../ui/modal.js";
import { state } from "../store.js";

export function renderShop(root, { onBuy, onSwitchTab, listTop = null } = {}) {
  const shop = state.shop || {};
  const tabs = shop.tabs || [];
  const tab = state.shopTab || (tabs[0] && tabs[0].key) || "seed";
  const items = (shop.items || []).filter((row) => row.tab === tab);
  const existing = root.querySelector(".island-shop");
  if (existing) {
    paintShopChrome(existing, shop, tabs, tab, onSwitchTab);
    paintShopList(existing, shop, items, onBuy, listTop);
    hideActionBar();
    return;
  }
  root.innerHTML = `
    <div class="island-shop">
      ${sceneArt("shop")}
      <div class="island-shop-shelf">
        <div class="island-shop-meta">
          <b>${esc(shop.name || "Tt酱杂货铺")}</b>
          <small>${esc(shop.heart_bar || "")} · ${esc(shop.zhe_label || "原价")}</small>
        </div>
        <div class="island-shop-tabs" role="tablist" aria-label="货架">
          ${tabs.map((row) => tabMarkup(row, tab)).join("")}
        </div>
        <div class="island-shop-list" id="island-shop-list"></div>
      </div>
    </div>
  `;
  hideActionBar();
  const wrap = root.querySelector(".island-shop");
  paintShopChrome(wrap, shop, tabs, tab, onSwitchTab);
  paintShopList(wrap, shop, items, onBuy, listTop == null ? 0 : listTop);
}

function hideActionBar() {
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
}

function paintShopChrome(wrap, shop, tabs, tab, onSwitchTab) {
  const name = wrap.querySelector(".island-shop-meta b");
  const note = wrap.querySelector(".island-shop-meta small");
  if (name) name.textContent = shop.name || "Tt酱杂货铺";
  if (note) note.textContent = `${shop.heart_bar || ""} · ${shop.zhe_label || "原价"}`;
  const tabBar = wrap.querySelector(".island-shop-tabs");
  if (tabBar) {
    tabBar.innerHTML = tabs.map((row) => tabMarkup(row, tab)).join("");
    tabBar.querySelectorAll("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => onSwitchTab && onSwitchTab(btn.getAttribute("data-tab")));
    });
  }
}

function paintShopList(wrap, shop, items, onBuy, listTop) {
  const list = wrap.querySelector("#island-shop-list");
  if (!list) return;
  const keep = listTop == null ? list.scrollTop : listTop;
  list.innerHTML = items.map((row) => skuMarkup(row)).join("") || `<p class="island-shop-empty">这栏现在没货。</p>`;
  list.querySelectorAll("[data-sku]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const id = btn.getAttribute("data-sku");
      const row = (shop.items || []).find((item) => item.id === id);
      if (row && onBuy) onBuy(row);
    });
  });
  list.scrollTop = keep;
  requestAnimationFrame(() => {
    list.scrollTop = keep;
  });
}

function tabMarkup(row, tab) {
  return `<button type="button" role="tab" class="${row.key === tab ? "is-on" : ""}" data-tab="${esc(row.key)}" aria-selected="${row.key === tab ? "true" : "false"}">${esc(row.label)}</button>`;
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
