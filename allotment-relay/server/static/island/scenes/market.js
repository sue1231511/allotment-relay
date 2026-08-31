import { esc } from "../ui/modal.js?v=island-plantbag1";
import { state } from "../store.js?v=island-plantbag1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-plantbag1";

export function renderMarket(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.market || {};
  const tabs = shop.tabs || [];
  const tab = state.marketTab || (tabs[0] && tabs[0].key) || "board";
  const peek = !state.marketShelf;
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(".island-market"),
    className: "island-shop island-market",
    sceneId: "market",
    tap: "点一下看摊",
    listId: "island-market-list",
    tabAria: "集市",
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
  if (name) name.textContent = shop.name || "玩家集市";
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
  const list = wrap.querySelector("#island-market-list");
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

function sku(kind, target, title, note, price, on) {
  return `<button type="button" class="island-shop-sku ${on ? "" : "is-off"}" data-act="${esc(kind)}" data-target="${esc(target)}">
    <span class="island-shop-emoji">${esc(title.emoji || "·")}</span>
    <span class="island-shop-name"><b>${esc(title.name)}</b><small>${esc(note)}</small></span>
    <span class="island-shop-price">${esc(price)}</span>
  </button>`;
}

function boardMarkup(shop) {
  const rows = shop.listings || [];
  if (!rows.length) {
    return `<p class="island-shop-empty">街上还没人摆。切到「我的摊」挂自己的货。</p>`;
  }
  return rows.map((row) => sku(
    row.can_buy ? "buy" : "look",
    String(row.id),
    { emoji: row.emoji, name: `${row.name} ×${row.qty}` },
    row.note || "",
    row.can_buy ? `${row.cost}票` : "看",
    Boolean(row.can_buy),
  )).join("");
}

function mineMarkup(shop) {
  const mine = shop.mine || {};
  const lots = mine.listings || [];
  const goods = mine.goods || [];
  const parts = [];
  parts.push(sku(
    mine.can_expand ? "expand" : "look",
    "1",
    { emoji: "📦", name: "扩一格" },
    mine.expand_note || "",
    mine.can_expand ? `${mine.slot_cost || 15}票` : "看",
    Boolean(mine.can_expand),
  ));
  if (!lots.length) {
    parts.push(`<p class="island-shop-empty">还没挂货。点袋里的东西写数量和单价。</p>`);
  } else {
    for (const row of lots) {
      parts.push(sku(
        "cancel",
        String(row.id),
        { emoji: row.emoji, name: `${row.name} ×${row.qty}` },
        row.note || "",
        "下架",
        Boolean(row.can_cancel),
      ));
    }
  }
  if (!goods.length) {
    parts.push(`<p class="island-shop-empty">行囊里没有能上架的货。背包里能卖的才能挂。</p>`);
  } else {
    for (const row of goods) {
      parts.push(sku(
        row.can_sell ? "sell" : "look",
        row.item,
        { emoji: row.emoji, name: row.name },
        row.note || "",
        row.can_sell ? "挂" : "看",
        Boolean(row.can_sell),
      ));
    }
  }
  return parts.join("");
}
