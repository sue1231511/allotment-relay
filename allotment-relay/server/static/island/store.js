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
  selectedSlot: null,
  plantOpen: false,
  plantKey: "kale",
  me: null,
  farm: null,
  world: null,
  shore: null,
  shop: null,
  shopTab: "seed",
  busy: false,
};

export function applySnapshot(data) {
  if (!data) return;
  if (data.enrolled != null) state.enrolled = data.enrolled;
  if (data.me) state.me = data.me;
  if (data.farm) state.farm = data.farm;
  if (data.world) state.world = data.world;
  if (data.shore) state.shore = data.shore;
  if (data.shop) state.shop = data.shop;
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
  if (farm.panels && farm.panels[kind]) return farm.panels[kind];
  return farm.panel || [];
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
