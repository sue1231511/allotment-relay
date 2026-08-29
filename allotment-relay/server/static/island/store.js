export const state = {
  enrolled: false,
  scene: "map",
  tab: "map",
  selectedSlot: null,
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

export function selectedPlot() {
  return homePlots().find((p) => String(p.slot) === String(state.selectedSlot)) || null;
}
