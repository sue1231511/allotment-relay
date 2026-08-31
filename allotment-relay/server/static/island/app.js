import { api, loadKey } from "./api.js?v=island-hutscene1";
import {
  applySnapshot,
  duesBlocked,
  landSnap,
  plotByToken,
  plotToken,
  ripeYard,
  state,
  hutScene,
  tickGrow,
  tickQuarry,
  tickWorkshop,
} from "./store.js?v=island-hutscene1";
import { renderHud } from "./hud.js?v=island-hutscene1";
import { renderMap } from "./map.js?v=island-hutscene1";
import { renderHome, renderYards, syncHomeChrome } from "./scenes/home.js?v=island-hutscene1";
import { renderShore, renderShoreYard } from "./scenes/shore.js?v=island-hutscene1";
import { renderPlaza } from "./scenes/plaza.js?v=island-hutscene1";
import { renderPlace } from "./scenes/place.js?v=island-hutscene1";
import { renderHut } from "./scenes/hut.js?v=island-hutscene1";
import { renderShop } from "./scenes/shop.js?v=island-hutscene1";
import { renderLili } from "./scenes/lili.js?v=island-hutscene1";
import { renderClinic } from "./scenes/clinic.js?v=island-hutscene1";
import { renderWorkshop } from "./scenes/workshop.js?v=island-hutscene1";
import { renderQuarry } from "./scenes/quarry.js?v=island-hutscene1";
import { renderBar } from "./scenes/bar.js?v=island-hutscene1";
import { renderTheater } from "./scenes/theater.js?v=island-hutscene1";
import { renderWriters } from "./scenes/writers.js?v=island-hutscene1";
import { renderAtelier } from "./scenes/atelier.js?v=island-hutscene1";
import { renderHall } from "./scenes/hall.js?v=island-hutscene1";
import { renderEatery } from "./scenes/eatery.js?v=island-hutscene1";
import { renderMarket } from "./scenes/market.js?v=island-hutscene1";
import { renderTing } from "./scenes/ting.js?v=island-hutscene1";
import { renderHui } from "./scenes/hui.js?v=island-hutscene1";
import { renderLianli } from "./scenes/lianli.js?v=island-hutscene1";
let lighthouseMod = null;
async function lighthouseScene() {
  if (!lighthouseMod) lighthouseMod = await import("./scenes/lighthouse.js?v=island-hutscene1");
  return lighthouseMod;
}
import { renderBag } from "./ui/bag.js?v=island-hutscene1";
import { setBackChip, setBagChip } from "./ui/back-map.js?v=island-hutscene1";
import { hidePlantPanel, renderPlantPanel } from "./ui/plant-panel.js?v=island-hutscene1";
import { popOut } from "./ui/pop.js?v=island-hutscene1";
import { careActs, hideModal, showActSheet, showBuySheet, showCareSheet, showCheerSheet, showExpandSheet, showEvent, showFormSheet, showHintSheet, showPickSheet, showPitchSheet, showVendSheet, toast } from "./ui/modal.js?v=island-hutscene1";

const sceneEl = () => document.getElementById("island-scene");
const sheetEl = () => document.getElementById("island-sheet");
const plantEl = () => document.getElementById("island-plant");
const LIVE_SCENES = ["home", "yards", "hut"];
let growTimer = 0;
let workshopTimer = 0;
let quarryTimer = 0;

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

function showBootVeil(text) {
  if (window.__islandBoot && typeof window.__islandBoot.showVeil === "function") {
    window.__islandBoot.showVeil(text);
  }
}

function hideBootVeil() {
  if (window.__islandBoot && typeof window.__islandBoot.hideVeil === "function") {
    window.__islandBoot.hideVeil();
  }
}

async function waitScenePics(root) {
  if (window.__islandBoot && typeof window.__islandBoot.waitPics === "function") {
    await window.__islandBoot.waitPics(root);
  }
}

let enterGen = 0;

async function bootFromServer() {
  showBootVeil("正在进入…");
  const pending = [api.me()];
  if (window.__islandBoot && typeof window.__islandBoot.preload === "function") {
    pending.push(window.__islandBoot.preload());
  }
  const pair = await Promise.all(pending);
  applySnapshot(pair[0]);
  renderHud();
  showPlay();
  await enterScene(state.scene);
}

async function enterScene(name, opts) {
  const quiet = !!(opts && opts.quiet);
  if (name === "home") name = "yards";
  const gen = quiet ? enterGen : ++enterGen;
  if (!quiet) {
    showBootVeil("正在进入…");
  }
  state.scene = name;
  state.tab = "map";
  markDock("");
  hideSheet({ instant: true });
  if (name !== "yards") {
    closePlant();
    hideModal();
  }
  const root = sceneEl();
  if (!root) {
    if (!quiet && gen === enterGen) hideBootVeil();
    toast("地图画布还没准备好。");
    return;
  }
  const bar = document.getElementById("island-actionbar");
  if (bar) bar.hidden = name === "map" || name === "yards";
  setYardsChrome(name === "yards");
  setBagChip(name !== "map");
  setBackChip(name !== "map", () => enterScene(state.backTo || "map"));
  try {
    if (name === "yards") {
      stopWorkshopTick();
      stopQuarryTick();
      if (!quiet) state.yardsShelf = false;
      renderYards(root, {
        onTapPlot: tapPlot,
        onTapGrass: tapGrass,
        onHarvestAll: harvestAll,
        onSwitchYard: switchYard,
      });
      startGrowTick();
      if (state.plantOpen) openPlant();
    } else if (name === "shore") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.backTo = "map";
      setBackChip(true, () => enterScene("map"));
      renderShoreYard(root, {
        onOpen: (go) => {
          state.backTo = "shore";
          enterScene(go);
        },
      });
    } else if (name === "port") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.backTo = "shore";
      state.portShelf = false;
      await openPort(root);
    } else if (name === "beach") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.backTo = "shore";
      state.shoreShelf = false;
      await openBeach(root);
    } else if (name === "plaza") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.backTo = "map";
      setBackChip(true, () => enterScene("map"));
      renderPlaza(root, {
        onOpen: (go) => {
          state.backTo = "plaza";
          enterScene(go);
        },
      });
    } else if (name === "shop") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.shopShelf = false;
      await openShop(root);
    } else if (name === "lili") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.liliShelf = false;
      await openLili(root);
    } else if (name === "clinic") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.clinicShelf = false;
      await openClinic(root);
    } else if (name === "workshop") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.workshopShelf = false;
      await openWorkshop(root);
      startWorkshopTick();
    } else if (name === "quarry") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.quarryShelf = false;
      await openQuarry(root);
      startQuarryTick();
    } else if (name === "bar") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.barShelf = false;
      await openBar(root);
    } else if (name === "theater") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.backTo = "map";
      setBackChip(true, () => enterScene("map"));
      renderTheater(root, {
        onOpen: (go) => {
          state.backTo = "theater";
          enterScene(go);
        },
      });
    } else if (name === "writers") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.writersShelf = false;
      await openWriters(root);
    } else if (name === "atelier") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.atelierShelf = false;
      await openAtelier(root);
    } else if (name === "hall") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.hallShelf = false;
      state.hallMeet = false;
      await openHall(root);
    } else if (name === "eatery") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.eateryShelf = false;
      await openEatery(root);
    } else if (name === "market") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.marketShelf = false;
      await openMarket(root);
    } else if (name === "ting") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.tingShelf = false;
      await openTing(root);
    } else if (name === "hui") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.huiShelf = false;
      await openHui(root);
    } else if (name === "lianli") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.lianliShelf = false;
      await openLianli(root);
    } else if (name === "lighthouse") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.lighthouseMeet = false;
      await openLighthouse(root);
    } else if (name === "hut") {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      paintHut();
    } else if (PLACE_TITLES[name]) {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      renderPlaceScene(name);
    } else {
      stopGrowTick();
      stopWorkshopTick();
      stopQuarryTick();
      state.backTo = "map";
      renderMap(root, {
        onOpen: (go) => {
          state.backTo = "map";
          enterScene(go);
        },
      });
    }
    if (!quiet) await waitScenePics(root);
  } catch (err) {
    toast(err.message || "这处场景没能打开。");
    state.backTo = "map";
    renderMap(root, {
      onOpen: (go) => {
        state.backTo = "map";
        enterScene(go);
      },
    });
    if (!quiet) await waitScenePics(root);
  } finally {
    if (!quiet && gen === enterGen) hideBootVeil();
  }
}

const PLACE_TITLES = {
  hut: "岸畔小屋",
  bar: "潮汐酒吧",
  theater: "潮汐剧场",
  writers: "编剧社",
  atelier: "衣泊坊",
  hall: "剧场看台",
  eatery: "岸畔小馆",
  market: "集市",
  ting: "听潮亭",
  lianli: "连理所",
  hui: "潮生会",
  workshop: "岸工坊",
  quarry: "盐风崖",
  shop: "杂货铺",
  lili: "栗栗流动摊",
  clinic: "乔乔诊所",
  lighthouse: "灯塔",
  notice: "潮汐公告",
};

function renderPlaceScene(name) {
  renderPlace(sceneEl(), { id: name, title: PLACE_TITLES[name] || name });
}

function paintHut() {
  renderHut(sceneEl(), { onBuild: tapBuildHut });
}

function tapBuildHut() {
  const info = hutScene();
  if (info.built) return;
  showActSheet({
    title: "搭棚屋",
    body: `还没买房，棚屋场景还锁着。搭好才看得见。要 ${info.cost} 票。`,
    confirm: "确认搭",
    onConfirm: () => act(() => api.buildHut()),
  });
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
  paintShop(0);
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
    onOpenShelf: () => {
      state.shopShelf = true;
      paintShop(0);
    },
    onCloseShelf: () => {
      state.shopShelf = false;
      hideModal();
      paintShop();
    },
    listTop,
  });
}

async function openLili() {
  try {
    const data = await api.lili();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "摊子还没支起来。");
  }
  const tabs = (state.lili && state.lili.tabs) || [];
  if (!tabs.some((row) => row.key === state.liliTab)) {
    state.liliTab = (tabs[0] && tabs[0].key) || "shelf";
  }
  paintLili();
}

function paintLili(listTop = 0) {
  renderLili(sceneEl(), {
    onAct: tapLili,
    onSwitchTab: (tab) => {
      state.liliTab = tab || "shelf";
      hideModal();
      paintLili(0);
    },
    onOpenShelf: () => {
      state.liliShelf = true;
      paintLili(0);
    },
    onCloseShelf: () => {
      state.liliShelf = false;
      hideModal();
      paintLili();
    },
    listTop,
  });
}

function liliRow(kind, target, id) {
  const shop = state.lili || {};
  const items = shop.items || {};
  const rows = [
    ...(items.shelf || []),
    ...(items.summon || []),
    ...(items.side || []),
  ];
  return rows.find((row) =>
    (id && String(row.id) === String(id))
    || (row.kind === kind && String(row.target || "") === String(target || ""))
  ) || null;
}

function tapLili(kind, target, id) {
  const row = liliRow(kind, target, id) || {};
  if (kind === "look" || !row.can) {
    showHintSheet({
      title: row.name || "栗栗流动摊",
      body: row.detail || row.note || (state.lili && state.lili.line) || "这会儿摊上没有这一下。",
    });
    return;
  }
  const pack = {
    trade: ["换货", row.detail || row.note, "确认换"],
    summon: ["献壳唤摊", row.detail || row.note, "确认献"],
    pet: ["摸夜栖", row.detail || row.note, "确认摸"],
    junk: ["糙壳换乱捡款", row.detail || row.note, "确认换"],
  }[kind] || ["栗栗流动摊", row.detail || row.note || "做这一下？", "确认"];
  showActSheet({
    title: pack[0],
    body: pack[1],
    confirm: pack[2],
    onConfirm: () => runLili(kind, target || row.target || ""),
  });
}

async function runLili(kind, target) {
  const list = document.getElementById("island-lili-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.liliAct(kind, target), { keepLili: true, listTop, quiet: true });
}

async function openClinic() {
  try {
    const data = await api.clinic();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "诊室门还关着。");
  }
  const tabs = (state.clinic && state.clinic.tabs) || [];
  if (!tabs.some((row) => row.key === state.clinicTab)) {
    state.clinicTab = (tabs[0] && tabs[0].key) || "treat";
  }
  paintClinic();
}

function paintClinic(listTop = 0) {
  renderClinic(sceneEl(), {
    onAct: tapClinic,
    onSwitchTab: (tab) => {
      state.clinicTab = tab || "treat";
      hideModal();
      paintClinic(0);
    },
    onOpenShelf: () => {
      state.clinicShelf = true;
      paintClinic(0);
    },
    onCloseShelf: () => {
      state.clinicShelf = false;
      hideModal();
      paintClinic();
    },
    listTop,
  });
}

function clinicRow(kind, target, id) {
  const shop = state.clinic || {};
  const items = shop.items || {};
  const rows = [
    ...(items.treat || []),
    ...(items.tonic || []),
    ...(items.shelf || []),
    ...(items.dove || []),
  ];
  return rows.find((row) =>
    (id && String(row.id) === String(id))
    || (row.kind === kind && String(row.target || "") === String(target || ""))
  ) || null;
}

function tapClinic(kind, target, id) {
  const row = clinicRow(kind, target, id) || {};
  if (kind === "look" || !row.can) {
    showHintSheet({
      title: row.name || "乔乔诊所",
      body: row.detail || row.note || (state.clinic && state.clinic.line) || "这会儿诊所用不上这一下。",
    });
    return;
  }
  const pack = {
    treat: ["看病", row.detail || row.note, "确认治"],
    tonic: ["调理", row.detail || row.note, "确认调"],
    buy: ["买药", row.detail || row.note, "确认买"],
    use: ["服药", row.detail || row.note, "确认服"],
    dove: ["喂斑鸠", row.detail || row.note, "确认喂"],
    chat: ["闲聊", row.detail || row.note, "确认聊"],
  }[kind] || ["乔乔诊所", row.detail || row.note || "做这一下？", "确认"];
  showActSheet({
    title: pack[0],
    body: pack[1],
    confirm: pack[2],
    onConfirm: () => runClinic(kind, target || row.target || ""),
  });
}

async function runClinic(kind, target) {
  const list = document.getElementById("island-clinic-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.clinicAct(kind, target), { keepClinic: true, listTop, quiet: true });
}

async function openWorkshop(root) {
  try {
    const data = await api.workshop();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "工坊门还没开。");
  }
  const tabs = (state.workshop && state.workshop.tabs) || [];
  if (!tabs.some((row) => row.key === state.workshopTab)) {
    state.workshopTab = (tabs[0] && tabs[0].key) || "anvil";
  }
  paintWorkshop();
}

function paintWorkshop(listTop = 0) {
  renderWorkshop(sceneEl(), {
    onAct: tapWorkshop,
    onSwitchTab: switchWorkshopTab,
    onOpenShelf: () => {
      state.workshopShelf = true;
      paintWorkshop(0);
    },
    onCloseShelf: () => {
      state.workshopShelf = false;
      hideModal();
      paintWorkshop();
    },
    listTop,
  });
}

function switchWorkshopTab(tab) {
  state.workshopTab = tab || "anvil";
  hideModal();
  paintWorkshop(0);
}

function workshopRow(kind, target) {
  const shop = state.workshop || {};
  if (kind === "craft") return (shop.recipes || []).find((row) => row.name === target);
  if (kind === "take") return shop.job;
  if (kind === "fill" || kind === "harvest") {
    return (shop.pans || []).find((row) => String(row.slot) === String(target));
  }
  if (kind === "open_pan") return shop.next_pan;
  if (kind === "salvage") return shop.salvage;
  if (kind === "patch") return shop.patch;
  if (kind === "donate") return (shop.exhibits || []).find((row) => row.name === target);
  return null;
}

function workshopCan(kind, row) {
  if (!row) return false;
  if (kind === "craft") return Boolean(row.can_craft);
  if (kind === "take") return Boolean(row.can_take);
  if (kind === "fill") return Boolean(row.can_fill);
  if (kind === "harvest") return Boolean(row.can_harvest);
  if (kind === "open_pan") return Boolean(row.can_buy);
  if (kind === "salvage") return Boolean(row.can_salvage);
  if (kind === "patch") return Boolean(row.can_patch);
  if (kind === "donate") return Boolean(row.can_donate);
  return false;
}

function tapWorkshop(kind, target) {
  const row = workshopRow(kind, target);
  const body = (row && (row.detail || row.note)) || "做这一下？";
  if (!workshopCan(kind, row)) {
    showHintSheet({
      title: (row && row.name) || ({
        take: "砧上",
        fill: "盐田",
        harvest: "盐田",
        open_pan: "开池",
        salvage: "打捞",
        patch: "补网",
        donate: "陈列",
        craft: target || "砧上",
      }[kind] || "岸工坊"),
      body,
    });
    return;
  }
  const pack = {
    craft: ["开打", body, "确认打"],
    take: ["取成品", body, "确认取"],
    fill: ["灌盐田", body, "确认灌"],
    harvest: ["收盐", body, "确认收"],
    open_pan: ["开新池", body, "确认开"],
    salvage: ["打捞", body, "确认捞"],
    donate: ["捐陈列", body, "确认捐"],
    patch: ["补网", body, "确认贴"],
  }[kind] || ["岸工坊", body, "确认"];
  showActSheet({
    title: pack[0],
    body: pack[1],
    confirm: pack[2],
    onConfirm: () => runWorkshop(kind, target),
  });
}

async function runWorkshop(kind, target) {
  const list = document.getElementById("island-workshop-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.workshopAct(kind, target), { keepWorkshop: true, listTop, quiet: true });
}

function startWorkshopTick() {
  stopWorkshopTick();
  workshopTimer = window.setInterval(() => {
    if (state.scene !== "workshop" || state.busy) return;
    const ready = tickWorkshop(1);
    const list = document.getElementById("island-workshop-list");
    paintWorkshop(list ? list.scrollTop : 0);
    if (!ready) return;
    api.workshop().then((data) => {
      applySnapshot(data);
      renderHud();
      const after = document.getElementById("island-workshop-list");
      paintWorkshop(after ? after.scrollTop : 0);
    }).catch(() => {});
  }, 1000);
}

function stopWorkshopTick() {
  if (workshopTimer) window.clearInterval(workshopTimer);
  workshopTimer = 0;
}

async function openQuarry(root) {
  try {
    const data = await api.quarry();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "崖门还没开。");
  }
  const tabs = (state.quarry && state.quarry.tabs) || [];
  if (!tabs.some((row) => row.key === state.quarryTab)) {
    state.quarryTab = (tabs[0] && tabs[0].key) || "pits";
  }
  paintQuarry();
}

function paintQuarry(listTop = 0) {
  renderQuarry(sceneEl(), {
    onAct: tapQuarry,
    onSwitchTab: switchQuarryTab,
    onOpenShelf: () => {
      state.quarryShelf = true;
      paintQuarry(0);
    },
    onCloseShelf: () => {
      state.quarryShelf = false;
      hideModal();
      paintQuarry();
    },
    listTop,
  });
}

function switchQuarryTab(tab) {
  state.quarryTab = tab || "pits";
  hideModal();
  paintQuarry(0);
}

function quarryRow(kind, target) {
  const q = state.quarry || {};
  if (kind === "prospect" || kind === "hew") {
    return (q.pits || []).find((row) => String(row.slot) === String(target));
  }
  if (kind === "wash") {
    const name = String(target || "").split(/\s+/)[0];
    return (q.raws || []).find((row) => row.name === name);
  }
  if (kind === "open_pit") return q.next_pit;
  if (kind === "buy_pick" || kind === "upgrade") return q.pick;
  return null;
}

function quarryCan(kind, row) {
  if (!row) return false;
  if (kind === "prospect") return Boolean(row.can_prospect);
  if (kind === "hew") return Boolean(row.can_hew);
  if (kind === "wash") return Boolean(row.can_wash);
  if (kind === "open_pit") return Boolean(row.can_buy);
  if (kind === "buy_pick") return Boolean(row.can_buy);
  if (kind === "upgrade") return Boolean(row.can_upgrade);
  return false;
}

function tapQuarry(kind, target) {
  const row = quarryRow(kind, target);
  const body = (row && (row.detail || row.note || row.upgrade_note)) || "做这一下？";
  if (!quarryCan(kind, row)) {
    showHintSheet({
      title: (row && (row.name ? `坑${row.slot || ""} ${row.name}`.trim() : row.name)) || ({
        prospect: "探脉",
        hew: "挖",
        wash: "洗矿",
        open_pit: "开坑",
        buy_pick: "买镐",
        upgrade: "升镐",
      }[kind] || "盐风崖"),
      body,
    });
    return;
  }
  const pack = {
    prospect: ["探脉", body, "确认探"],
    hew: ["挥镐", body, "确认挖"],
    wash: ["洗矿", body, "确认洗"],
    open_pit: ["开新坑", body, "确认开"],
    buy_pick: ["买镐", body, "确认买"],
    upgrade: ["升镐", body, "确认升"],
  }[kind] || ["盐风崖", body, "确认"];
  showActSheet({
    title: pack[0],
    body: pack[1],
    confirm: pack[2],
    onConfirm: () => runQuarry(kind, target),
  });
}

async function runQuarry(kind, target) {
  const list = document.getElementById("island-quarry-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.quarryAct(kind, target), { keepQuarry: true, listTop, quiet: true });
}

async function openBar(root) {
  try {
    const data = await api.bar();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "酒吧门还没开。");
  }
  const tabs = (state.bar && state.bar.tabs) || [];
  if (!tabs.some((row) => row.key === state.barTab)) {
    state.barTab = (tabs[0] && tabs[0].key) || "work";
  }
  paintBar();
}

function paintBar(listTop = 0) {
  renderBar(sceneEl(), {
    onAct: tapBar,
    onSwitchTab: switchBarTab,
    onOpenShelf: () => {
      state.barShelf = true;
      paintBar(0);
    },
    onCloseShelf: () => {
      state.barShelf = false;
      hideModal();
      paintBar();
    },
    listTop,
  });
}

function switchBarTab(tab) {
  state.barTab = tab || "work";
  hideModal();
  paintBar(0);
}

function barRow(kind, target) {
  const shop = state.bar || {};
  if (kind === "work") return (shop.jobs || []).find((row) => row.cmd === target);
  if (kind === "order") return (shop.drinks || []).find((row) => row.name === target);
  if (kind === "cheer" || kind === "look") return shop.tonight || {};
  return null;
}

function barCan(kind, row) {
  if (!row) return false;
  if (kind === "work") return Boolean(row.can_work);
  if (kind === "order") return Boolean(row.can_order);
  if (kind === "cheer") return Boolean(row.can_cheer);
  return false;
}

function tapBar(kind, target) {
  const row = barRow(kind, target);
  if (kind === "look") {
    const t = row || {};
    const pack = {
      singer: [t.singer || "驻唱", t.singer_line || `今晚歌单 ${t.songs || 0} 首`],
      special: ["今日特调", t.special || "今晚还没定"],
      activity: [t.activity || "今晚", t.activity_desc || t.mood || "先看看场子"],
    }[target] || ["今晚", t.cheer_note || "先看看场子"];
    showHintSheet({ title: pack[0], body: pack[1] });
    return;
  }
  const body = (row && (row.detail || row.note || row.cheer_note)) || "做这一下？";
  if (!barCan(kind, row)) {
    showHintSheet({
      title: (row && row.name) || ({
        work: target || "上工",
        order: target || "酒单",
        cheer: "哄荔栀",
      }[kind] || "潮汐酒吧"),
      body,
    });
    return;
  }
  if (kind === "cheer") {
    showCheerSheet({
      title: "哄荔栀",
      body: body,
      presets: (row && row.cheer_presets) || ["今晚生意好", "杯子擦得亮", "辛苦了"],
      onConfirm: (line) => runBar("cheer", line),
    });
    return;
  }
  const pack = {
    work: ["洗碗打卡", body, "确认上工"],
    order: ["点酒", body, "确认点"],
  }[kind] || ["潮汐酒吧", body, "确认"];
  if (kind === "work") {
    pack[0] = (row && row.name) || "洗碗打卡";
  }
  showActSheet({
    title: pack[0],
    body: pack[1],
    confirm: pack[2],
    onConfirm: () => runBar(kind, target),
  });
}

async function runBar(kind, target) {
  const list = document.getElementById("island-bar-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.barAct(kind, target), { keepBar: true, listTop, quiet: true });
}

async function openWriters(root) {
  try {
    const data = await api.writers();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "编剧社门还没开。");
  }
  const tabs = (state.writers && state.writers.tabs) || [];
  if (!tabs.some((row) => row.key === state.writersTab)) {
    state.writersTab = (tabs[0] && tabs[0].key) || "desk";
  }
  paintWriters();
}

function paintWriters(listTop = 0) {
  renderWriters(sceneEl(), {
    onAct: tapWriters,
    onSwitchTab: (tab) => {
      state.writersTab = tab || "desk";
      hideModal();
      paintWriters(0);
    },
    onOpenShelf: () => {
      state.writersShelf = true;
      paintWriters(0);
    },
    onCloseShelf: () => {
      state.writersShelf = false;
      hideModal();
      paintWriters();
    },
    listTop,
  });
}

function tapWriters(kind, target) {
  const shop = state.writers || {};
  if (kind === "look") {
    const row = (shop.scripts || []).find((item) => String(item.id) === String(target));
    showHintSheet({
      title: row ? `《${row.title}》` : "编剧社",
      body: (row && (row.detail || row.note)) || shop.submit_note || "侧厅常开。稿费不是领薪。",
    });
    return;
  }
  if (kind === "submit") {
    if (!shop.can_submit) {
      showHintSheet({ title: "投稿", body: shop.submit_note || "待审已经满了。" });
      return;
    }
    showPitchSheet({
      title: "投稿",
      body: shop.submit_note || "标题和正文分开写。不是接现有潮闻。",
      titleMin: shop.title_min || 2,
      bodyMin: shop.body_min || 40,
      onConfirm: (line) => runWriters("submit", line),
    });
    return;
  }
  if (kind === "withdraw") {
    const row = (shop.scripts || []).find((item) => String(item.id) === String(target));
    if (!row || !row.can_withdraw) {
      showHintSheet({ title: "撤回", body: (row && row.detail) || "这篇不能撤回。" });
      return;
    }
    showActSheet({
      title: "撤回稿件",
      body: `撤回《${row.title}》？待审才能撤。`,
      confirm: "确认撤回",
      onConfirm: () => runWriters("withdraw", String(row.id)),
    });
  }
}

async function runWriters(kind, target) {
  const list = document.getElementById("island-writers-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.writersAct(kind, target), { keepWriters: true, listTop, quiet: true });
}

async function openAtelier(root) {
  try {
    const data = await api.atelier();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "衣泊坊门还没开。");
  }
  const tabs = (state.atelier && state.atelier.tabs) || [];
  if (!tabs.some((row) => row.key === state.atelierTab)) {
    state.atelierTab = (tabs[0] && tabs[0].key) || "desk";
  }
  paintAtelier();
}

function paintAtelier(listTop = 0) {
  renderAtelier(sceneEl(), {
    onAct: tapAtelier,
    onSwitchTab: (tab) => {
      state.atelierTab = tab || "desk";
      hideModal();
      paintAtelier(0);
    },
    onOpenShelf: () => {
      state.atelierShelf = true;
      paintAtelier(0);
    },
    onCloseShelf: () => {
      state.atelierShelf = false;
      hideModal();
      paintAtelier();
    },
    listTop,
  });
}

function tapAtelier(kind, target) {
  const shop = state.atelier || {};
  const desk = shop.desk || {};
  if (kind === "look") {
    const body = target === "worn" ? (desk.worn_note || "没穿。") : (desk.take_note || "台上空闲。");
    showHintSheet({
      title: target === "worn" ? (desk.worn || "身上") : (desk.job || "看坊"),
      body,
    });
    return;
  }
  if (kind === "take") {
    if (!desk.can_take) {
      showHintSheet({ title: "取衣", body: desk.take_note || "台上还没有做好的衣服。" });
      return;
    }
    showActSheet({
      title: "取衣",
      body: desk.take_note,
      confirm: "确认取",
      onConfirm: () => runAtelier("take", ""),
    });
    return;
  }
  if (kind === "remove") {
    if (!desk.can_remove) {
      showHintSheet({ title: "脱下", body: "本来就没穿。" });
      return;
    }
    showActSheet({
      title: "脱下",
      body: desk.worn_note || `脱下「${desk.worn}」。`,
      confirm: "确认脱",
      onConfirm: () => runAtelier("remove", ""),
    });
    return;
  }
  if (kind === "visit") {
    showActSheet({
      title: "见漾漾",
      body: desk.yangyang || "今日首次约三成给旧衣料，不是必给。",
      confirm: "去见",
      onConfirm: () => runAtelier("visit", ""),
    });
    return;
  }
  if (kind === "buy") {
    const row = (shop.goods || []).find((item) => item.cmd === target);
    if (!row || !row.can_buy) {
      showHintSheet({
        title: (row && row.name) || "现货",
        body: (row && (row.detail || row.note)) || "日常不卖成衣。",
      });
      return;
    }
    showActSheet({
      title: `买${row.name}`,
      body: row.detail || row.note,
      confirm: "确认买",
      onConfirm: () => runAtelier("buy", row.cmd),
    });
    return;
  }
  if (kind === "wear") {
    const row = (shop.closet || []).find((item) => String(item.id) === String(target));
    if (!row || !row.can_wear) {
      showHintSheet({
        title: (row && row.name) || "衣橱",
        body: (row && (row.detail || row.note)) || "衣橱空着。",
      });
      return;
    }
    showActSheet({
      title: "换衣服",
      body: `换上「${row.name}」。${row.note || ""}`,
      confirm: "确认穿",
      onConfirm: () => runAtelier("wear", String(row.id)),
    });
  }
}

async function runAtelier(kind, target) {
  const list = document.getElementById("island-atelier-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.atelierAct(kind, target), { keepAtelier: true, listTop, quiet: true });
}

async function openHall(root) {
  try {
    const data = await api.hall();
    applySnapshot(data);
    renderHud();
  } catch (err) {
    toast(err.message || "剧场门还没开。");
  }
  const tabs = (state.hall && state.hall.tabs) || [];
  if (!tabs.some((row) => row.key === state.hallTab)) {
    state.hallTab = (tabs[0] && tabs[0].key) || "board";
  }
  paintHall();
}

function paintHall() {
  renderHall(sceneEl(), { onAct: tapHall, onMeet: meetHall });
}

function meetHall() {
  if (state.hallMeet) return;
  state.hallMeet = true;
  paintHall();
}

function speakHall(text) {
  hideModal();
  if (!state.hall) state.hall = {};
  state.hall.line = text || "……";
  state.hall.speaker = state.hall.speaker || "小橘";
  paintHall();
}

function tapHall(kind, target) {
  const shop = state.hall || {};
  const board = shop.board || {};
  if (kind === "look") {
    if (target === "affinity") {
      const head = board.head_fan ? " · 头粉好感×2" : "";
      speakHall(`小橘好感 ${board.affinity ?? 0}/100${board.tier ? ` · ${board.tier}` : ""}${head}。`);
      return;
    }
    speakHall(board.note || "先看看今晚有没有专场。应援打赏围观就在看台。");
    return;
  }
  const star = (shop.stars || []).find((item) => item.id === kind);
  if (star) {
    if (!star.can_act) {
      speakHall(star.detail || star.note || "这会儿还不行。");
      return;
    }
    if (kind === "cheer") {
      showFormSheet({
        title: "应援",
        body: "每日一条，进她收件盒。要她本人点「看到」才算。",
        fields: [
          { id: "words", label: "好话", placeholder: "今晚很好听", max: 100, empty: "先写下一句好话。" },
        ],
        confirm: "递上去",
        onConfirm: (vals) => runHall("cheer", vals.words),
      });
      return;
    }
    if (kind === "tip") {
      showFormSheet({
        title: "打赏",
        body: "1～100 票。酒馆场荔栀抽三成，小剧场全归她。",
        fields: [
          { id: "amount", label: "票数", placeholder: "20", max: 3, empty: "先写下票数。" },
        ],
        confirm: "打赏",
        onConfirm: (vals) => runHall("tip", vals.amount),
      });
      return;
    }
    if (kind === "song") {
      showFormSheet({
        title: "点歌",
        body: "15 票，纸条递上台。她唱不唱，看她自己。",
        fields: [
          { id: "song", label: "歌名", placeholder: "歌名", max: 60, empty: "先写下歌名。" },
        ],
        confirm: "递纸条",
        onConfirm: (vals) => runHall("song", vals.song),
      });
      return;
    }
    runHall(kind, "");
    return;
  }
  const row = (shop.jobs || []).find((item) => item.id === kind);
  const body = (row && (row.detail || row.note)) || "做这一下？";
  if (!row || !row.can_act) {
    speakHall(body);
    return;
  }
  runHall(kind, target);
}

async function runHall(kind, target) {
  await act(() => api.hallAct(kind, target), { keepHall: true, quiet: true });
}

async function openEatery(root) {
  try {
    const data = await api.eatery();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "小馆门还没开。");
  }
  const tabs = (state.eatery && state.eatery.tabs) || [];
  if (!tabs.some((row) => row.key === state.eateryTab)) {
    state.eateryTab = (tabs[0] && tabs[0].key) || "board";
  }
  paintEatery();
}

function paintEatery(listTop = 0) {
  renderEatery(sceneEl(), {
    onAct: tapEatery,
    onSwitchTab: (tab) => {
      state.eateryTab = tab || "board";
      hideModal();
      paintEatery(0);
    },
    onOpenShelf: () => {
      state.eateryShelf = true;
      paintEatery(0);
    },
    onCloseShelf: () => {
      state.eateryShelf = false;
      hideModal();
      paintEatery();
    },
    listTop,
  });
}

function eateryRow(kind, target) {
  const shop = state.eatery || {};
  const mine = shop.mine || {};
  if (kind === "dine") {
    const [host, id] = String(target || "").split("|");
    return (shop.dishes || []).find((row) => row.shop === host && String(row.id) === String(id));
  }
  if (kind === "stock") return (mine.stock || []).find((row) => row.item === target);
  if (kind === "unstock") return (mine.menu || []).find((row) => String(row.id) === String(target));
  if (kind === "open" || kind === "sell") return mine;
  return (shop.dishes || []).find((row) => `${row.shop}|${row.id}` === target)
    || (mine.stock || []).find((row) => row.item === target)
    || mine;
}

function tapEatery(kind, target) {
  const shop = state.eatery || {};
  const mine = shop.mine || {};
  if (kind === "look") {
    const row = eateryRow("look", target) || {};
    showHintSheet({
      title: row.name || shop.name || "岸畔小馆",
      body: row.detail || row.note || row.open_note || shop.line || "先看看谁在开火。",
    });
    return;
  }
  const row = eateryRow(kind, target);
  const body = (row && (row.detail || row.note || row.open_note || row.sell_note)) || "做这一下？";
  const can = {
    dine: Boolean(row && row.can_dine),
    stock: Boolean(row && row.can_stock),
    unstock: Boolean(row && row.can_unstock),
    open: Boolean(mine.can_open),
    sell: Boolean(mine.can_sell),
  }[kind];
  if (!can) {
    showHintSheet({
      title: (row && row.name) || ({
        dine: "堂食",
        stock: "上架",
        unstock: "撤菜单",
        open: "开馆",
        sell: "卖掉小馆",
      }[kind] || "岸畔小馆"),
      body,
    });
    return;
  }
  const pack = {
    dine: ["堂食", body, "确认吃"],
    stock: ["上架", body, "确认上"],
    unstock: ["撤菜单", body, "确认撤"],
    open: ["开馆", mine.open_note || body, "确认开"],
    sell: ["卖掉小馆", mine.sell_note || body, "确认卖"],
  }[kind] || ["岸畔小馆", body, "确认"];
  showActSheet({
    title: pack[0],
    body: pack[1],
    confirm: pack[2],
    onConfirm: () => runEatery(kind, target),
  });
}

async function runEatery(kind, target) {
  const list = document.getElementById("island-eatery-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.eateryAct(kind, target), { keepEatery: true, listTop, quiet: true });
}

async function openMarket() {
  try {
    const data = await api.market();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "集市门还没开。");
  }
  const tabs = (state.market && state.market.tabs) || [];
  if (!tabs.some((row) => row.key === state.marketTab)) {
    state.marketTab = (tabs[0] && tabs[0].key) || "board";
  }
  paintMarket();
}

function paintMarket(listTop = 0) {
  renderMarket(sceneEl(), {
    onAct: tapMarket,
    onSwitchTab: (tab) => {
      state.marketTab = tab || "board";
      hideModal();
      paintMarket(0);
    },
    onOpenShelf: () => {
      state.marketShelf = true;
      paintMarket(0);
    },
    onCloseShelf: () => {
      state.marketShelf = false;
      hideModal();
      paintMarket();
    },
    listTop,
  });
}

function marketRow(kind, target) {
  const shop = state.market || {};
  const mine = shop.mine || {};
  if (kind === "buy" || (kind === "look" && target)) {
    return (shop.listings || []).find((row) => String(row.id) === String(target))
      || (mine.listings || []).find((row) => String(row.id) === String(target))
      || (mine.goods || []).find((row) => row.item === target)
      || mine;
  }
  if (kind === "cancel") return (mine.listings || []).find((row) => String(row.id) === String(target));
  if (kind === "sell") return (mine.goods || []).find((row) => row.item === target);
  if (kind === "expand") return mine;
  return null;
}

function tapMarket(kind, target) {
  const shop = state.market || {};
  const mine = shop.mine || {};
  const row = marketRow(kind, target) || {};
  if (kind === "look") {
    showHintSheet({
      title: row.name || shop.name || "玩家集市",
      body: row.detail || row.note || mine.expand_note || shop.line || "先看看街上谁在卖。",
    });
    return;
  }
  if (kind === "sell") {
    if (!row.can_sell) {
      showHintSheet({ title: row.name || "挂摊", body: row.detail || row.note || "这会儿挂不了。" });
      return;
    }
    showFormSheet({
      title: `挂出 ${row.name}`,
      body: row.detail || `袋里 ${row.qty}。建议 ${row.suggested} 票/个。`,
      fields: [
        { id: "qty", label: "数量", placeholder: "1", max: 4, empty: "先写下数量。" },
        { id: "price", label: "单价（票）", placeholder: String(row.suggested || 8), max: 6, empty: "先写下单价。" },
      ],
      confirm: "挂上",
      onConfirm: (vals) => runMarket("sell", `${row.item} ${vals.qty} ${vals.price}`),
    });
    return;
  }
  const can = {
    buy: Boolean(row.can_buy),
    cancel: Boolean(row.can_cancel),
    expand: Boolean(mine.can_expand),
  }[kind];
  if (!can) {
    showHintSheet({
      title: row.name || ({ buy: "买", cancel: "下架", expand: "扩摊" }[kind] || "集市"),
      body: row.detail || row.note || mine.expand_note || "这会儿还不行。",
    });
    return;
  }
  const pack = {
    buy: ["买下", row.detail || `一共 ${row.cost} 票（含手续费）。`, "确认买"],
    cancel: ["下架", row.detail || "货退回行囊。", "确认下架"],
    expand: ["扩一格", mine.expand_note || "加一格摊位。", "确认扩"],
  }[kind] || ["集市", "做这一下？", "确认"];
  showActSheet({
    title: pack[0],
    body: pack[1],
    confirm: pack[2],
    onConfirm: () => runMarket(kind, target),
  });
}

async function runMarket(kind, target) {
  const list = document.getElementById("island-market-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.marketAct(kind, target), { keepMarket: true, listTop, quiet: true });
}

async function openTing() {
  try {
    const data = await api.ting();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "亭门还没开。");
  }
  const tabs = (state.ting && state.ting.tabs) || [];
  if (!tabs.some((row) => row.key === state.tingTab)) {
    state.tingTab = (tabs[0] && tabs[0].key) || "ask";
  }
  paintTing();
}

function paintTing(listTop = 0) {
  renderTing(sceneEl(), {
    onAct: tapTing,
    onSwitchTab: (tab) => {
      state.tingTab = tab || "ask";
      hideModal();
      paintTing(0);
    },
    onOpenShelf: () => {
      state.tingShelf = true;
      paintTing(0);
    },
    onCloseShelf: () => {
      state.tingShelf = false;
      hideModal();
      paintTing();
    },
    listTop,
  });
}

function tingThread(id) {
  const shop = state.ting || {};
  const mine = shop.mine || [];
  const hit = mine.find((row) => String(row.id) === String(id));
  if (hit) return hit;
  const boards = shop.boards || {};
  for (const key of Object.keys(boards)) {
    const rows = (boards[key] && boards[key].threads) || [];
    const row = rows.find((item) => String(item.id) === String(id));
    if (row) return row;
  }
  return null;
}

function tapTing(kind, target) {
  const shop = state.ting || {};
  if (kind === "post") {
    const board = target || state.tingTab || "ask";
    const meta = (shop.boards && shop.boards[board]) || {};
    const tab = (shop.tabs || []).find((row) => row.key === board);
    showFormSheet({
      title: `钉到${(tab && tab.label) || "木牌"}`,
      body: meta.hint || shop.post_note || "标题和正文分开写。不是聊天室，不是厅示。",
      fields: [
        { id: "title", label: "标题", max: shop.title_max || 36, min: shop.title_min || 2, empty: "标题至少 2 个字。" },
        { id: "body", label: "正文", type: "textarea", rows: 5, max: shop.body_max || 800, min: shop.body_min || 8, empty: "正文至少 8 个字。" },
      ],
      confirm: "钉上去",
      onConfirm: (vals) => runTing("post", `${board}|${vals.title}|${vals.body}`),
    });
    return;
  }
  if (kind === "look") {
    lookTing(target);
    return;
  }
  if (kind === "tear") {
    const row = tingThread(target);
    if (!row || !row.can_tear) {
      showHintSheet({ title: "撕牌", body: (row && row.note) || "只能撕自己钉的。" });
      return;
    }
    showActSheet({
      title: "撕下来",
      body: `撕《${row.title}》？整帖从墙上拿下。`,
      confirm: "确认撕",
      onConfirm: () => runTing("tear", String(row.id)),
    });
  }
}

async function lookTing(id) {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await api.tingAct("look", String(id));
    applySnapshot(data);
    renderHud();
    const row = tingThread(id) || {};
    const text = (data.event && data.event.narrative) || row.detail || "这块木牌看不清。";
    const title = row.title ? `《${row.title}》` : "木牌";
    if (row.can_reply) {
      showActSheet({
        title,
        body: text,
        confirm: "回一张",
        onConfirm: () => replyTing(row),
      });
    } else {
      showHintSheet({ title, body: text });
    }
  } catch (err) {
    toast(err.message || "这块木牌看不清。");
  } finally {
    state.busy = false;
  }
}

function replyTing(row) {
  const shop = state.ting || {};
  showFormSheet({
    title: row.title ? `回《${row.title}》` : "回帖",
    body: "回帖会钉在这块木牌下面。不是聊天室。",
    fields: [
      { id: "body", label: "回帖", type: "textarea", rows: 4, max: shop.reply_max || 400, min: shop.reply_min || 2, empty: "回帖至少 2 个字。" },
    ],
    confirm: "钉上去",
    onConfirm: (vals) => runTing("reply", `${row.id}|${vals.body}`),
  });
}

async function runTing(kind, target) {
  const list = document.getElementById("island-ting-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.tingAct(kind, target), { keepTing: true, listTop, quiet: true });
}

async function openPort() {
  try {
    const data = await api.shore();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "潮水还没退到岸边。");
  }
  const tabs = (state.port && state.port.tabs) || [];
  if (!tabs.some((row) => row.key === state.portTab)) {
    state.portTab = (tabs[0] && tabs[0].key) || "cast";
  }
  paintPort();
}

function paintPort(listTop = 0) {
  renderShore(sceneEl(), {
    place: "port",
    onAct: tapShore,
    onSwitchTab: (tab) => {
      state.portTab = tab || "cast";
      hideModal();
      paintPort(0);
      if (tab === "chat") loadPortChat();
    },
    onOpenShelf: () => {
      state.portShelf = true;
      paintPort(0);
      if (state.portTab === "chat") loadPortChat();
    },
    onCloseShelf: () => {
      state.portShelf = false;
      hideModal();
      paintPort();
    },
    onSay: sayPort,
    listTop,
  });
}

async function loadPortChat() {
  if (state.scene !== "port" || !state.portShelf) return;
  try {
    const data = await api.messages();
    state.portChat = data.messages || [];
    if (state.scene === "port" && state.portTab === "chat" && state.portShelf) {
      paintPort();
    }
  } catch (err) {
    toast(err.message || "这会儿码头没人说话。");
  }
}

async function sayPort(text) {
  const line = (text || "").trim();
  if (!line || state.busy) return;
  state.busy = true;
  try {
    const data = await api.say(line);
    state.portChat = data.messages || [];
    renderHud();
    if (state.scene === "port" && state.portTab === "chat" && state.portShelf) {
      paintPort();
    }
  } catch (err) {
    toast(err.message || "这句没能说出去。");
  } finally {
    state.busy = false;
  }
}

async function openBeach() {
  try {
    const data = await api.shore();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "潮水还没退到岸边。");
  }
  const tabs = (state.shore && state.shore.tabs) || [];
  if (!tabs.some((row) => row.key === state.shoreTab)) {
    state.shoreTab = (tabs[0] && tabs[0].key) || "beach";
  }
  paintBeach();
}

function paintBeach(listTop = 0) {
  renderShore(sceneEl(), {
    place: "beach",
    onAct: tapShore,
    onSwitchTab: (tab) => {
      state.shoreTab = tab || "beach";
      hideModal();
      paintBeach(0);
    },
    onOpenShelf: () => {
      state.shoreShelf = true;
      paintBeach(0);
    },
    onCloseShelf: () => {
      state.shoreShelf = false;
      hideModal();
      paintBeach();
    },
    listTop,
  });
}

function shoreShop() {
  return state.scene === "port" ? (state.port || {}) : (state.shore || {});
}

function shoreTitle() {
  return state.scene === "port" ? "港口" : "海边";
}

function shoreRow(kind, target, id) {
  const shop = shoreShop();
  const items = shop.items || {};
  for (const key of Object.keys(items)) {
    const hit = (items[key] || []).find((row) => row.id === id || (row.kind === kind && String(row.target) === String(target)));
    if (hit) return hit;
  }
  return null;
}

function tapShore(kind, target, id) {
  const row = shoreRow(kind, target, id) || {};
  if (kind === "look") {
    lookShore(target, row);
    return;
  }
  if (!row.can) {
    showHintSheet({ title: row.name || shoreTitle(), body: row.detail || row.note || "这会儿做不了。" });
    return;
  }
  showActSheet({
    title: row.name || shoreTitle(),
    body: row.detail || row.note || "点一下就办。",
    confirm: row.price && row.price !== "看" ? String(row.price) : "确认",
    onConfirm: () => runShore(kind, target),
  });
}

async function lookShore(target, row) {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await api.shoreAct("look", String(target));
    applySnapshot(data);
    renderHud();
    const text = (data.event && data.event.narrative) || (row && (row.detail || row.note)) || "潮水拍了一下岸。";
    showHintSheet({ title: (row && row.name) || shoreTitle(), body: text });
  } catch (err) {
    toast(err.message || "这会儿看不清。");
  } finally {
    state.busy = false;
  }
}

async function runShore(kind, target) {
  const listId = state.scene === "port" ? "island-port-list" : "island-shore-list";
  const list = document.getElementById(listId);
  const listTop = list ? list.scrollTop : 0;
  const keep = state.scene === "port" ? { keepPort: true } : { keepShore: true };
  await act(() => api.shoreAct(kind, target), { ...keep, listTop, quiet: true });
}

async function openHui() {
  try {
    const data = await api.hui();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "会厅门还没开。");
  }
  const tabs = (state.hui && state.hui.tabs) || [];
  if (!tabs.some((row) => row.key === state.huiTab)) {
    state.huiTab = (tabs[0] && tabs[0].key) || "ask";
  }
  paintHui();
}

function paintHui(listTop = 0) {
  renderHui(sceneEl(), {
    onAct: tapHui,
    onSwitchTab: (tab) => {
      state.huiTab = tab || "ask";
      hideModal();
      paintHui(0);
    },
    onOpenShelf: () => {
      state.huiShelf = true;
      paintHui(0);
    },
    onCloseShelf: () => {
      state.huiShelf = false;
      hideModal();
      paintHui();
    },
    listTop,
  });
}

function huiRow(kind, target, id) {
  const shop = state.hui || {};
  const items = shop.items || {};
  for (const key of Object.keys(items)) {
    const hit = (items[key] || []).find((row) => row.id === id || (row.kind === kind && String(row.target) === String(target)));
    if (hit) return hit;
  }
  return null;
}

function tapHui(kind, target, id) {
  const shop = state.hui || {};
  const row = huiRow(kind, target, id) || {};
  if (kind === "look") {
    lookHui(target, row);
    return;
  }
  if (kind === "donate") {
    if (!row.can) {
      showHintSheet({ title: row.name || "捐基金", body: row.detail || row.note || "口袋不高于岛均，捐不了。" });
      return;
    }
    const max = shop.fund_max || shop.max_donate || "";
    showFormSheet({
      title: "捐进潮汐基金",
      body: row.detail || `票数自己填。最少 ${shop.min_donate || 1}。`,
      fields: [
        { id: "amount", label: "票数", placeholder: max ? String(max) : "50", max: 8, empty: "先写下票数。" },
      ],
      confirm: "捐进去",
      onConfirm: (vals) => runHui("donate", String(vals.amount)),
    });
    return;
  }
  if (kind === "pay_part") {
    if (!row.can) {
      showHintSheet({ title: row.name || "交一部分", body: row.detail || row.note || "这会儿不欠。" });
      return;
    }
    showFormSheet({
      title: row.name || "交一部分",
      body: row.detail || row.note || "自己填票数。",
      fields: [
        { id: "amount", label: "票数", placeholder: "50", max: 8, empty: "先写下票数。" },
      ],
      confirm: "交",
      onConfirm: (vals) => runHui("pay", `${target}:${vals.amount}`),
    });
    return;
  }
  if (kind === "pay") {
    if (!row.can) {
      showHintSheet({ title: row.name || "交", body: row.detail || row.note || "这会儿不欠。" });
      return;
    }
    showActSheet({
      title: row.name || "交清",
      body: row.detail || row.note || "把欠的交上。",
      confirm: "确认交",
      onConfirm: () => runHui("pay", target),
    });
  }
}

async function lookHui(target, row) {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await api.huiAct("look", String(target));
    applySnapshot(data);
    renderHud();
    const text = (data.event && data.event.narrative) || (row && (row.detail || row.note)) || "阿簿把册子合上。";
    showHintSheet({ title: (row && row.name) || "会厅", body: text });
  } catch (err) {
    toast(err.message || "这会儿看不清。");
  } finally {
    state.busy = false;
  }
}

async function runHui(kind, target) {
  const list = document.getElementById("island-hui-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.huiAct(kind, target), { keepHui: true, listTop, quiet: true });
}

async function openLianli() {
  try {
    const data = await api.lianli();
    applySnapshot(data);
    renderHud();
    if (data.event) showEvent(data.event);
  } catch (err) {
    toast(err.message || "登记处门还没开。");
  }
  const tabs = (state.lianli && state.lianli.tabs) || [];
  if (!tabs.some((row) => row.key === state.lianliTab)) {
    state.lianliTab = (tabs[0] && tabs[0].key) || "desk";
  }
  paintLianli();
}

function paintLianli(listTop = 0) {
  renderLianli(sceneEl(), {
    onAct: tapLianli,
    onSwitchTab: (tab) => {
      state.lianliTab = tab || "desk";
      hideModal();
      paintLianli(0);
    },
    onOpenShelf: () => {
      state.lianliShelf = true;
      paintLianli(0);
    },
    onCloseShelf: () => {
      state.lianliShelf = false;
      hideModal();
      paintLianli();
    },
    listTop,
  });
}

function lianliRow(kind, target, id) {
  const shop = state.lianli || {};
  const items = shop.items || {};
  for (const key of Object.keys(items)) {
    const hit = (items[key] || []).find((row) => row.id === id || (row.kind === kind && String(row.target) === String(target)));
    if (hit) return hit;
  }
  return null;
}

function tapLianli(kind, target, id) {
  const row = lianliRow(kind, target, id) || {};
  if (kind === "look") {
    if (row.can === false) {
      showHintSheet({ title: row.name || "登记处", body: row.detail || row.note || "这会儿还不行。" });
      return;
    }
    lookLianli(target, row);
    return;
  }
  if (kind === "bless") {
    if (!row.can) {
      showHintSheet({ title: row.name || "祝词", body: row.detail || row.note || "这会儿写不了。" });
      return;
    }
    showFormSheet({
      title: row.name || "祝词",
      body: row.note || "写下祝词，只进对方婚书。",
      fields: [
        { id: "body", label: "祝词", type: "textarea", rows: 4, max: 200, min: 2, empty: "祝词至少 2 个字。" },
      ],
      confirm: "留下",
      onConfirm: (vals) => runLianli("bless", `${target}|${vals.body}`),
    });
    return;
  }
  if (kind === "gift") {
    if (!row.can) {
      showHintSheet({ title: row.name || "送礼", body: row.detail || row.note || "这会儿送不了。" });
      return;
    }
    showFormSheet({
      title: row.name || "送礼",
      body: row.note || "写下行囊里的物品名。",
      fields: [
        { id: "item", label: "物品", placeholder: "海玻璃", max: 20, empty: "先写下物品名。" },
      ],
      confirm: "送出",
      onConfirm: (vals) => runLianli("gift", `${target}|${vals.item}`),
    });
    return;
  }
  if (!row.can) {
    showHintSheet({ title: row.name || "连理所", body: row.detail || row.note || "这会儿还不行。" });
    return;
  }
  const pack = kind === "buy"
    ? ["买下", row.detail || row.note || "Tt酱嫁妆柜，不打折。", "确认买"]
    : [row.name || "连理所", row.detail || row.note || "办这一下？", "确认"];
  showActSheet({
    title: pack[0],
    body: pack[1],
    confirm: pack[2],
    onConfirm: () => runLianli(kind, target),
  });
}

async function lookLianli(target, row) {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await api.lianliAct("look", String(target));
    applySnapshot(data);
    renderHud();
    const text = (data.event && data.event.narrative) || (row && (row.detail || row.note)) || "理枝把册子合上。";
    showHintSheet({ title: (row && row.name) || "登记处", body: text });
  } catch (err) {
    toast(err.message || "这会儿看不清。");
  } finally {
    state.busy = false;
  }
}

async function runLianli(kind, target) {
  const list = document.getElementById("island-lianli-list");
  const listTop = list ? list.scrollTop : 0;
  await act(() => api.lianliAct(kind, target), { keepLianli: true, listTop, quiet: true });
}

async function openLighthouse() {
  try {
    const data = await api.lighthouse();
    applySnapshot(data);
    renderHud();
  } catch (err) {
    toast(err.message || "塔门还没开。");
  }
  await paintLighthouse();
}

async function paintLighthouse() {
  const { renderLighthouse } = await lighthouseScene();
  renderLighthouse(sceneEl(), { onAct: tapLighthouse, onMeet: meetLighthouse });
}

async function meetLighthouse() {
  if (state.lighthouseMeet || state.busy) return;
  state.lighthouseMeet = true;
  await paintLighthouse();
  await act(() => api.lighthouseAct("visit"), { keepLighthouse: true, quiet: true });
}

function lighthouseChoice(kind) {
  const shop = state.lighthouse || {};
  return (shop.choices || []).find((row) => row.id === kind) || null;
}

function tapLighthouse(kind) {
  const shop = state.lighthouse || {};
  const row = lighthouseChoice(kind);
  if (kind === "light") {
    if (row && !row.can) {
      showHintSheet({ title: "点一盏守夜灯", body: row.detail || row.note || "灯油钱不够。" });
      return;
    }
    showFormSheet({
      title: "点一盏守夜灯",
      body: "名牌和愿望会挂上灯廊，全岛看得见。别写现实隐私。15 票，回 4 精力。",
      fields: [
        { id: "who", label: "给谁点的", placeholder: "妈妈", max: 24, empty: "先写下给谁点的。" },
        { id: "wish", label: "求什么", placeholder: "平安", max: 48, empty: "先写下求什么。" },
      ],
      confirm: "确认点灯",
      onConfirm: (vals) => runLighthouse("light", `${vals.who} | ${vals.wish}`),
    });
    return;
  }
  if (kind === "entrust") {
    showFormSheet({
      title: "托付旧事",
      body: "东西你留着，话记下。不要填写现实隐私。",
      fields: [
        { id: "text", label: "一件旧事", placeholder: "一把旧钥匙", max: 120, empty: "先写下一件旧事。" },
      ],
      confirm: "记下",
      onConfirm: (vals) => runLighthouse("entrust", vals.text),
    });
    return;
  }
  if (kind === "fulfill") {
    const open = (shop.lights || []).filter((item) => !item.fulfilled);
    if (!open.length) {
      showHintSheet({ title: "还愿", body: (row && (row.detail || row.note)) || "还没有自己点着的灯。" });
      return;
    }
    showPickSheet({
      title: "还愿",
      body: "在自己的灯旁记一个成了。",
      options: open.map((item) => ({
        id: String(item.id),
        label: `第 ${item.id} 盏 · 给${item.label}，求${item.wish}`,
      })),
      onConfirm: (id) => runLighthouse("fulfill", id),
    });
    return;
  }
  if (!row || !row.can) {
    showHintSheet({
      title: (row && row.label) || "灯塔",
      body: (row && (row.detail || row.note)) || "这会儿还不行。",
    });
    return;
  }
  if (row.confirm) {
    showActSheet({
      title: row.label,
      body: row.detail || row.note,
      confirm: row.confirm,
      onConfirm: () => runLighthouse(kind, ""),
    });
    return;
  }
  runLighthouse(kind, "");
}

async function runLighthouse(kind, target) {
  await act(() => api.lighthouseAct(kind, target), { keepLighthouse: true, quiet: true });
}

function startQuarryTick() {
  stopQuarryTick();
  quarryTimer = window.setInterval(() => {
    if (state.scene !== "quarry" || state.busy) return;
    const ready = tickQuarry(1);
    const list = document.getElementById("island-quarry-list");
    paintQuarry(list ? list.scrollTop : 0);
    if (!ready) return;
    api.quarry().then((data) => {
      applySnapshot(data);
      renderHud();
      const after = document.getElementById("island-quarry-list");
      paintQuarry(after ? after.scrollTop : 0);
    }).catch(() => {});
  }, 1000);
}

function stopQuarryTick() {
  if (quarryTimer) window.clearInterval(quarryTimer);
  quarryTimer = 0;
}

async function buyShopSku(item) {
  if (!item) return;
  const listTop = shopListTop();
  await act(() => api.shopBuy(item.id, 1), { keepShop: true, listTop, quiet: true });
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
    await enterScene("yards", { quiet: true });
  } catch (err) {
    toast(err.message || "这次没做成。");
    await enterScene("yards", { quiet: true });
  } finally {
    state.busy = false;
  }
}

function closeBag() {
  hideSheet();
  state.tab = "map";
  markDock("");
  if (state.scene !== "map") {
    setBagChip(true);
    setBackChip(true, () => enterScene(state.backTo || "map"));
  }
}

function bagHandlers() {
  return { onEat: eatItem, onVend: tapVend, onClose: closeBag };
}

async function eatItem(item) {
  await act(() => api.eat(item), { keepTab: true });
}

function tapVend(item) {
  if (!item) return;
  if (item.can_vend === false) {
    toast("这件不能从行囊卖掉。家具回小屋卖掉。");
    return;
  }
  showVendSheet(item, { onConfirm: () => vendItem(item) });
}

async function vendItem(item) {
  const name = (item && (item.name || item.item)) || "";
  if (!name) return;
  await act(() => api.vend(name, 1), { keepTab: true });
}

async function act(fn, { refreshScene = false, keepPlant = false, keepTab = false, keepShop = false, keepWorkshop = false, keepQuarry = false, keepBar = false, keepWriters = false, keepAtelier = false, keepHall = false, keepEatery = false, keepMarket = false, keepTing = false, keepHui = false, keepLianli = false, keepShore = false, keepPort = false, keepLighthouse = false, keepLili = false, keepClinic = false, listTop = null, quiet = false } = {}) {
  if (state.busy) return;
  state.busy = true;
  try {
    const data = await fn();
    applySnapshot(data);
    renderHud();
    if (data.event && !quiet) showEvent(data.event);
    else if (quiet && data.event && data.event.narrative && !keepLighthouse && !keepHall) toast(data.event.narrative);
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
    if (keepLili && state.scene === "lili") {
      paintLili(listTop);
      return;
    }
    if (keepClinic && state.scene === "clinic") {
      paintClinic(listTop);
      return;
    }
    if (keepWorkshop && state.scene === "workshop") {
      paintWorkshop(listTop);
      return;
    }
    if (keepQuarry && state.scene === "quarry") {
      paintQuarry(listTop);
      return;
    }
    if (keepBar && state.scene === "bar") {
      paintBar(listTop);
      return;
    }
    if (keepWriters && state.scene === "writers") {
      paintWriters(listTop);
      return;
    }
    if (keepAtelier && state.scene === "atelier") {
      paintAtelier(listTop);
      return;
    }
    if (keepHall && state.scene === "hall") {
      if (data.event && data.event.narrative && state.hall) {
        state.hall.line = data.event.narrative;
        state.hall.speaker = data.event.speaker || "小橘";
      }
      paintHall();
      return;
    }
    if (keepEatery && state.scene === "eatery") {
      paintEatery(listTop);
      return;
    }
    if (keepMarket && state.scene === "market") {
      paintMarket(listTop);
      return;
    }
    if (keepTing && state.scene === "ting") {
      paintTing(listTop);
      return;
    }
    if (keepHui && state.scene === "hui") {
      paintHui(listTop);
      return;
    }
    if (keepPort && state.scene === "port") {
      paintPort(listTop);
      return;
    }
    if (keepShore && state.scene === "beach") {
      paintBeach(listTop);
      return;
    }
    if (keepLianli && state.scene === "lianli") {
      paintLianli(listTop);
      return;
    }
    if (keepLighthouse && state.scene === "lighthouse") {
      if (data.event && data.event.narrative && state.lighthouse) {
        state.lighthouse.line = data.event.narrative;
        state.lighthouse.speaker = data.event.speaker || "不醒";
      }
      await paintLighthouse();
      return;
    }
    if (refreshScene || LIVE_SCENES.includes(state.scene)) {
      await enterScene(state.scene, { quiet: true });
    }
  } catch (err) {
    const msg = err.message || "这次没做成。";
    if (keepHall && state.scene === "hall") speakHall(msg);
    else toast(msg);
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

function hideSheet({ instant = false } = {}) {
  const sheet = sheetEl();
  if (!sheet) return;
  const finish = () => {
    if (sheet._popTimer) {
      window.clearTimeout(sheet._popTimer);
      sheet._popTimer = 0;
      sheet._popOut = false;
    }
    sheet.hidden = true;
    sheet.classList.remove("is-bag", "is-pop", "is-out");
    document.body.classList.remove("is-bag-open");
    sheet.innerHTML = "";
  };
  if (instant || sheet.hidden || !sheet.classList.contains("is-bag")) {
    finish();
    return;
  }
  popOut(sheet, finish);
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
    closeBag();
    return;
  }
  state.tab = "bag";
  state.bagPage = 0;
  markDock("bag");
  closePlant();
  setBagChip(false);
  setBackChip(false);
  renderBag(sheet, bagHandlers());
}

async function startFromSnapshot(data, scene) {
  applySnapshot(data);
  renderHud();
  if (!data || !data.enrolled) {
    hideBootVeil();
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
  showBootVeil("正在进入…");
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
    hideBootVeil();
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
  hideBootVeil();
  showGate();
  toast((error && error.message) || "地图没能打开。再点一次进入地图。");
});
