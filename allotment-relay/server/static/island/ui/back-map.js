export function setBagChip(on) {
  const btn = document.getElementById("island-bag-chip");
  if (!btn) return;
  btn.hidden = !on;
  if (on) btn.removeAttribute("hidden");
}

export function setBackChip(on, onBack) {
  const btn = document.getElementById("island-back-chip");
  if (!btn) return;
  btn.hidden = !on;
  if (on) btn.removeAttribute("hidden");
  btn.onclick = on && typeof onBack === "function" ? onBack : null;
}
