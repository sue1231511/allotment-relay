import { setStatsChip } from "./stats.js?v=island-stats2";

function revealChipSrc(btn) {
  const img = btn && btn.querySelector("img[data-src]");
  if (!img || img.getAttribute("src")) return;
  img.src = img.getAttribute("data-src");
}

export function setBagChip(on) {
  const btn = document.getElementById("island-bag-chip");
  if (!btn) return;
  btn.hidden = !on;
  if (on) {
    btn.removeAttribute("hidden");
    revealChipSrc(btn);
  }
}

export function setBackChip(on, onBack) {
  const btn = document.getElementById("island-back-chip");
  if (!btn) return;
  btn.hidden = !on;
  if (on) {
    btn.removeAttribute("hidden");
    revealChipSrc(btn);
  }
  btn.onclick = on && typeof onBack === "function" ? onBack : null;
  setStatsChip(on);
}
