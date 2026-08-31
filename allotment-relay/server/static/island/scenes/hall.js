import { esc } from "../ui/modal.js?v=island-fix1";
import { state } from "../store.js?v=island-fix1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-stay1";

export function renderHall(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.hall || {};
  const tabs = shop.tabs || [];
  const tab = state.hallTab || (tabs[0] && tabs[0].key) || "board";
  const peek = !state.hallShelf;
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(".island-hall"),
    className: "island-shop island-bar island-hall",
    sceneId: "hall",
    tap: "点一下看看板",
    listId: "island-hall-list",
    tabAria: "剧场看台",
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
  if (name) name.textContent = shop.name || "剧场看台";
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
  const list = wrap.querySelector("#island-hall-list");
  if (!list) return;
  const keep = listTop == null ? list.scrollTop : listTop;
  list.innerHTML = tab === "work" ? workMarkup(shop) : boardMarkup(shop);
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
  const t = shop.board || {};
  return [
    sku("look", "board", { emoji: "📋", name: t.title || "今晚看板" }, t.note || t.phase || "", "看", false),
    sku("look", "affinity", { emoji: "🧡", name: "舞台好感" }, `${t.affinity ?? 0}/100 · ${t.tier || ""}`, "看", false),
  ].join("");
}

function workMarkup(shop) {
  const rows = (shop.jobs || []).map((row) => sku(
    row.id,
    row.cmd,
    { emoji: row.emoji, name: row.name },
    row.note || "",
    row.can_act ? "上" : "看",
    Boolean(row.can_act),
    row.can_act ? "is-ready" : "",
  ));
  return rows.join("") || `<p class="island-shop-empty">今晚没专场。编剧社侧厅常开。</p>`;
}
