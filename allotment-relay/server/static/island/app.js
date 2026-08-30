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
import { renderQuest } from "./ui/quest.js";
import { renderChat } from "./ui/chat.js";
import { hidePlantPanel, renderPlantPanel } from "./ui/plant-panel.js";
import { showEvent, toast } from "./ui/modal.js";

const sceneEl = () => document.getElementById("island-scene");
const sheetEl = () => document.getElementById("island-sheet");
const plantEl = () => document.getElementById("island-plant");
const LIVE_SCENES = ["home", "yards", "shore", "plaza", "hut", "bar", "theater", "eatery", "hui"];
let loungeCache = { messages: [], notices: [] };
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
  document.getElementById("island-dock").hidden = false;
}

function showGate() {
  if (window.__islandBoot && typeof window.__islandBoot.showGate === "function") {
    window.__islandBoot.showGate();
    return;
  }
  document.body.classList.remove("is-playing");
  const root = document.getElementById("island-root");
  if (root) root.classList.remove("is-playing");
  document.getElementById("island-gate").classList.remove("island-hidden");
  document.getElementById("island-stage").hidden = true;
  document.getElementById("island-dock").hidden = true;
}

async function bootFromServer() {
  const data = await api.me();
  applySnapshot(data);
  renderHud();
  showPlay();
  await enterScene(state.scene);
}

async function enterScene(name) {
  state.scene = name;
  state.tab = "map";
  markDock("map");
  hideSheet();
  if (name !== "yards") closePlant();
  const root = sceneEl();
  if (!root) {
    toast("地图画布还没准备好。");
    return;
  }
  const bar = document.getElementById("island-actionbar");
  if (bar && name !== "map") bar.hidden = false;
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
        onBack: () => enterScene("home"),
      });
      startGrowTick();
      if (state.plantOpen) openPlant();
      return;
    }
    stopGrowTick();
    if (name === "shore") {
      renderShore(root, {
        onCast: (mode) => act(() => api.shore(mode)),
        onBack: () => enterScene("map"),
      });
      return;
    }
    if (name === "plaza") {
      try {
        loungeCache = await api.messages();
      } catch (err) {
        toast(err.message);
      }
      renderPlaza(root, {
        messages: loungeCache.messages,
        notices: loungeCache.notices,
        onSay: (text) => act(async () => {
          const out = await api.say(text);
          loungeCache = out;
          return out;
        }, { refreshScene: true }),
        onBack: () => enterScene("map"),
      });
      return;
    }
    if (name === "hut" || name === "bar" || name === "theater" || name === "eatery" || name === "hui") {
      renderPlaceScene(name);
      return;
    }
    renderMap(root, { onOpen: enterScene });
  } catch (err) {
    toast(err.message || "这处场景没能打开。");
    renderMap(root, { onOpen: enterScene });
  }
}

function renderPlaceScene(name) {
  const root = sceneEl();
  const me = state.me || {};
  const flags = me.flags || {};
  const dues = me.dues || {};
  const stock = me.stock || [];
  const back = () => enterScene("map");
  if (name === "hut") {
    const built = !!flags.hut_built;
    renderPlace(root, {
      id: "hut",
      title: "岸畔小屋",
      body: built
        ? ["困了就睡。每天一次，回精力。没有床就去上手页买一张装上。升级仍去上手页。"]
        : ["还没有棚屋。先搭一座才能睡。床和升级仍去上手页。"],
      actions: built
        ? [{ id: "sleep", label: "睡觉", primary: true }]
        : [{ id: "build", label: "搭棚屋", primary: true }],
      onAct: (id) => act(() => (id === "build" ? api.buildHut() : api.sleep())),
      onBack: back,
    });
    return;
  }
  if (name === "bar") {
    renderPlace(root, {
      id: "bar",
      title: "潮汐酒吧",
      body: [
        me.duty || "每 2 天来洗一次碗。",
        "点单仍去上手页。",
      ],
      actions: [{ id: "work", label: "洗碗", primary: true }],
      onAct: () => act(() => api.work()),
      onBack: back,
    });
    return;
  }
  if (name === "theater") {
    renderPlace(root, {
      id: "theater",
      title: "潮汐剧场",
      body: ["浪潮为幕，星光为灯。打赏、看今晚档仍去上手页。"],
      actions: [{ id: "play", label: "去上手页", primary: true }],
      onAct: () => { window.location.href = "/play?go=star"; },
      onBack: back,
    });
    return;
  }
  if (name === "eatery") {
    renderPlace(root, {
      id: "eatery",
      title: "岸畔小馆",
      body: [
        stock.length ? "饿了打开行囊吃一口。点单、下别人家馆子仍去上手页。" : "行囊空着。先种、收或去上手页下馆子。",
      ],
      actions: [{ id: "bag", label: "打开行囊", primary: true }],
      onAct: () => openTab("bag"),
      onBack: back,
    });
    return;
  }
  const tax = Number(dues.tax_arrears) || 0;
  const upkeep = Number(dues.upkeep_arrears) || 0;
  renderPlace(root, {
    id: "hui",
    title: "潮生会",
    body: [
      tax || upkeep ? "欠了就交。交完红条会灭。" : "岸税岸维没欠就不用跑。",
      "捐基金、看告示仍去上手页。",
    ],
    actions: [
      { id: "tax", label: tax ? `交岸税 ${tax}` : "交岸税", primary: !!tax, disabled: !tax },
      { id: "upkeep", label: upkeep ? `交岸维 ${upkeep}` : "交岸维", disabled: !upkeep },
    ],
    onAct: (id) => act(() => api.pay(id === "upkeep" ? "upkeep" : "tax")),
    onBack: back,
  });
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

async function openTab(tab) {
  state.tab = tab;
  markDock(tab);
  if (tab === "map") {
    hideSheet();
    if (state.scene !== "map" && !LIVE_SCENES.includes(state.scene)) {
      await enterScene("map");
    }
    return;
  }
  closePlant();
  const sheet = sheetEl();
  if (tab === "bag") {
    renderBag(sheet, { onEat: eatItem });
    return;
  }
  if (tab === "quest") {
    renderQuest(sheet);
    return;
  }
  if (tab === "chat") {
    try {
      loungeCache = await api.messages();
    } catch (err) {
      toast(err.message);
    }
    const talk = (text) => act(async () => {
      const out = await api.say(text);
      loungeCache = out;
      renderChat(sheet, { messages: out.messages, onSay: talk });
      return out;
    }, { keepTab: true });
    renderChat(sheet, { messages: loungeCache.messages, onSay: talk });
  }
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
  document.getElementById("island-dock").addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-tab]");
    if (btn) openTab(btn.getAttribute("data-tab"));
  });
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
