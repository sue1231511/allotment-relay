import { esc } from "../ui/modal.js?v=island-shore1";
import { state } from "../store.js?v=island-shore1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-shore1";

export function renderAtelier(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.atelier || {};
  const tabs = shop.tabs || [];
  const tab = state.atelierTab || (tabs[0] && tabs[0].key) || "desk";
  const peek = !state.atelierShelf;
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(".island-atelier"),
    className: "island-shop island-bar island-atelier",
    sceneId: "atelier",
    tap: "点一下看坊",
    listId: "island-atelier-list",
    tabAria: "衣泊坊",
  });
  setShopPeek(wrap, peek);
  bindShopFrame(wrap, { onOpenShelf, onCloseShelf });
  hideActionBar();
  if (peek) return;
  paintChrome(wrap, shop, tabs, tab, onSwitchTab);
  paintList(wrap, shop, tab, onAct, listTop == null ? 0 : listTop);
}

function hideActionBar() {
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
}

function paintChrome(wrap, shop, tabs, tab, onSwitchTab) {
  const name = wrap.querySelector(".island-shop-meta b");
  const note = wrap.querySelector(".island-shop-meta small");
  if (name) name.textContent = shop.name || "衣泊坊";
  if (note) note.textContent = shop.line || "";
  const tabBar = wrap.querySelector(".island-shop-tabs");
  if (tabBar) {
    tabBar.innerHTML = tabs.map((row) => (
      `<button type="button" role="tab" class="${row.key === tab ? "is-on" : ""}" data-tab="${esc(row.key)}" aria-selected="${row.key === tab ? "true" : "false"}">${esc(row.label)}${row.badge ? `<i>${esc(row.badge)}</i>` : ""}</button>`
    )).join("");
    tabBar.querySelectorAll("[data-tab]").forEach((btn) => {
      btn.addEventListener("click", () => onSwitchTab && onSwitchTab(btn.getAttribute("data-tab")));
    });
  }
}

function paintList(wrap, shop, tab, onAct, listTop) {
  const list = wrap.querySelector("#island-atelier-list");
  if (!list) return;
  const keep = listTop == null ? list.scrollTop : listTop;
  list.innerHTML = listMarkup(shop, tab);
  list.querySelectorAll("[data-act]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (onAct) onAct(btn.getAttribute("data-act"), btn.getAttribute("data-target") || "");
    });
  });
  list.scrollTop = keep;
  requestAnimationFrame(() => {
    list.scrollTop = keep;
  });
}

function sku(kind, target, title, note, price, on, extra = "") {
  return `<button type="button" class="island-shop-sku ${on ? "" : "is-off"} ${extra}" data-act="${esc(kind)}" data-target="${esc(target)}">
    <span class="island-shop-emoji">${esc(title.emoji || "·")}</span>
    <span class="island-shop-name"><b>${esc(title.name)}</b><small>${esc(note)}</small></span>
    <span class="island-shop-price">${esc(price)}</span>
  </button>`;
}

function listMarkup(shop, tab) {
  if (tab === "shop") return shopMarkup(shop);
  if (tab === "closet") return closetMarkup(shop);
  return deskMarkup(shop);
}

function deskMarkup(shop) {
  const d = shop.desk || {};
  return [
    sku("look", "job", { emoji: "🧵", name: d.job === "空闲" ? "台上空闲" : d.job }, d.take_note || "", d.can_take ? "取" : "看", Boolean(d.can_take), d.can_take ? "is-ready" : ""),
    sku("take", "", { emoji: "📦", name: "取衣" }, d.take_note || "", d.can_take ? "取" : "看", Boolean(d.can_take), d.can_take ? "is-ready" : ""),
    sku("look", "worn", { emoji: "👕", name: d.worn || "没穿" }, d.worn_note || "", d.can_remove ? "脱" : "看", Boolean(d.can_remove)),
    sku("remove", "", { emoji: "🧥", name: "脱下" }, d.worn_note || "本来就没穿。", d.can_remove ? "脱" : "看", Boolean(d.can_remove)),
    sku("visit", "", { emoji: "🪡", name: "见漾漾" }, d.yangyang || "今日首次约三成给旧衣料，不是必给。", "见", true),
  ].join("");
}

function shopMarkup(shop) {
  const rows = (shop.goods || []).map((row) => sku(
    "buy",
    row.cmd,
    { emoji: row.emoji, name: row.name },
    row.note || "",
    row.can_buy ? `${row.price} 票` : "看",
    Boolean(row.can_buy),
  ));
  return rows.join("") || `<p class="island-shop-empty">日常不卖成衣。现货只有婚服和订婚服。</p>`;
}

function closetMarkup(shop) {
  const rows = (shop.closet || []).map((row) => sku(
    "wear",
    String(row.id),
    { emoji: "👘", name: row.name },
    row.note || "",
    row.can_wear ? "穿" : "穿着",
    Boolean(row.can_wear),
  ));
  return rows.join("") || `<p class="island-shop-empty">衣橱空着。现货买婚服订婚服，短褂委托仍在上手页。</p>`;
}
