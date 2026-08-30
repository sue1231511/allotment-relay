import { api, loadKey } from "./api.js";
import {
  applySnapshot,
  duesBlocked,
  landSnap,
  plotByToken,
  plotToken,
  ripeYard,
  state,
  tickGrow,
} from "./store.js";
import { renderHud } from "./hud.js";
import { renderMap } from "./map.js";
import { renderHome, renderYards, syncHomeChrome } from "./scenes/home.js";
import { renderShore } from "./scenes/shore.js";
import { renderPlaza } from "./scenes/plaza.js";
import { renderPlace } from "./scenes/place.js";
import { renderShop } from "./scenes/shop.js";
import { renderBag } from "./ui/bag.js";
import { setBackChip, setBagChip } from "./ui/back-map.js";
import { hidePlantPanel, renderPlantPanel } from "./ui/plant-panel.js";
import { careActs, hideModal, showBuySheet, showCareSheet, showExpandSheet, showEvent, showVendSheet, toast } from "./ui/modal.js";

const sceneEl = () => document.getElementById("island-scene");
const sheetEl = () => document.getElementById("island-sheet");
const plantEl = () => document.getElementById("island-plant");
const LIVE_SCENES = ["home", "yards"];
let growTimer = 0;

function showPlay() {
  if (window.__islandBoot && typeof window.__islandBoot.showPlay === "function") {
    window.__islandBoot.showPlay();
    return;
  }
  document.body.classList.add("is-playing");
  const root = document.getElementById("island-root");
  if (root) root.classList.add("is-playing");
  document.getElementById("island-gate").classList.add("island-hidden");
  const stage = document.getElementById("island-stage");
  stage.classList.remove("island-hidden");
  stage.hidden = false;
  const dock = document.getElementById("island-dock");
  if (dock) dock.hidden = true;
  setBagChip(false);
}

function showGate() {
  document.body.classList.remove("is-yards");
  if (window.__islandBoot && typeof window.__islandBoot.showGate === "function") {
    window.__islandBoot.showGate();
    return;
  }
  document.body.classList.remove("is-playing");
  const root = document.getElementById("island-root");
  if (root) root.classList.remove("is-playing");
  document.getElementById("island-gate").classList.remove("island-hidden");
  document.getElementById("island-stage").hidden = true;
  const dock = document.getElementById("island-dock");
  if (dock) dock.hidden = true;
  setBagChip(false);
  setBackChip(false);
}

async function bootFromServer() {
  const data = await api.me();
  applySnapshot(data);
  renderHud();
  showPlay();
  await enterScene(state.scene);
}

async function enterScene(name) {
  if (name === "home") name = "yards";
  state.scene = name;
  state.tab = "map";
  markDock("");
  hideSheet();
  if (name !== "yards") {
    closePlant();
    hideModal();
  }
  const root = sceneEl();
  if (!root) {
    toast("地图画布还没准备好。");
    return;
  }
  const bar = document.getElementById("island-actionbar");
  if (bar) bar.hidden = name === "map" || name === "yards";
  setYardsChrome(name === "yards");
  setBagChip(name !== "map");
  setBackChip(name !== "map", () => enterScene(state.backTo || "map"));
  try {
    if (name === "home") {
      stopGrowTick();
      renderHome(root, {
        onOpenLand: () => enterScene("yards"),
        onBack: () => enterScene("map"),
      });
      return;
    }
    if (name === "yards") {
      renderYards(root, {
        onTapPlot: tapPlot,
        onTapGrass: tapGrass,
        onHarvestAll: harvestAll,
        onSwitchYard: switchYard,
      });
      startGrowTick();
      if (state.plantOpen) openPlant();
      return;
    }
    stopGrowTick();
    if (name === "shore") {
      renderShore(root);
      return;
    }
    if (name === "plaza") {
      state.backTo = "map";
      setBackChip(true, () => enterScene("map"));
      renderPlaza(root, {
        onOpen: (go) => {
          state.backTo = "plaza";
          enterScene(go);
        },
      });
      return;
    }
    if (name === "shop") {
      await openShop(root);
      return;
    }
    if (PLACE_TITLES[name]) {
      renderPlaceScene(name);
      return;
    }
    state.backTo = "map";
    renderMap(root, {
      onOpen: (go) => {
        state.backTo = "map";
        enterScene(go);
      },
    });
  } catch (err) {
    toast(err.message || "这处场景没能打开。");
    state.backTo = "map";
    renderMap(root, {
      onOpen: (go) => {
        state.backTo = "map";
        enterScene(go);
      },
    });
  }
}

const PLACE_TITLES = {
  hut: "岸畔小屋",
  bar: "潮汐酒吧",
  theater: "潮汐剧场",
  eatery: "岸畔小馆",
  market: "集市",
  ting: "听潮亭",
  lianli: "连理所",
  hui: "潮生会",
  workshop: "岸工坊",
  quarry: "盐风崖",
  shop: "杂货铺",
  lighthouse: "灯塔",
  notice: "潮汐公告",
};

function renderPlaceScene(name) {
  renderPlace(sceneEl(), { id: name, title: PLACE_TITLES[name] || name });
}

async function openShop(root) {
  try {
    const data = await api.shop();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "店门还没开。");
  }
  const tabs = (state.shop && state.shop.tabs) || [];
  if (!tabs.some((row) => row.key === state.shopTab)) {
    state.shopTab = (tabs[0] && tabs[0].key) || "seed";
  }
  paintShop();
}

function switchShopTab(tab) {
  state.shopTab = tab || "seed";
  hideModal();
  paintShop();
}

function tapShopSku(item) {
  if (!item) return;
  if (!item.can_buy) {
    toast(item.note || "这件现在买不了。");
    return;
  }
  showBuySheet(item, { onConfirm: () => buyShopSku(item) });
}

function shopListTop() {
  const list = document.getElementById("island-shop-list");
  return list ? list.scrollTop : 0;
}

function paintShop(listTop = 0) {
  renderShop(sceneEl(), {
    onBuy: tapShopSku,
    onSwitchTab: switchShopTab,
    listTop,
  });
}

async function buyShopSku(item) {
  if (!item) return;
  const listTop = shopListTop();
  await act(() => api.shopBuy(item.id, 1), { keepShop: true, listTop });
}

function tapGrass() {
  closePlant();
  hideModal();
  if (duesBlocked()) {
    toast("欠岸税或岸维，交清才能开垦。先去潮生会。");
    return;
  }
  const snap = landSnap();
  if (!snap) {
    toast("这块还不能开垦。");
    return;
  }
  if (snap.clearing) {
    const label = [snap.clearing_label, "开垦中", snap.clearing_eta].filter(Boolean).join(" · ");
    toast(label);
    return;
  }
  if (!snap.offer) {
    toast("现在不能开垦。");
    return;
  }
  showExpandSheet(snap, { onConfirm: confirmExpand });
}

async function confirmExpand() {
  await act(() => api.expand(state.yard || "home"));
}

function tapPlot(token) {
  const plot = plotByToken(token);
  if (!plot) return;
  state.selectedSlot = token;
  closePlant();
  hideModal();
  if (plot.state === "clearing") {
    toast(plot.detail || "开垦中");
    return;
  }
  if (plot.can_sow || plot.state === "fallow") {
    openPlant();
    return;
  }
  if (plot.state === "growing" || plot.state === "tending") {
    const acts = careActs(plot);
    if (!acts.length) {
      toast("这一茬打理、浇水、施肥都做过了。等它熟再点这块地。");
      return;
    }
    showCareSheet(plot, { onAct: (kind) => careAct(kind, token) });
    return;
  }
  if (plot.state === "ready") {
    const acts = careActs(plot);
    if (acts.length === 1 && acts[0].id === "harvest") {
      act(() => api.harvest(token));
      return;
    }
    showCareSheet(plot, { onAct: (kind) => careAct(kind, token) });
    return;
  }
  if (plot.state === "overripe") {
    showCareSheet(plot, { onAct: (kind) => careAct(kind, token) });
    return;
  }
  toast(plot.detail || "这块地现在点不了。");
}

async function careAct(kind, token) {
  const fn = {
    tend: () => api.tend(token),
    water: () => api.water(token),
    fertilize: () => api.fertilize(token),
    harvest: () => api.harvest(token),
    compost: () => api.compost(token),
    shake: () => api.shake(token),
  }[kind];
  if (!fn) return;
  await act(fn);
}

function openPlant() {
  state.plantOpen = true;
  hideSheet();
  hideModal();
  renderPlantPanel(plantEl(), {
    onSelect: (key) => {
      state.plantKey = key;
      openPlant();
    },
    onPlant: sowSelected,
    onBuy: buySeed,
    onClose: closePlant,
  });
}

function closePlant() {
  state.plantOpen = false;
  hidePlantPanel(plantEl());
}

function switchYard(yard) {
  state.yard = yard || "home";
  state.yardPage = 0;
  state.selectedSlot = null;
  closePlant();
  hideModal();
  syncHomeChrome();
}

async function sowSelected(crop) {
  if (!crop) {
    toast("先点一块空地。");
    return;
  }
  const plot = plotByToken(state.selectedSlot);
  if (!plot || !plot.can_sow) {
    toast("先点一块空地。");
    return;
  }
  await act(() => api.sow(plotToken(plot), crop.name || crop.key), { keepPlant: false });
}

async function buySeed(crop) {
  if (!crop) return;
  await act(() => api.buy(crop.name || crop.key, 1), { keepPlant: true });
}

async function harvestAll() {
  const ready = ripeYard();
  if (!ready.length) {
    toast("还没有成熟的作物。");
    return;
  }
  await runPlotBatch(ready, (plot) => api.harvest(plotToken(plot)), "一键收获", "收获");
}

async function runPlotBatch(plots, fn, manyTitle, oneTitle) {
  if (state.busy) return;
  state.busy = true;
  closePlant();
  hideModal();
  try {
    let last = null;
    const notes = [];
    for (const plot of plots) {
      last = await fn(plot);
      applySnapshot(last);
      if (last.event && last.event.narrative) notes.push(last.event.narrative);
    }
    renderHud();
    if (notes.length) {
      showEvent({
        title: notes.length > 1 ? manyTitle : oneTitle,
        narrative: notes.join("\n"),
        kind: "farm",
      });
    }
    await enterScene("yards");
  } catch (err) {
    toast(err.message || "这次没做成。");
    await enterScene("yards");
  } finally {
    state.busy = false;
  }
}

function bagHandlers() {
  return { onEat: eatItem, onVend: tapVend };
}

async function eatItem(item) {
  await act(() => api.eat(item), { keepTab: true });
}

function tapVend(item) {
  if (!item) return;
  if (item.can_vend === false) {
    toast("这件不能从行囊卖掉。家具去上手页小屋。");
    return;
  }
  showVendSheet(item, { onConfirm: () => vendItem(item) });
}

async function vendItem(item) {
  const name = (item && (item.name || item.item)) || "";
  if (!name) return;
  await act(() => api.vend(name, 1), { keepTab: true });
}

async function act(fn, { refreshScene = false, keepPlant = false, keepTab = false, keepShop = false, listTop = 0 } = {}) {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await fn();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
    if (!keepPlant) closePlant();
    else state.plantOpen = true;
    if (keepTab) {
      if (state.tab === "bag") renderBag(sheetEl(), bagHandlers());
      return;
    }
    if (keepShop && state.scene === "shop") {
      paintShop(listTop);
      return;
    }
    if (refreshScene || LIVE_SCENES.includes(state.scene)) {
      await enterScene(state.scene);
    }
  } catch (err) {
    toast(err.message || "这次没做成。");
    if (state.scene === "yards" && state.plantOpen) openPlant();
  } finally {
    state.busy = false;
  }
}

function startGrowTick() {
  stopGrowTick();
  growTimer = window.setInterval(async () => {
    if (state.scene !== "yards" || state.busy) return;
    const matured = tickGrow(1);
    syncHomeChrome();
    if (!matured) return;
    try {
      const data = await api.farm();
      applySnapshot(data);
      renderHud();
      syncHomeChrome();
      if (state.plantOpen) openPlant();
      else {
        const harvest = document.getElementById("island-harvest-all");
        if (harvest) harvest.hidden = ripeYard().length === 0;
      }
    } catch {
      /* 下一秒再试 */
    }
  }, 1000);
}

function stopGrowTick() {
  if (growTimer) window.clearInterval(growTimer);
  growTimer = 0;
}

function hideSheet() {
  const sheet = sheetEl();
  sheet.hidden = true;
  sheet.innerHTML = "";
}

function markDock(tab) {
  document.querySelectorAll("#island-dock [data-tab]").forEach((btn) => {
    btn.classList.toggle("is-on", btn.getAttribute("data-tab") === tab);
  });
}

function setYardsChrome(on) {
  document.body.classList.toggle("is-yards", on);
  const bar = document.getElementById("island-actionbar");
  if (bar && on) {
    bar.hidden = true;
    bar.innerHTML = "";
  }
  const dock = document.getElementById("island-dock");
  if (dock) dock.hidden = true;
}

async function openTab(tab) {
  if (tab !== "bag") return;
  const sheet = sheetEl();
  if (state.tab === "bag" && sheet && !sheet.hidden) {
    hideSheet();
    state.tab = "map";
    markDock("");
    return;
  }
  state.tab = "bag";
  markDock("bag");
  closePlant();
  renderBag(sheet, bagHandlers());
}

async function startFromSnapshot(data, scene) {
  applySnapshot(data);
  renderHud();
  if (!data || !data.enrolled) {
    showGate();
    const enrollForm = document.getElementById("island-enroll-form");
    if (enrollForm) enrollForm.classList.remove("island-hidden");
    toast("先起一个岛上的名字。");
    return;
  }
  showPlay();
  try {
    if (data.event && scene === "home") showEvent(data.event);
  } catch {
    /* 弹窗失败不挡进图 */
  }
  try {
    await enterScene(scene || "map");
  } catch (err) {
    toast(err.message || "地图没能打开。");
    const root = sceneEl();
    if (root) {
      try {
        renderMap(root, { onOpen: enterScene });
      } catch {
        if (window.__islandBoot) window.__islandBoot.fallbackScene(err.message);
      }
    }
  }
}

function bindDock() {
  const bag = document.getElementById("island-bag-chip");
  if (bag) bag.addEventListener("click", () => openTab("bag"));
  const dock = document.getElementById("island-dock");
  if (dock) {
    dock.addEventListener("click", (ev) => {
      const btn = ev.target.closest("[data-tab]");
      if (btn) openTab(btn.getAttribute("data-tab"));
    });
  }
  document.getElementById("island-scene").addEventListener("click", (ev) => {
    const link = ev.target.closest("[data-href]");
    if (link) {
      window.location.href = link.getAttribute("data-href");
      return;
    }
    const pin = ev.target.closest("[data-go]");
    if (pin) enterScene(pin.getAttribute("data-go"));
  });
  const ribbon = document.getElementById("island-ribbon");
  if (ribbon) {
    ribbon.addEventListener("click", (ev) => {
      const go = ev.target.closest("[data-go]");
      if (go) enterScene(go.getAttribute("data-go"));
    });
  }
}

async function start() {
  bindDock();
  window.__islandApp = true;
  window.__islandStart = startFromSnapshot;
  if (window.__islandPending) {
    const pending = window.__islandPending;
    window.__islandPending = null;
    await startFromSnapshot(pending.data, pending.scene);
    return;
  }
  const key = loadKey();
  if (!key) {
    showGate();
    return;
  }
  const enterBtn = document.getElementById("island-enter");
  window.__islandBusy = true;
  if (enterBtn) {
    enterBtn.disabled = true;
    enterBtn.textContent = "正在进入…";
  }
  if (window.__islandBoot && window.__islandBoot.hint) {
    window.__islandBoot.hint("正在进入地图。");
  }
  try {
    await bootFromServer();
  } catch (err) {
    if (err.code === "NOT_ENROLLED") {
      showGate();
      document.getElementById("island-enroll-form").classList.remove("island-hidden");
      toast("先起一个岛上的名字。");
      return;
    }
    showGate();
    toast(err.message || "没能读到存档。再点一次进入地图。");
  } finally {
    window.__islandBusy = false;
    if (enterBtn) {
      enterBtn.disabled = false;
      enterBtn.textContent = "进入地图";
    }
    if (window.__islandBoot && window.__islandBoot.hint) {
      window.__islandBoot.hint("");
    }
  }
}

window.addEventListener("pageshow", () => {
  if (state.enrolled) {
    api.me().then((data) => {
      applySnapshot(data);
      renderHud();
      if (state.scene === "yards") syncHomeChrome();
    }).catch(() => {});
  }
});

start().catch((error) => {
  showGate();
  toast((error && error.message) || "地图没能打开。再点一次进入地图。");
});
