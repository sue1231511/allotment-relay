import { state } from "../store.js?v=island-mapbgm1";

const KEYS = [
  ["shadow", "shadow_rep"],
  ["satiety", "satiety"],
  ["mist", "mist_wit"],
  ["standing", "standing"],
  ["health", "health"],
  ["energy", "energy"],
];

function num(v) {
  if (v == null || v === "") return "—";
  const n = Number(v);
  return Number.isFinite(n) ? String(Math.round(n)) : "—";
}

export function paintStats() {
  const el = document.getElementById("island-stats");
  if (!el) return;
  const me = state.me || {};
  KEYS.forEach(([k, field]) => {
    const slot = el.querySelector(`[data-k="${k}"]`);
    if (slot) slot.textContent = num(me[field]);
  });
}

export function setStatsChip(on) {
  const el = document.getElementById("island-stats");
  if (!el) return;
  el.hidden = !on;
  if (on) {
    el.removeAttribute("hidden");
    paintStats();
  }
}
