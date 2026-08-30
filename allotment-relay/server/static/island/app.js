import { api, loadKey } from "./api.js";
import {
  applySnapshot,
  firstIdleYard,
  plotToken,
  ripeYard,
  state,
  thirstyYard,
  tickGrow,
  yardFullMessage,
} from "./store.js";
import { renderHud } from "./hud.js";
import { renderMap } from "./map.js";
import { renderHome, renderYards, syncHomeChrome } from "./scenes/home.js";
import { renderShore } from "./scenes/shore.js";
import { renderPlaza } from "./scenes/plaza.js";
import { renderPlace } from "./scenes/place.js";
import { renderBag } from "./ui/bag.js";
import { setBackChip, setBagChip } from "./ui/back-map.js";
import { hidePlantPanel, renderPlantPanel } from "./ui/plant-panel.js";
import { showEvent, toast } from "./ui/modal.js";

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
  if (name !== "yards") closePlant();
  const root = sceneEl();
  if (!root) {
    toast("地图画布还没准备好。");
    return;
  }
  const bar = document.getElementById("island-actionbar");
  if (bar) bar.hidden = name === "map" || name === "yards";
  setYardsChrome(name === "yards");
  setBagChip(name !== "map");
  setBackChip(name !== "map", () => enterScene("map"));
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
        onOpenGarden: openPlant,
        onHarvestAll: harvestAll,
        onWaterAll: waterAll,
        onSwitchYard: switchYard,
        onBack: () => enterScene("map"),
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
      renderPlaza(root);
      return;
    }
    if (name === "hut" || name === "bar" || name === "theater" || name === "eatery" || name === "hui" || name === "market" || name === "ting" || name === "lianli") {
      renderPlaceScene(name);
      return;
    }
    renderMap(root, { onOpen: enterScene });
  } catch (err) {
    toast(err.message || "这处场景没能打开。");
    renderMap(root, { onOpen: enterScene });
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
};

function renderPlaceScene(name) {
  renderPlace(sceneEl(), { id: name, title: PLACE_TITLES[name] || name });
}

function openPlant() {
  state.plantOpen = true;
  hideSheet();
  renderPlantPanel(plantEl(), {
    onSelect: (key) => {
      state.plantKey = key;
      openPlant();
    },
    onPlant: autoSow,
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
  syncHomeChrome();
  if (state.plantOpen) openPlant();
}

async function autoSow(crop) {
  if (!crop) {
    toast(yardFullMessage());
    return;
  }
  const idle = firstIdleYard();
  if (!idle) {
    toast(yardFullMessage());
    openPlant();
    return;
  }
  await act(() => api.sow(plotToken(idle), crop.name || crop.key), { keepPlant: false });
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

async function waterAll() {
  const thirsty = thirstyYard();
  if (!thirsty.length) {
    toast("这一类没有要浇的地。");
    return;
  }
  await runPlotBatch(thirsty, (plot) => api.water(plotToken(plot)), "浇水", "浇水");
}

async function runPlotBatch(plots, fn, manyTitle, oneTitle) {
  if (state.busy) return;
  state.busy = true;
  closePlant();
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

async function eatItem(item) {
  await act(() => api.eat(item), { keepTab: true });
}

async function act(fn, { refreshScene = false, keepPlant = false, keepTab = false } = {}) {
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
      if (state.tab === "bag") renderBag(sheetEl(), { onEat: eatItem });
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
  renderBag(sheet, { onEat: eatItem });
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
