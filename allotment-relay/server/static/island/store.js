export const YARDS = {
  home: {
    key: "home",
    label: "菜地",
    unit: "块",
    full: "菜地已经种满了",
    empty: "还没有菜地",
    plant: "种菜地",
  },
  orchard: {
    key: "orchard",
    label: "果园",
    unit: "个",
    full: "果园已经种满了",
    empty: "还没有果园",
    plant: "种果园",
  },
  greenhouse: {
    key: "greenhouse",
    label: "温室",
    unit: "座",
    full: "温室已经种满了",
    empty: "还没有温室。点草地开垦第一座。",
    plant: "种温室",
  },
};

export const state = {
  enrolled: false,
  scene: "map",
  backTo: "map",
  tab: "map",
  yard: "home",
  yardPage: 0,
  yardsShelf: false,
  selectedSlot: null,
  plantOpen: false,
  plantKey: "kale",
  me: null,
  farm: null,
  world: null,
  shore: null,
  shoreTab: "beach",
  shoreShelf: false,
  port: null,
  portTab: "cast",
  portShelf: false,
  portPeek: false,
  portChatOpen: false,
  portChat: [],
  shop: null,
  shopTab: "seed",
  shopShelf: false,
  workshop: null,
  workshopTab: "anvil",
  workshopShelf: false,
  quarry: null,
  quarryTab: "pits",
  quarryShelf: false,
  bar: null,
  barTab: "work",
  barShelf: false,
  writers: null,
  writersTab: "desk",
  writersShelf: false,
  atelier: null,
  atelierTab: "desk",
  atelierShelf: false,
  hall: null,
  hallTab: "board",
  hallShelf: false,
  hallMeet: false,
  eatery: null,
  eateryTab: "board",
  eateryShelf: false,
  market: null,
  marketTab: "board",
  marketShelf: false,
  ting: null,
  tingTab: "ask",
  tingShelf: false,
  hui: null,
  huiTab: "ask",
  huiShelf: false,
  lianli: null,
  lianliTab: "desk",
  lianliShelf: false,
  lili: null,
  liliTab: "shelf",
  liliShelf: false,
  liliMeet: false,
  clinic: null,
  clinicTab: "treat",
  clinicMeet: false,
  lighthouse: null,
  lighthouseMeet: false,
  shaonian: null,
  shaonianMeet: false,
  beachPeek: false,
  hut: null,
  hutTab: "home",
  hutShelf: false,
  bagPage: 0,
  busy: false,
};

export function applySnapshot(data) {
  if (!data) return;
  if (data.enrolled != null) state.enrolled = data.enrolled;
  if (data.me) state.me = data.me;
  if (data.farm) state.farm = data.farm;
  if (data.world) state.world = data.world;
  if (data.shore) {
    state.shore = data.shore;
    const tabs = data.shore.tabs || [];
    if (tabs.length && !tabs.some((t) => t.key === state.shoreTab)) {
      state.shoreTab = tabs[0].key;
    }
  }
  if (data.port) {
    state.port = data.port;
    const tabs = data.port.tabs || [];
    if (tabs.length && !tabs.some((t) => t.key === state.portTab)) {
      state.portTab = tabs[0].key;
    }
  }
  if (data.shop) state.shop = data.shop;
  if (data.workshop) state.workshop = data.workshop;
  if (data.quarry) state.quarry = data.quarry;
  if (data.bar) state.bar = data.bar;
  if (data.writers) state.writers = data.writers;
  if (data.atelier) state.atelier = data.atelier;
  if (data.hall) state.hall = data.hall;
  if (data.eatery) {
    state.eatery = data.eatery;
    const tabs = data.eatery.tabs || [];
    if (tabs.length && !tabs.some((t) => t.key === state.eateryTab)) {
      state.eateryTab = tabs[0].key;
    }
  }
  if (data.market) {
    state.market = data.market;
    const tabs = data.market.tabs || [];
    if (tabs.length && !tabs.some((t) => t.key === state.marketTab)) {
      state.marketTab = tabs[0].key;
    }
  }
  if (data.ting) {
    state.ting = data.ting;
    const tabs = data.ting.tabs || [];
    if (tabs.length && !tabs.some((t) => t.key === state.tingTab)) {
      state.tingTab = tabs[0].key;
    }
  }
  if (data.hui) {
    state.hui = data.hui;
    const tabs = data.hui.tabs || [];
    if (tabs.length && !tabs.some((t) => t.key === state.huiTab)) {
      state.huiTab = tabs[0].key;
    }
  }
  if (data.lianli) {
    state.lianli = data.lianli;
    const tabs = data.lianli.tabs || [];
    if (tabs.length && !tabs.some((t) => t.key === state.lianliTab)) {
      state.lianliTab = tabs[0].key;
    }
  }
  if (data.lili) {
    state.lili = data.lili;
    const tabs = data.lili.tabs || [];
    if (tabs.length && !tabs.some((t) => t.key === state.liliTab)) {
      state.liliTab = tabs[0].key;
    }
  }
  if (data.clinic) {
    state.clinic = data.clinic;
    const tabs = data.clinic.tabs || [];
    if (tabs.length && !tabs.some((t) => t.key === state.clinicTab)) {
      state.clinicTab = tabs[0].key;
    }
  }
  if (data.hut) {
    state.hut = data.hut;
    const tabs = data.hut.tabs || [];
    if (tabs.length && !tabs.some((t) => t.key === state.hutTab)) {
      state.hutTab = tabs[0].key;
    }
  }
  if (data.lighthouse) state.lighthouse = data.lighthouse;
  if (data.shaonian) state.shaonian = data.shaonian;
}

export function yardMeta(kind = state.yard) {
  return YARDS[kind] || YARDS.home;
}

export function allPlots() {
  const farm = state.farm || {};
  if (Array.isArray(farm.parcels) && farm.parcels.length) return farm.parcels;
  return [
    ...((farm.home) || []),
    ...((farm.orchard) || []),
    ...((farm.greenhouse) || []),
  ];
}

export function yardPlots(kind = state.yard) {
  const farm = state.farm || {};
  if (kind === "orchard") {
    return farm.orchard || allPlots().filter((p) => p.orchard && !p.greenhouse);
  }
  if (kind === "greenhouse") {
    return farm.greenhouse || allPlots().filter((p) => p.greenhouse);
  }
  if (farm.home) return farm.home;
  return allPlots().filter((p) => !p.orchard && !p.greenhouse);
}

export function homePlots() {
  return yardPlots("home");
}

export function panelCrops() {
  const farm = state.farm || {};
  const kind = state.yard || "home";
  const all = (farm.panels && farm.panels[kind]) ? farm.panels[kind] : (farm.panel || []);
  return all.filter((crop) => (crop.seed_qty || 0) > 0);
}

export function plotToken(plot) {
  if (!plot) return "";
  if (plot.token) return String(plot.token);
  if (plot.greenhouse) return `棚${plot.slot}`;
  if (plot.orchard) return `园${plot.slot}`;
  return String(plot.slot);
}

export function plotLabel(plot) {
  const token = plotToken(plot);
  if (/[园棚]/.test(token)) return token;
  return `#${plot.slot}`;
}

export function plotByToken(token) {
  const want = String(token || "");
  if (!want) return null;
  return allPlots().find((p) => plotToken(p) === want) || null;
}

export function selectedPlot() {
  return plotByToken(state.selectedSlot);
}

export function firstIdleYard(kind = state.yard) {
  return yardPlots(kind)
    .filter((p) => p.can_sow)
    .sort((a, b) => Number(a.slot) - Number(b.slot))[0] || null;
}

export function firstIdleHome() {
  return firstIdleYard("home");
}

export function ripeYard(kind = state.yard) {
  return yardPlots(kind).filter((p) => p.can_harvest);
}

export function thirstyYard(kind = state.yard) {
  return yardPlots(kind).filter((p) => p.can_water);
}

export function ripeHome() {
  return ripeYard("home");
}

export function growingYard(kind = state.yard) {
  return yardPlots(kind).filter((p) => p.crop && !p.can_sow && !p.can_harvest);
}

export function growingHome() {
  return growingYard("home");
}

export function tickWorkshop(seconds = 1) {
  const job = state.workshop && state.workshop.job;
  if (!job || job.ready) return false;
  job.remain_sec = Math.max(0, (job.remain_sec || 0) - seconds);
  if (job.remain_sec === 0) {
    job.ready = true;
    job.can_take = true;
    job.note = "好了，可以取";
    state.workshop.line = `砧上：${job.name} 好了`;
    return true;
  }
  const n = job.remain_sec;
  job.note = n < 60 ? `还要 ${n} 秒` : `还要 ${Math.ceil(n / 60)} 分`;
  return false;
}

export function tickQuarry(seconds = 1) {
  const q = state.quarry;
  if (!q) return false;
  let ready = false;
  const tick = (row) => {
    if (!row || !(row.remain_sec > 0)) return;
    row.remain_sec = Math.max(0, row.remain_sec - seconds);
    if (row.remain_sec === 0) ready = true;
  };
  for (const pit of q.pits || []) tick(pit);
  if (q.prospect) tick(q.prospect);
  if (q.hew) tick(q.hew);
  return ready;
}

export function tickGrow(seconds = 1) {
  let matured = false;
  for (const plot of allPlots()) {
    if ((plot.remain_sec || 0) > 0) {
      plot.remain_sec = Math.max(0, plot.remain_sec - seconds);
      if (plot.remain_sec === 0) matured = true;
    }
  }
  return matured;
}

export function formatRemain(sec) {
  const n = Math.max(0, Math.floor(Number(sec) || 0));
  if (n <= 0) return "已成熟";
  if (n < 60) return `${n} 秒`;
  const mins = Math.ceil(n / 60);
  if (mins < 60) return `${mins} 分钟`;
  const hours = Math.floor(mins / 60);
  const left = mins % 60;
  return left ? `${hours} 小时 ${left} 分钟` : `${hours} 小时`;
}

export function growStatusLine(kind = state.yard) {
  const meta = yardMeta(kind);
  const plots = yardPlots(kind);
  if (!plots.length) return meta.empty;
  const idle = plots.filter((p) => p.can_sow).length;
  const ripe = ripeYard(kind).length;
  const growing = growingYard(kind);
  const clearing = plots.filter((p) => p.state === "clearing").length;
  let line = `${meta.label} ${plots.length} ${meta.unit}：空闲 ${idle} · 生长中 ${growing.length} · 可收 ${ripe}`;
  if (clearing) line += ` · 开垦中 ${clearing}`;
  if (growing.length) {
    const fastest = Math.min(...growing.map((p) => Number(p.remain_sec) || 0));
    const wait = fastest < 60
      ? `${Math.max(1, fastest)} 秒`
      : `${Math.max(1, Math.ceil(fastest / 60))} 分钟`;
    line += `；最快 ${wait}成熟`;
  }
  return line;
}

export function panelSubtitle(kind = state.yard) {
  const meta = yardMeta(kind);
  if (!yardPlots(kind).length) return meta.empty;
  const selected = selectedPlot();
  if (selected && selected.can_sow) return `种到 ${plotLabel(selected)}`;
  if (selected && !selected.can_sow) return "先点一块空地";
  if (!firstIdleYard(kind)) return meta.full;
  return growStatusLine(kind);
}

export function yardFullMessage(kind = state.yard) {
  return yardMeta(kind).full;
}

export function landSnap(kind = state.yard) {
  const land = (state.farm && state.farm.land) || {};
  if (kind === "orchard") return land.orchard || null;
  if (kind === "greenhouse") return land.greenhouse || null;
  return land.plots || null;
}

export function duesBlocked() {
  const dues = (state.me && state.me.dues) || {};
  return Number(dues.tax_arrears || 0) > 0 || Number(dues.upkeep_arrears || 0) > 0;
}

const HUT_NAMES = {
  1: "棚屋",
  2: "岸畔小屋",
  3: "联盟小宅",
  4: "临海邸",
};

/** 没买房看不见棚屋场景。买了才按 Lv1 棚屋 / Lv2 岸畔小屋 / Lv3 联盟小宅 / Lv4 临海邸换景。 */
export function hutScene() {
  const me = state.me || {};
  const flags = me.flags || {};
  const built = Boolean(flags.hut_built);
  const raw = Number(flags.hut_level) || 0;
  const level = built ? Math.min(4, Math.max(1, raw || 1)) : 0;
  const title = built
    ? (flags.hut_name || HUT_NAMES[level] || "岸畔小屋")
    : "岸畔小屋";
  return {
    built,
    level,
    sceneId: built ? `hut-${level}` : null,
    title,
    cost: Number(me.hut_build_cost) || 95,
  };
}
