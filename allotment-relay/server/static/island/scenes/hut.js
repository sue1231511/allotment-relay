import { hutScene, state } from "../store.js?v=island-mapbgm1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-mapbgm1";
import { esc } from "../ui/modal.js?v=island-mapbgm1";

/** 没买房看不见棚屋场景。买了才按等级换景，点一下看出能睡、升级、潮柜、堆肥桶、畜栏。 */
export function renderHut(root, { onBuild, onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const info = hutScene();
  hideActionBar();
  if (!info.built) {
    root.innerHTML = `
      <div class="island-place is-locked">
        <article class="island-place-card is-lock">
          <b>还没买房</b>
          <p>棚屋场景还锁着。搭好才看得见棚屋，再升到岸畔小屋、联盟小宅、临海邸会换景。点一下看屋里，能睡、升级、潮柜、堆肥桶、畜栏。</p>
          <button type="button" class="island-btn primary wide" data-act="build">搭棚屋 · ${esc(String(info.cost))} 票</button>
        </article>
      </div>
    `;
    const btn = root.querySelector("[data-act=build]");
    if (btn && typeof onBuild === "function") btn.addEventListener("click", onBuild);
    return;
  }
  const shop = state.hut || {};
  const tabs = shop.tabs || [];
  const tab = state.hutTab || (tabs[0] && tabs[0].key) || "home";
  const peek = !state.hutShelf;
  const sceneId = info.sceneId || shop.scene_id || "hut-1";
  let wrap = root.querySelector(".island-hut");
  if (wrap && wrap.getAttribute("data-scene") !== sceneId) {
    root.innerHTML = "";
    wrap = null;
  }
  wrap = ensureShopFrame(root, {
    find: (el) => el.querySelector(".island-hut"),
    className: "island-shop island-hut",
    sceneId,
    tap: "点一下看屋里",
    listId: "island-hut-list",
    tabAria: "小屋",
  });
  wrap.setAttribute("data-scene", sceneId);
  setShopPeek(wrap, peek);
  bindShopFrame(wrap, { onOpenShelf, onCloseShelf });
  if (peek) return;
  paintChrome(wrap, shop, info, tabs, tab, onSwitchTab);
  paintList(wrap, shop, tab, onAct, listTop == null ? 0 : listTop);
}

function hideActionBar() {
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
}

function paintChrome(wrap, shop, info, tabs, tab, onSwitchTab) {
  const name = wrap.querySelector(".island-shop-meta b");
  const note = wrap.querySelector(".island-shop-meta small");
  if (name) name.textContent = shop.name || info.title || "岸畔小屋";
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
  const list = wrap.querySelector("#island-hut-list");
  if (!list) return;
  const keep = listTop == null ? list.scrollTop : listTop;
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
