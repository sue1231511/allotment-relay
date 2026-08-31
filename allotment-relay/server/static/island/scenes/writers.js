import { esc } from "../ui/modal.js?v=island-vn-meet1";
import { state } from "../store.js?v=island-vn-meet1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-vn-meet1";

export function renderWriters(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.writers || {};
  const tabs = shop.tabs || [];
  const tab = state.writersTab || (tabs[0] && tabs[0].key) || "desk";
  const peek = !state.writersShelf;
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(".island-writers"),
    className: "island-shop island-bar island-writers",
    sceneId: "writers",
    tap: "点一下看收稿台",
    listId: "island-writers-list",
    tabAria: "编剧社",
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
  if (name) name.textContent = shop.name || "编剧社";
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
  const list = wrap.querySelector("#island-writers-list");
  if (!list) return;
  const keep = listTop == null ? list.scrollTop : listTop;
  list.innerHTML = deskMarkup(shop);
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

function deskMarkup(shop) {
  const rows = [
    sku(
      "submit",
      "",
      { emoji: "✒️", name: "投稿" },
      shop.submit_note || "标题和正文用稿纸写。",
      shop.can_submit ? "投" : "看",
      Boolean(shop.can_submit),
      shop.can_submit ? "is-ready" : "",
    ),
  ];
  const scripts = shop.scripts || [];
  if (!scripts.length) {
    rows.push(`<p class="island-shop-empty">还没投过。不是接现有潮闻，稿费也不是领薪。</p>`);
    return rows.join("");
  }
  scripts.forEach((row) => {
    rows.push(sku(
      row.can_withdraw ? "withdraw" : "look",
      String(row.id),
      { emoji: "📜", name: `《${row.title}》` },
      `${row.pitch} · ${row.note || row.status}`,
      row.can_withdraw ? "撤回" : row.status,
      Boolean(row.can_withdraw),
    ));
  });
  return rows.join("");
}
