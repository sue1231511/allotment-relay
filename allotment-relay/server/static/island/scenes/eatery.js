import { esc } from "../ui/modal.js?v=island-plazaclinic1";
import { state } from "../store.js?v=island-plazaclinic1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-plazaclinic1";

export function renderEatery(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.eatery || {};
  const tabs = shop.tabs || [];
  const tab = state.eateryTab || (tabs[0] && tabs[0].key) || "board";
  const peek = !state.eateryShelf;
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(".island-eatery"),
    className: "island-shop island-eatery",
    sceneId: "eatery",
    tap: "点一下看菜单",
    listId: "island-eatery-list",
    tabAria: "小馆",
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
  if (name) name.textContent = shop.name || "岸畔小馆";
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
  const list = wrap.querySelector("#island-eatery-list");
  if (!list) return;
  const keep = listTop == null ? list.scrollTop : listTop;
  list.innerHTML = tab === "mine" ? mineMarkup(shop) : boardMarkup(shop);
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

function boardMarkup(shop) {
  const rows = (shop.dishes || []).map((row) => sku(
    row.can_dine ? "dine" : "look",
        `${row.shop}|${row.id}`,
    { emoji: row.emoji, name: row.name },
    row.note || "",
    row.can_dine ? "吃" : "看",
    Boolean(row.can_dine),
    row.can_dine ? "is-ready" : "",
  ));
  return rows.join("") || `<p class="island-shop-empty">还没人开张。有小屋和冰箱就能在「我的馆」开张。</p>`;
}

function mineMarkup(shop) {
  const mine = shop.mine || {};
  const rows = [];
  if (!mine.open) {
    rows.push(sku(
      mine.can_open ? "open" : "look",
      "",
      { emoji: "🏠", name: "开馆" },
      mine.open_note || "",
      mine.can_open ? "开" : "看",
      Boolean(mine.can_open),
      mine.can_open ? "is-ready" : "",
    ));
    return rows.join("");
  }
  (mine.menu || []).forEach((row) => {
    rows.push(sku(
      "unstock",
      String(row.id),
      { emoji: row.emoji, name: row.name },
      row.note || "",
      "撤",
      Boolean(row.can_unstock),
    ));
  });
  (mine.stock || []).forEach((row) => {
    rows.push(sku(
      row.can_stock ? "stock" : "look",
      row.item,
      { emoji: row.emoji, name: row.name },
      row.note || "",
      row.can_stock ? "上架" : "看",
      Boolean(row.can_stock),
    ));
  });
  if (mine.can_sell) {
    rows.push(sku(
      "sell",
      "确认",
      { emoji: "📦", name: "卖掉小馆" },
      mine.sell_note || "",
      `收 ${mine.sell_refund || 0}`,
      true,
    ));
  }
  if (!(mine.menu || []).length && !(mine.stock || []).length) {
    rows.unshift(`<p class="island-shop-empty">菜单空着。行囊有熟菜就能上架。</p>`);
  }
  return rows.join("");
}
