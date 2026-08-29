export const state = {
  enrolled: false,
  scene: "map",
  tab: "map",
  selectedSlot: null,
  plantOpen: false,
  plantKey: "kale",
  me: null,
  farm: null,
  world: null,
  shore: null,
  busy: false,
};

export function applySnapshot(data) {
  if (!data) return;
  if (data.enrolled != null) state.enrolled = data.enrolled;
  if (data.me) state.me = data.me;
  if (data.farm) state.farm = data.farm;
  if (data.world) state.world = data.world;
  if (data.shore) state.shore = data.shore;
}

export function homePlots() {
  return (state.farm && state.farm.home) || [];
}

export function panelCrops() {
  return (state.farm && state.farm.panel) || [];
}

export function selectedPlot() {
  return homePlots().find((p) => String(p.slot) === String(state.selectedSlot)) || null;
}

export function firstIdleHome() {
  return homePlots()
    .filter((p) => p.can_sow)
    .sort((a, b) => Number(a.slot) - Number(b.slot))[0] || null;
}

export function ripeHome() {
  return homePlots().filter((p) => p.can_harvest);
}

export function growingHome() {
  return homePlots().filter((p) => p.crop && !p.can_sow && !p.can_harvest);
}

export function tickGrow(seconds = 1) {
  let matured = false;
  for (const plot of homePlots()) {
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

export function growStatusLine() {
  const ripe = ripeHome().length;
  const growing = growingHome();
  if (!growing.length && !ripe) return "菜园空闲，可以种植";
  if (!growing.length && ripe) {
    return ripe === 1 ? "1 种作物成熟了" : `${ripe} 种作物成熟了`;
  }
  const fastest = Math.min(...growing.map((p) => Number(p.remain_sec) || 0));
  const wait = fastest < 60
    ? `${Math.max(1, fastest)} 秒`
    : `${Math.max(1, Math.ceil(fastest / 60))} 分钟`;
  return `${growing.length} 种作物生长中，最快 ${wait}成熟`;
}

export function panelSubtitle() {
  if (!firstIdleHome()) return "菜园已经种满了";
  return growStatusLine();
}
