import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=island-mapbgm1";
import { esc } from "../ui/modal.js?v=island-mapbgm1";
import { state } from "../store.js?v=island-mapbgm1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-mapbgm1";

function renderPickHub(root, {
  findClass,
  className,
  sceneId,
  tap,
  listId,
  title,
  line,
  rows,
  peek,
  onPeek,
  onClose,
  onPick,
}) {
  const wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(`.${findClass}`),
    className,
    sceneId,
    tap,
    listId,
    tabAria: title,
  });
  setShopPeek(wrap, peek);
  bindShopFrame(wrap, { onOpenShelf: onPeek, onCloseShelf: onClose });
  hideActionBar();
  if (peek) return;
  const name = wrap.querySelector(".island-shop-meta b");
  const note = wrap.querySelector(".island-shop-meta small");
  if (name) name.textContent = title;
  if (note) note.textContent = line;
  const tabBar = wrap.querySelector(".island-shop-tabs");
  if (tabBar) tabBar.innerHTML = "";
  const list = wrap.querySelector(`#${listId}`);
  if (!list) return;
  list.innerHTML = rows.map((row) => (
    `<button type="button" class="island-shop-sku" data-go="${esc(row.go)}">
      <span class="island-shop-emoji">${esc(row.emoji)}</span>
      <span class="island-shop-name"><b>${esc(row.name)}</b><small>${esc(row.note)}</small></span>
      <span class="island-shop-price">${esc(row.price)}</span>
    </button>`
  )).join("");
  list.querySelectorAll("[data-go]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (onPick) onPick(btn.getAttribute("data-go"));
    });
  });
}

export function renderPortHub(root, { onPeek, onClose, onChat, onDock } = {}) {
  renderPickHub(root, {
    findClass: "island-port-hub",
    className: "island-shop island-port-hub",
    sceneId: "port",
    tap: "点一下看码头",
    listId: "island-port-hub-list",
    title: "港口",
    line: "闲聊或看码头。",
    peek: !state.portPeek,
    rows: [
      { go: "chat", name: "闲聊", emoji: "💬", note: "全服聊天室。说话、发红包、对暗号、许愿墙。", price: "聊" },
      { go: "dock", name: "看码头", emoji: "⚓", note: "撒网、坐钓、开船。", price: "看" },
    ],
    onPeek,
    onClose,
    onPick: (go) => {
      if (go === "chat" && onChat) onChat();
      if (go === "dock" && onDock) onDock();
    },
  });
}

export function renderBeachHub(root, { onPeek, onClose, onMeet, onShore } = {}) {
  renderPickHub(root, {
    findClass: "island-beach-hub",
    className: "island-shop island-beach-hub",
    sceneId: "beach",
    tap: "点一下看沙滩",
    listId: "island-beach-hub-list",
    title: "海边",
    line: "去见韶年或去赶海。",
    peek: !state.beachPeek,
    rows: [
      { go: "shaonian", name: "去见韶年", emoji: "🎴", note: "卜卦、转运、买符。", price: "见" },
      { go: "shore", name: "去赶海", emoji: "🐚", note: "撒网、坐钓、赶海、开船。", price: "去" },
    ],
    onPeek,
    onClose,
    onPick: (go) => {
      if (go === "shaonian" && onMeet) onMeet();
      if (go === "shore" && onShore) onShore();
    },
  });
}

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

function sku(row) {
  return `<button type="button" class="island-shop-sku ${row.can ? "" : "is-off"}" data-act="${esc(row.kind)}" data-target="${esc(row.target || "")}" data-id="${esc(row.id || "")}">
    <span class="island-shop-emoji">${esc(row.emoji || "·")}</span>
    <span class="island-shop-name"><b>${esc(row.name)}</b><small>${esc(row.note || "")}</small></span>
    <span class="island-shop-price">${esc(row.price || "看")}</span>
  </button>`;
}
