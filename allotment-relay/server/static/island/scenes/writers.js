import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=island-fix1";
import { esc } from "../ui/modal.js?v=island-fix1";
import { state } from "../store.js?v=island-fix1";

export function renderWriters(root, { onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const shop = state.writers || {};
  const tabs = shop.tabs || [];
  const tab = state.writersTab || (tabs[0] && tabs[0].key) || "desk";
  const peek = !state.writersShelf;
  const existing = root.querySelector(".island-writers");
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
      <div class="island-shop island-bar island-writers is-peek">
        <div class="island-shop-board">
          ${sceneArt("writers")}
          <button type="button" class="island-scene-tap">点一下看收稿台</button>
        </div>
      </div>
    `;
    hideActionBar();
    const wrap = root.querySelector(".island-writers");
    layoutCoverBoard(wrap, ".island-shop-board", 941, 1672);
    bindPeek(wrap, onOpenShelf);
    return;
  }
  root.innerHTML = `
    <div class="island-shop island-bar island-writers">
      ${sceneArt("writers")}
      <button type="button" class="island-scene-fold" aria-label="收起列表"></button>
      <div class="island-shop-shelf">
        <div class="island-shop-meta">
          <b>编剧社</b>
          <small></small>
        </div>
        <div class="island-shop-tabs" role="tablist" aria-label="编剧社">
        </div>
        <div class="island-shop-list" id="island-writers-list"></div>
      </div>
    </div>
  `;
  hideActionBar();
  const wrap = root.querySelector(".island-writers");
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
