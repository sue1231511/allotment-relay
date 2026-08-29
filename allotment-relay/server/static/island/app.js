import { api, loadKey, saveKey } from "./api.js";
import { applySnapshot, state } from "./store.js";
import { renderHud } from "./hud.js";
import { renderMap } from "./map.js";
import { renderHome } from "./scenes/home.js";
import { renderShore } from "./scenes/shore.js";
import { renderPlaza } from "./scenes/plaza.js";
import { renderBag } from "./ui/bag.js";
import { renderQuest } from "./ui/quest.js";
import { renderChat } from "./ui/chat.js";
import { showEvent, toast } from "./ui/modal.js";

const sceneEl = () => document.getElementById("island-scene");
const sheetEl = () => document.getElementById("island-sheet");
let loungeCache = { messages: [], notices: [] };

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
  const root = sceneEl();
  if (name === "home") {
    renderHome(root, {
      onSelect: (slot) => { state.selectedSlot = slot; enterScene("home"); },
      onSow: (slot, crop) => act(() => api.sow(slot, crop)),
      onWater: (slot) => act(() => api.water(slot)),
      onHarvest: (slot) => act(() => api.harvest(slot)),
      onLook: (plot) => showEvent({ title: plot.name || "地块", narrative: plot.label || plot.detail || "休耕。" }),
      onBack: () => enterScene("map"),
    });
    return;
  }
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
}

async function act(fn, { refreshScene = false } = {}) {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await fn();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
    if (refreshScene || state.scene === "home" || state.scene === "shore" || state.scene === "plaza") {
      await enterScene(state.scene);
    }
  } catch (err) {
    toast(err.message || "这次没做成。");
  } finally {
    state.busy = false;
  }
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
      if (data.event) showEvent(data.event);
      showPlay();
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
  }
}

window.addEventListener("pageshow", () => {
  if (state.enrolled) {
    api.me().then((data) => {
      applySnapshot(data);
      renderHud();
    }).catch(() => {});
  }
});

start();
