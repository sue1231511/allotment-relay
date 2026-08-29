import { api, loadKey, saveKey } from "./api.js";
import {
  applySnapshot,
  firstIdleYard,
  plotToken,
  ripeYard,
  state,
  tickGrow,
  yardFullMessage,
} from "./store.js";
import { renderHud } from "./hud.js";
import { renderMap } from "./map.js";
import { renderHome, syncHomeChrome } from "./scenes/home.js";
import { renderShore } from "./scenes/shore.js";
import { renderPlaza } from "./scenes/plaza.js";
import { renderBag } from "./ui/bag.js";
import { renderQuest } from "./ui/quest.js";
import { renderChat } from "./ui/chat.js";
import { hidePlantPanel, renderPlantPanel } from "./ui/plant-panel.js";
import { showEvent, toast } from "./ui/modal.js";

const sceneEl = () => document.getElementById("island-scene");
const sheetEl = () => document.getElementById("island-sheet");
const plantEl = () => document.getElementById("island-plant");
let loungeCache = { messages: [], notices: [] };
let growTimer = 0;

function showPlay() {
  document.getElementById("island-gate").classList.add("island-hidden");
  const stage = document.getElementById("island-stage");
  stage.classList.remove("island-hidden");
  stage.hidden = false;
  document.getElementById("island-dock").hidden = false;
}

function showGate() {
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
  if (name !== "home") closePlant();
  const root = sceneEl();
  if (!root) {
    toast("地图画布还没准备好。");
    return;
  }
  try {
    if (name === "home") {
      renderHome(root, {
        onOpenGarden: openPlant,
        onHarvestAll: harvestAll,
        onSwitchYard: switchYard,
        onBack: () => enterScene("map"),
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
    renderMap(root, { onOpen: enterScene });
  } catch (err) {
    toast(err.message || "这处场景没能打开。");
    renderMap(root, { onOpen: enterScene });
  }
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

async function harvestAll() {
  const ready = ripeYard();
  if (!ready.length) {
    toast("还没有成熟的作物。");
    return;
  }
  if (state.busy) return;
  state.busy = true;
  closePlant();
  try {
    let last = null;
    const notes = [];
    for (const plot of ready) {
      last = await api.harvest(plotToken(plot));
      applySnapshot(last);
      if (last.event && last.event.narrative) notes.push(last.event.narrative);
    }
    renderHud();
    if (notes.length) {
      showEvent({
        title: notes.length > 1 ? "一键收获" : "收获",
        narrative: notes.join("\n"),
        kind: "farm",
      });
    }
    await enterScene("home");
  } catch (err) {
    toast(err.message || "这次没做成。");
    await enterScene("home");
  } finally {
    state.busy = false;
  }
}

async function act(fn, { refreshScene = false, keepPlant = false } = {}) {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await fn();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
    if (!keepPlant) closePlant();
    if (refreshScene || state.scene === "home" || state.scene === "shore" || state.scene === "plaza") {
      await enterScene(state.scene);
    }
  } catch (err) {
    toast(err.message || "这次没做成。");
    if (state.scene === "home" && state.plantOpen) openPlant();
  } finally {
    state.busy = false;
  }
}

function startGrowTick() {
  stopGrowTick();
  growTimer = window.setInterval(async () => {
    if (state.scene !== "home" || state.busy) return;
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
    if (state.scene !== "map" && state.scene !== "home" && state.scene !== "shore" && state.scene !== "plaza") {
      await enterScene("map");
    }
    return;
  }
  closePlant();
  const sheet = sheetEl();
  if (tab === "bag") {
    renderBag(sheet);
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
    });
    renderChat(sheet, { messages: loungeCache.messages, onSay: talk });
  }
}

function bindGate() {
  const keyForm = document.getElementById("island-key-form");
  const enrollForm = document.getElementById("island-enroll-form");
  const keyInput = document.getElementById("island-key");
  const saved = loadKey();
  if (saved) keyInput.value = saved;
  keyForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const key = keyInput.value.trim();
    if (!key.startsWith("ar_sk_")) {
      toast("凭证应以 ar_sk_ 开头。");
      return;
    }
    saveKey(key);
    try {
      const data = await api.session(key);
      applySnapshot(data);
      renderHud();
      if (!data.enrolled) {
        enrollForm.classList.remove("island-hidden");
        toast("先起一个岛上的名字。");
        return;
      }
      showPlay();
      await enterScene("map");
    } catch (err) {
      toast(err.message);
    }
  });
  enrollForm.addEventListener("submit", async (ev) => {
    ev.preventDefault();
    const name = document.getElementById("island-enroll-name").value.trim();
    try {
      const data = await api.session(loadKey(), name);
      applySnapshot(data);
      renderHud();
      showPlay();
      try {
        if (data.event) showEvent(data.event);
      } catch {
        /* 弹窗失败不挡进家园 */
      }
      await enterScene("home");
    } catch (err) {
      toast(err.message);
    }
  });
}

function bindDock() {
  document.getElementById("island-dock").addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-tab]");
    if (btn) openTab(btn.getAttribute("data-tab"));
  });
  document.getElementById("island-scene").addEventListener("click", (ev) => {
    const pin = ev.target.closest("[data-go]");
    if (pin) enterScene(pin.getAttribute("data-go"));
  });
}

async function start() {
  bindGate();
  bindDock();
  const key = loadKey();
  if (!key) {
    showGate();
    return;
  }
  try {
    await bootFromServer();
  } catch (err) {
    if (err.code === "NOT_ENROLLED") {
      showGate();
      document.getElementById("island-enroll-form").classList.remove("island-hidden");
      return;
    }
    showGate();
    toast(err.message || "没能读到存档。");
  }
}

window.addEventListener("pageshow", () => {
  if (state.enrolled) {
    api.me().then((data) => {
      applySnapshot(data);
      renderHud();
      if (state.scene === "home") syncHomeChrome();
    }).catch(() => {});
  }
});

start();
