import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=island-portchat1";
import { esc } from "../ui/modal.js?v=island-portchat1";
import { state } from "../store.js?v=island-portchat1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-portchat1";

/** 热区按滩景 1080×1920：码头船是港口，左下沙滩是海边。 */
const HOTS = [
  { go: "port", cls: "is-port", name: "港口", left: 28, top: 22, w: 68, h: 42 },
  { go: "beach", cls: "is-beach", name: "海边", left: 2, top: 62, w: 52, h: 34 },
];

export function renderShoreYard(root, { onOpen } = {}) {
  root.innerHTML = `
    <div class="island-plaza island-shore-yard">
      <div class="island-plaza-board island-shore-board">
        ${sceneArt("shore")}
        ${HOTS.map((p) => hotMarkup(p)).join("")}
      </div>
    </div>
  `;
  hideActionBar();
  layoutCoverBoard(root.querySelector(".island-shore-yard"), ".island-shore-board", 1080, 1920);
  if (typeof onOpen !== "function") return;
  root.querySelectorAll("[data-go]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      onOpen(btn.getAttribute("data-go"));
    });
  });
}

function hotMarkup(p) {
  const style = `left:${p.left}%;top:${p.top}%;width:${p.w}%;height:${p.h}%`;
  return `<button type="button" class="island-hot ${p.cls}" data-go="${p.go}" style="${style}" aria-label="${p.name}"><span>${p.name}</span></button>`;
}

export function renderShore(root, { place = "beach", onAct, onSwitchTab, onOpenShelf, onCloseShelf, onSay, listTop = null } = {}) {
  const isPort = place === "port";
  const shop = isPort ? (state.port || {}) : (state.shore || {});
  const peek = isPort ? !state.portShelf : !state.shoreShelf;
  const tabKey = isPort ? state.portTab : state.shoreTab;
  const tabs = shop.tabs || [];
  const tab = tabKey || (tabs[0] && tabs[0].key) || (isPort ? "cast" : "beach");
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(isPort ? ".island-port" : ".island-beach"),
    className: isPort ? "island-shop island-port" : "island-shop island-beach island-shore",
    sceneId: isPort ? "port" : "beach",
    tap: isPort ? "点一下看码头" : "点一下看沙滩",
    listId: isPort ? "island-port-list" : "island-shore-list",
    tabAria: isPort ? "港口" : "海边",
  });
  setShopPeek(wrap, peek);
  bindShopFrame(wrap, { onOpenShelf, onCloseShelf });
  hideActionBar();
  if (peek) return;
  paintChrome(wrap, shop, tabs, tab, onSwitchTab);
  paintList(wrap, shop, tab, onAct, isPort ? "island-port-list" : "island-shore-list", listTop == null ? 0 : listTop, onSay);
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
  if (name) name.textContent = shop.name || "海边";
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

function paintList(wrap, shop, tab, onAct, listId, listTop, onSay) {
  const list = wrap.querySelector(`#${listId}`);
  if (!list) return;
  const keep = listTop == null ? list.scrollTop : listTop;
  if (tab === "chat") {
    paintChat(list, onSay);
    return;
  }
  list.classList.remove("is-chat");
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

function paintChat(list, onSay) {
  list.classList.add("is-chat");
  const rows = state.portChat || [];
  const msgs = rows.length
    ? rows.slice(-20).map((m) => `
        <article class="island-port-msg">
          <b>${esc(m.who || "")}</b>
          <p>${esc(m.text || m.body || "")}</p>
        </article>
      `).join("")
    : `<p class="island-shop-empty">码头边还没人说话。</p>`;
  list.innerHTML = `
    <div class="island-port-msgs">${msgs}</div>
    <form class="island-port-say" id="island-port-say">
      <input name="text" maxlength="280" placeholder="码头边说一句" autocomplete="off">
      <button type="submit">发送</button>
    </form>
    <p class="island-shop-empty">港口闲聊，和上手页聊天室同一屋。对暗号、发红包仍去全服聊天室。</p>
  `;
  const box = list.querySelector(".island-port-msgs");
  if (box) box.scrollTop = box.scrollHeight;
  const form = list.querySelector("#island-port-say");
  if (form) {
    form.addEventListener("submit", (ev) => {
      ev.preventDefault();
      const input = ev.target.elements.text;
      const text = (input.value || "").trim();
      if (text && onSay) onSay(text);
    });
  }
}

function sku(row) {
  return `<button type="button" class="island-shop-sku ${row.can ? "" : "is-off"}" data-act="${esc(row.kind)}" data-target="${esc(row.target || "")}" data-id="${esc(row.id || "")}">
    <span class="island-shop-emoji">${esc(row.emoji || "·")}</span>
    <span class="island-shop-name"><b>${esc(row.name)}</b><small>${esc(row.note || "")}</small></span>
    <span class="island-shop-price">${esc(row.price || "看")}</span>
  </button>`;
}
