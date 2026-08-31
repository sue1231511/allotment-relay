import { esc } from "../ui/modal.js?v=island-plantbag1";
import { state } from "../store.js?v=island-plantbag1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-plantbag1";

export function renderWorkshop(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.workshop || {};
  const tabs = shop.tabs || [];
  const tab = state.workshopTab || (tabs[0] && tabs[0].key) || "anvil";
  const peek = !state.workshopShelf;
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(".island-workshop"),
    className: "island-shop island-workshop",
    sceneId: "workshop",
    tap: "点一下看砧上",
    listId: "island-workshop-list",
    tabAria: "工坊",
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
  if (name) name.textContent = shop.name || "岸工坊";
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
  const list = wrap.querySelector("#island-workshop-list");
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
  if (tab === "salt") return saltMarkup(shop);
  if (tab === "salvage") return salvageMarkup(shop);
  if (tab === "exhibit") return exhibitMarkup(shop);
  return anvilMarkup(shop);
}

function sku(kind, target, title, note, price, on, extra = "") {
  return `<button type="button" class="island-shop-sku ${on ? "" : "is-off"} ${extra}" data-act="${esc(kind)}" data-target="${esc(target)}">
    <span class="island-shop-emoji">${esc(title.emoji || "·")}</span>
    <span class="island-shop-name"><b>${esc(title.name)}</b><small>${esc(note)}</small></span>
    <span class="island-shop-price">${esc(price)}</span>
  </button>`;
}

function needLine(needs) {
  return (needs || []).map((n) => `${n.label} ${n.have}/${n.qty}`).join(" · ");
}

function anvilMarkup(shop) {
  const job = shop.job;
  const rows = [];
  if (job) {
    rows.push(sku(
      "take",
      "",
      { emoji: job.emoji, name: job.ready ? `取 ${job.name}` : `正在打 ${job.name}` },
      job.note || "",
      job.ready ? "取" : "等",
      Boolean(job.can_take),
      job.ready ? "is-ready" : "",
    ));
  }
  for (const row of shop.recipes || []) {
    const need = needLine(row.need) || row.note || "";
    rows.push(sku(
      "craft",
      row.name,
      { emoji: row.emoji, name: row.name },
      row.note || need,
      row.can_craft ? "打" : "看",
      Boolean(row.can_craft),
    ));
  }
  return rows.join("") || `<p class="island-shop-empty">砧上这会儿没活。</p>`;
}

function saltMarkup(shop) {
  const rows = [];
  for (const pan of shop.pans || []) {
    if (pan.can_harvest) {
      rows.push(sku("harvest", String(pan.slot), { emoji: "🧂", name: `池${pan.slot}` }, pan.note, "收盐", true, "is-ready"));
    } else {
      rows.push(sku("fill", String(pan.slot), { emoji: "🌊", name: `池${pan.slot}` }, pan.note, pan.can_fill ? "灌" : "看", Boolean(pan.can_fill)));
    }
  }
  const next = shop.next_pan;
  if (next) {
    rows.push(sku("open_pan", "", { emoji: "＋", name: "再开一口" }, next.note, `${next.cost} 票`, Boolean(next.can_buy)));
  }
  return rows.join("") || `<p class="island-shop-empty">盐田还没铺。</p>`;
}

function salvageMarkup(shop) {
  const s = shop.salvage || {};
  const p = shop.patch || {};
  return [
    sku("salvage", "", { emoji: "🪵", name: "下滩打捞" }, s.note || "", s.can_salvage ? "捞" : "看", Boolean(s.can_salvage), s.can_salvage ? "is-ready" : ""),
    sku("patch", "", { emoji: "🩹", name: "补网" }, p.note || "", p.can_patch ? "贴" : "看", Boolean(p.can_patch)),
  ].join("");
}

function exhibitMarkup(shop) {
  const rows = (shop.exhibits || []).map((row) => sku(
    "donate",
    row.name,
    { emoji: row.emoji, name: row.name },
    row.note || needLine(row.need) || row.hint || "",
    row.donated ? "齐了" : (row.can_donate ? "捐" : "看"),
    Boolean(row.can_donate),
    row.can_donate ? "is-ready" : "",
  ));
  return rows.join("") || `<p class="island-shop-empty">柜子还空着。</p>`;
}
