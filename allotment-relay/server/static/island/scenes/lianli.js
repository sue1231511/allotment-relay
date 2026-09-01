import { esc } from "../ui/modal.js?v=island-modulefix2";
import { state } from "../store.js?v=island-modulefix2";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-modulefix2";

export function renderLianli(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.lianli || {};
  const tabs = shop.tabs || [];
  const tab = state.lianliTab || (tabs[0] && tabs[0].key) || "desk";
  const peek = !state.lianliShelf;
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(".island-lianli"),
    className: "island-shop island-lianli",
    sceneId: "lianli",
    tap: "点一下看登记处",
    listId: "island-lianli-list",
    tabAria: "连理所",
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
  if (name) name.textContent = shop.name || "连理所";
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
  const list = wrap.querySelector("#island-lianli-list");
  if (!list) return;
  const keep = listTop == null ? list.scrollTop : listTop;
  const rows = (shop.items && shop.items[tab]) || [];
  if (!rows.length) {
    list.innerHTML = `<p class="island-shop-empty">这栏空着。</p>`;
  } else {
    list.innerHTML = rows.map((row) => sku(row)).join("");
    list.querySelectorAll("[data-act]").forEach((btn) => {
      btn.addEventListener("click", () => {
        if (onAct) onAct(btn.getAttribute("data-act"), btn.getAttribute("data-target") || "", btn.getAttribute("data-id") || "");
      });
    });
  }
  list.scrollTop = keep;
  requestAnimationFrame(() => {
    list.scrollTop = keep;
  });
}

function sku(row) {
  return `<button type="button" class="island-shop-sku ${row.can ? "" : "is-off"}" data-act="${esc(row.kind)}" data-target="${esc(row.target || "")}" data-id="${esc(row.id || "")}">
    <span class="island-shop-emoji">${esc(row.emoji || "·")}</span>
    <span class="island-shop-name"><b>${esc(row.name)}</b><small>${esc(row.note || "")}</small></span>
    <span class="island-shop-price">${esc(row.price || "看")}</span>
  </button>`;
}
