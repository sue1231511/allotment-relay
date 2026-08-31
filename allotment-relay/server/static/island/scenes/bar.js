import { esc } from "../ui/modal.js?v=island-lilistall1";
import { state } from "../store.js?v=island-lilistall1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-lilistall1";

export function renderBar(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.bar || {};
  const tabs = shop.tabs || [];
  const tab = state.barTab || (tabs[0] && tabs[0].key) || "work";
  const peek = !state.barShelf;
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(".island-bar"),
    className: "island-shop island-bar",
    sceneId: "bar",
    tap: "点一下看吧台",
    listId: "island-bar-list",
    tabAria: "酒吧",
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
  if (name) name.textContent = shop.name || "潮汐酒吧";
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
  const list = wrap.querySelector("#island-bar-list");
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

function listMarkup(shop, tab) {
  if (tab === "menu") return menuMarkup(shop);
  if (tab === "tonight") return tonightMarkup(shop);
  return workMarkup(shop);
}

function sku(kind, target, title, note, price, on, extra = "") {
  return `<button type="button" class="island-shop-sku ${on ? "" : "is-off"} ${extra}" data-act="${esc(kind)}" data-target="${esc(target)}">
    <span class="island-shop-emoji">${esc(title.emoji || "·")}</span>
    <span class="island-shop-name"><b>${esc(title.name)}</b><small>${esc(note)}</small></span>
    <span class="island-shop-price">${esc(price)}</span>
  </button>`;
}

function workMarkup(shop) {
  const rows = (shop.jobs || []).map((row) => sku(
    "work",
    row.cmd,
    { emoji: row.emoji, name: row.name },
    row.note || "",
    row.can_work ? "上工" : "看",
    Boolean(row.can_work),
    row.cmd === "洗碗" && row.can_work ? "is-ready" : "",
  ));
  return rows.join("") || `<p class="island-shop-empty">这会儿没班可上。洗碗暮/夜就能打卡。</p>`;
}

function menuMarkup(shop) {
  const rows = (shop.drinks || []).map((row) => sku(
    "order",
    row.name,
    { emoji: row.emoji, name: row.name },
    row.note || "",
    row.can_order ? `${row.price} 票` : "看",
    Boolean(row.can_order),
  ));
  return rows.join("") || `<p class="island-shop-empty">酒单这会儿空着。</p>`;
}

function tonightMarkup(shop) {
  const t = shop.tonight || {};
  const rows = [
    sku("look", "singer", { emoji: "🎤", name: t.singer || "驻唱" }, t.singer_line || `歌单 ${t.songs || 0} 首`, "看", false),
    sku("look", "special", { emoji: "✨", name: "今日特调" }, t.special || "—", "看", false),
    sku("look", "activity", { emoji: "🌙", name: t.activity || "今晚" }, t.activity_desc || t.mood || "", "看", false),
    sku(
      "cheer",
      "",
      { emoji: "💬", name: "哄荔栀" },
      t.cheer_note || "",
      t.can_cheer ? "哄" : "看",
      Boolean(t.can_cheer),
      t.can_cheer ? "is-ready" : "",
    ),
  ];
  return rows.join("");
}
