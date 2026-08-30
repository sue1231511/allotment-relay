import { layoutCoverBoard, sceneArt } from "../ui/art.js";
import { esc } from "../ui/modal.js";
import { state } from "../store.js";

export function renderHall(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.hall || {};
  const tabs = shop.tabs || [];
  const tab = state.hallTab || (tabs[0] && tabs[0].key) || "board";
  const peek = !state.hallShelf;
  const existing = root.querySelector(".island-hall");
  if (existing && existing.classList.contains("is-peek") === peek) {
    if (peek) {
      bindPeek(existing, onOpenShelf);
    } else {
      paintChrome(existing, shop, tabs, tab, onSwitchTab);
      paintList(existing, shop, tab, onAct, listTop);
      bindFold(existing, onCloseShelf);
    }
    hideActionBar();
    return;
  }
  if (peek) {
    root.innerHTML = `
      <div class="island-shop island-bar island-hall is-peek">
        <div class="island-shop-board">
          ${sceneArt("hall")}
          <button type="button" class="island-scene-tap">点一下看看板</button>
        </div>
      </div>
    `;
    hideActionBar();
    const wrap = root.querySelector(".island-hall");
    layoutCoverBoard(wrap, ".island-shop-board", 941, 1672);
    bindPeek(wrap, onOpenShelf);
    return;
  }
  root.innerHTML = `
    <div class="island-shop island-bar island-hall">
      ${sceneArt("hall")}
      <button type="button" class="island-scene-fold" aria-label="收起列表"></button>
      <div class="island-shop-shelf">
        <div class="island-shop-meta">
          <b>剧场看台</b>
          <small></small>
        </div>
        <div class="island-shop-tabs" role="tablist" aria-label="剧场看台">
        </div>
        <div class="island-shop-list" id="island-hall-list"></div>
      </div>
    </div>
  `;
  hideActionBar();
  const wrap = root.querySelector(".island-hall");
  paintChrome(wrap, shop, tabs, tab, onSwitchTab);
  paintList(wrap, shop, tab, onAct, listTop == null ? 0 : listTop);
  bindFold(wrap, onCloseShelf);
}

function bindPeek(wrap, onOpenShelf) {
  const board = wrap.querySelector(".island-shop-board");
  if (!board || board._bound) return;
  board._bound = true;
  board.addEventListener("click", () => onOpenShelf && onOpenShelf());
}

function bindFold(wrap, onCloseShelf) {
  const fold = wrap.querySelector(".island-scene-fold");
  if (!fold || fold._bound) return;
  fold._bound = true;
  fold.addEventListener("click", () => onCloseShelf && onCloseShelf());
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
