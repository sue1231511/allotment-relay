import { esc } from "../ui/modal.js?v=island-fix1";
import { state } from "../store.js?v=island-fix1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-stay1";

export function renderQuarry(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.quarry || {};
  const tabs = shop.tabs || [];
  const tab = state.quarryTab || (tabs[0] && tabs[0].key) || "pits";
  const peek = !state.quarryShelf;
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(".island-quarry"),
    className: "island-shop island-quarry",
    sceneId: "quarry",
    tap: "点一下看矿坑",
    listId: "island-quarry-list",
    tabAria: "盐风崖",
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
  if (name) name.textContent = shop.name || "盐风崖";
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
  const list = wrap.querySelector("#island-quarry-list");
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
  if (tab === "wash") return washMarkup(shop);
  if (tab === "pick") return pickMarkup(shop);
  return pitsMarkup(shop);
}

function sku(kind, target, title, note, price, on, extra = "") {
  return `<button type="button" class="island-shop-sku ${on ? "" : "is-off"} ${extra}" data-act="${esc(kind)}" data-target="${esc(target)}">
    <span class="island-shop-emoji">${esc(title.emoji || "·")}</span>
    <span class="island-shop-name"><b>${esc(title.name)}</b><small>${esc(note)}</small></span>
    <span class="island-shop-price">${esc(price)}</span>
  </button>`;
}

function pitsMarkup(shop) {
  const rows = [];
  for (const pit of shop.pits || []) {
    if (pit.can_hew) {
      rows.push(sku("hew", String(pit.slot), { emoji: pit.emoji, name: `坑${pit.slot}` }, pit.note, "挖", true, "is-ready"));
    } else if (pit.can_prospect) {
      rows.push(sku("prospect", String(pit.slot), { emoji: "🔍", name: `坑${pit.slot}` }, pit.note, "探", true, "is-ready"));
    } else {
      const kind = pit.state === "vein" ? "hew" : "prospect";
      rows.push(sku(kind, String(pit.slot), { emoji: pit.emoji || "🪨", name: `坑${pit.slot}` }, pit.note, "看", false));
    }
  }
  const next = shop.next_pit;
  if (next) {
    rows.push(sku("open_pit", "", { emoji: "＋", name: `再开坑${next.slot}` }, next.note, `${next.cost} 票`, Boolean(next.can_buy)));
  }
  return rows.join("") || `<p class="island-shop-empty">崖上还没开坑。</p>`;
}

function washMarkup(shop) {
  const rows = (shop.raws || []).map((row) => sku(
    "wash",
    `${row.name} ${row.qty}`,
    { emoji: row.emoji, name: row.name },
    row.note,
    row.can_wash ? "洗" : "看",
    Boolean(row.can_wash),
    row.can_wash ? "is-ready" : "",
  ));
  return rows.join("") || `<p class="island-shop-empty">挖到原矿再来洗。两份出一份精矿。</p>`;
}

function pickMarkup(shop) {
  const p = shop.pick || {};
  if (p.tier < 1) {
    return sku("buy_pick", "", { emoji: "⛏️", name: "盐风镐" }, p.note || "", p.can_buy ? `${p.buy_cost} 票` : "看", Boolean(p.can_buy), p.can_buy ? "is-ready" : "");
  }
  return sku(
    "upgrade",
    "",
    { emoji: "⛏️", name: `T${p.tier} ${p.name}` },
    p.upgrade_note || p.note || "",
    p.can_upgrade ? "升" : "看",
    Boolean(p.can_upgrade),
    p.can_upgrade ? "is-ready" : "",
  );
}
