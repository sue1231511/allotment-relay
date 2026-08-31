import { hutScene, state } from "../store.js?v=island-mapbgm1";
import { bindShopFrame, ensureShopFrame, setShopPeek } from "../ui/shop-frame.js?v=island-mapbgm1";
import { esc } from "../ui/modal.js?v=island-mapbgm1";

/** 没买房看不见棚屋场景。买了才按等级换景，点一下看屋里能睡、做饭、升级、潮柜、堆肥桶、畜栏。 */

const mixSel = [];

export function renderHut(root, { onBuild, onAct, onSwitchTab, onOpenShelf, onCloseShelf, listTop = null } = {}) {
  const info = hutScene();
  hideActionBar();
  if (!info.built) {
    root.innerHTML = `
      <div class="island-place is-locked">
        <article class="island-place-card is-lock">
          <b>还没买房</b>
          <p>棚屋场景还锁着。搭好才看得见棚屋，再升到岸畔小屋、联盟小宅、临海邸会换景。点一下看屋里，能睡、做饭、升级、潮柜、堆肥桶、畜栏。</p>
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
  pruneMix(rows);
  if (!rows.length) {
    list.innerHTML = `<p class="island-shop-empty">这栏空着。</p>`;
  } else {
    list.innerHTML = rows.map((row) => sku(row)).join("");
    list.querySelectorAll("[data-act]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const kind = btn.getAttribute("data-act") || "";
        const target = btn.getAttribute("data-target") || "";
        const id = btn.getAttribute("data-id") || "";
        if (kind === "mix_pick") {
          toggleMix(target, Number(btn.getAttribute("data-qty") || "0"));
          paintList(wrap, shop, tab, onAct, list.scrollTop);
          return;
        }
        if (kind === "cook_mix") {
          if (onAct) onAct("cook_mix", mixSel.join(" "), id);
          return;
        }
        if (onAct) onAct(kind, target, id);
      });
    });
  }
  list.scrollTop = keep;
  requestAnimationFrame(() => {
    list.scrollTop = keep;
  });
}

function pruneMix(rows) {
  const have = {};
  for (const row of rows) {
    if (row.kind === "mix_pick") have[String(row.target || row.name)] = Number(row.qty) || 0;
  }
  if (!Object.keys(have).length && mixSel.length) {
    mixSel.length = 0;
    return;
  }
  if (!mixSel.length) return;
  const next = [];
  const used = {};
  for (const label of mixSel) {
    used[label] = (used[label] || 0) + 1;
    if ((have[label] || 0) >= used[label]) next.push(label);
  }
  mixSel.length = 0;
  mixSel.push(...next);
}

function mixCount(label) {
  return mixSel.filter((x) => x === label).length;
}

function toggleMix(label, qty) {
  const key = String(label || "");
  if (!key) return;
  const have = Number(qty) || 0;
  const others = mixSel.filter((x) => x !== key).length;
  const cur = mixCount(key);
  const cap = Math.min(have, Math.max(0, 5 - others));
  if (cur >= cap) {
    for (let i = mixSel.length - 1; i >= 0; i -= 1) {
      if (mixSel[i] === key) mixSel.splice(i, 1);
    }
    return;
  }
  mixSel.push(key);
}

function sku(row) {
  const kind = row.kind || "";
  const picked = kind === "mix_pick" ? mixCount(row.target || row.name) : 0;
  let extra = "";
  let price = row.price || "看";
  let note = row.note || "";
  let off = row.can ? "" : "is-off";
  if (kind === "mix_pick" && picked) {
    extra = " is-picked";
    off = "";
    price = `已点 ${picked}`;
    note = `行囊 ${row.qty || 0} · 再点加一份，点满取消。`;
  }
  if (kind === "cook_mix") {
    extra += " is-span";
    if (mixSel.length) {
      note = `已点 ${mixSel.join("、")}（${mixSel.length}/5）`;
      price = mixSel.length >= 2 && mixSel.length <= 5 ? "煮" : "再点";
      off = mixSel.length >= 2 && mixSel.length <= 5 ? "" : "is-off";
    }
  }
  if (kind === "quota") extra += " is-span";
  const cls = `island-shop-sku ${off}${extra}`.trim();
  return `<button type="button" class="${cls}" data-act="${esc(kind)}" data-target="${esc(row.target || "")}" data-id="${esc(row.id || "")}" data-qty="${esc(String(row.qty || 0))}">
    <span class="island-shop-emoji">${esc(row.emoji || "·")}</span>
    <span class="island-shop-name"><b>${esc(row.name)}</b><small>${esc(note)}</small></span>
    <span class="island-shop-price">${esc(price)}</span>
  </button>`;
}
