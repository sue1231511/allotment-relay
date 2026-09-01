import { esc } from "../ui/modal.js?v=island-mapbgm1";
import { state } from "../store.js?v=island-mapbgm1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-fastscenes1";

export function renderTing(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.ting || {};
  const tabs = shop.tabs || [];
  const tab = state.tingTab || (tabs[0] && tabs[0].key) || "ask";
  const peek = !state.tingShelf;
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(".island-ting"),
    className: "island-shop island-ting",
    sceneId: "ting",
    tap: "点一下看木牌",
    listId: "island-ting-list",
    tabAria: "听潮亭",
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
  if (name) name.textContent = shop.name || "听潮亭";
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
  const list = wrap.querySelector("#island-ting-list");
  if (!list) return;
  const keep = listTop == null ? list.scrollTop : listTop;
  list.innerHTML = tab === "mine" ? mineMarkup(shop) : boardMarkup(shop, tab);
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

function boardMarkup(shop, tab) {
  const board = (shop.boards && shop.boards[tab]) || {};
  const rows = board.threads || [];
  const parts = [];
  parts.push(sku(
    "post",
    tab,
    { emoji: "🪵", name: "钉一块" },
    board.hint || shop.post_note || "标题和正文分开写。",
    "钉",
    true,
  ));
  if (!rows.length) {
    parts.push(`<p class="island-shop-empty">这块还空着。先钉一块。不是聊天室，不是厅示。</p>`);
    return parts.join("");
  }
  for (const row of rows) {
    parts.push(sku(
      "look",
      String(row.id),
      { emoji: row.pinned ? "📌" : "🪵", name: row.title },
      row.note || "",
      "看",
      true,
    ));
  }
  return parts.join("");
}

function mineMarkup(shop) {
  const rows = shop.mine || [];
  const parts = [];
  if (!rows.length) {
    return `<p class="island-shop-empty">你还没钉过。切到问事、市声、闲话或寻人钉一块。</p>`;
  }
  for (const row of rows) {
    parts.push(sku(
      "look",
      String(row.id),
      { emoji: "🪵", name: row.title },
      row.note || row.board_name || "",
      "看",
      true,
    ));
    if (row.can_tear) {
      parts.push(sku(
        "tear",
        String(row.id),
        { emoji: "✂️", name: `撕《${row.title}》` },
        "撕下来整帖从墙上拿下。",
        "撕",
        true,
      ));
    }
  }
  return parts.join("");
}
