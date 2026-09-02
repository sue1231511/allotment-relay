import { state } from "../store.js?v=island-modulefix2";

const PANELS = [
  ["island-stats", [
    ["shadow", "shadow_rep"],
    ["satiety", "satiety"],
    ["mist", "mist_wit"],
    ["standing", "standing"],
    ["health", "health"],
    ["energy", "energy"],
  ]],
  ["island-status", [
    ["tickets", "tickets"],
    ["level", "level"],
    ["bond", "island_bond"],
  ]],
];

function num(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? String(Math.round(n)) : "—";
}

export function paintStats() {
  const me = state.me || {};
  PANELS.forEach(([id, keys]) => {
    const el = document.getElementById(id);
    if (!el) return;
    keys.forEach(([k, field]) => {
      const slot = el.querySelector(`[data-k="${k}"]`);
      if (slot) slot.textContent = num(me[field]);
    });
  });
}

export function setStatsChip(on) {
  PANELS.forEach(([id]) => {
    const el = document.getElementById(id);
    if (!el) return;
    el.hidden = !on;
    if (on) el.removeAttribute("hidden");
  });
  if (on) paintStats();
}
