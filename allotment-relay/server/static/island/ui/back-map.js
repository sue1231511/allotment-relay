export function backChipMarkup() {
  return `<button type="button" class="island-back-chip" data-act="back">回地图</button>`;
}

export function bindBackChip(root, onBack) {
  const btn = root.querySelector(".island-back-chip");
  if (btn && typeof onBack === "function") btn.addEventListener("click", onBack);
}
