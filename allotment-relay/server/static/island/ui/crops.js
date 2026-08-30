/** 作物图按 catalog.CROPS 顺序，文件在 /static/island/assets/crops/{key}.png */

const CROP_FALLBACK = {
  kale: "🥬",
  beet: "🥕",
  fogpea: "🍅",
  chili: "🌶️",
  garlic: "🧄",
  durian: "🌳",
  mango: "🥭",
  orange: "🍊",
};

export function cropArt(key, stage = "ripe") {
  if (!key || stage === "empty") return "";
  const cls = stage === "seedling" ? "is-seed" : stage === "growing" ? "is-grow" : "is-ripe";
  const fallback = CROP_FALLBACK[key] || "🌱";
  return `<img class="island-crop-pic ${cls}" src="/static/island/assets/crops/${key}.png" alt="" draggable="false" onerror="this.replaceWith(Object.assign(document.createElement('span'),{className:'island-crop-fallback',textContent:'${fallback}'}))">`;
}

export function neighborCrop(crops, key, delta) {
  if (!crops.length) return "";
  const i = Math.max(0, crops.findIndex((c) => c.key === key));
  return crops[(i + delta + crops.length * 10) % crops.length].key;
}
