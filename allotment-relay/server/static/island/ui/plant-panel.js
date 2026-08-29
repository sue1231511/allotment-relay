import { panelCrops, panelSubtitle, state } from "../store.js";
import { esc } from "./modal.js";

const ART = {
  kale: `<svg viewBox="0 0 80 80" aria-hidden="true"><ellipse cx="40" cy="48" rx="22" ry="16" fill="#9bb88a"/><ellipse cx="28" cy="42" rx="14" ry="12" fill="#b7cda3"/><ellipse cx="52" cy="42" rx="14" ry="12" fill="#86a576"/><ellipse cx="40" cy="36" rx="12" ry="10" fill="#cfe0be"/><circle cx="40" cy="44" r="6" fill="#e8f0dc"/></svg>`,
  beet: `<svg viewBox="0 0 80 80" aria-hidden="true"><path d="M40 18c2 10 6 16 6 16s-4 0-6 4c-2-4-6-4-6-4s4-6 6-16z" fill="#7d9a6c"/><path d="M40 34c14 4 18 22 8 30-8 6-20 4-24-6-4-12 6-26 16-24z" fill="#d08a4a"/><path d="M36 40c6 2 10 10 6 16" stroke="#e8b57a" stroke-width="2" fill="none"/></svg>`,
  fogpea: `<svg viewBox="0 0 80 80" aria-hidden="true"><ellipse cx="40" cy="46" rx="16" ry="14" fill="#c45b4a"/><ellipse cx="34" cy="40" rx="5" ry="4" fill="#e7a197"/><path d="M40 22c1 8 8 12 8 12" stroke="#7d9a6c" stroke-width="3" fill="none" stroke-linecap="round"/><circle cx="50" cy="22" r="5" fill="#86a576"/></svg>`,
};

export function renderPlantPanel(root, { onSelect, onPlant, onClose }) {
  const crops = panelCrops();
  const selected = crops.find((c) => c.key === state.plantKey) || crops[0];
  if (selected) state.plantKey = selected.key;
  const full = firstIdleMissing();
  root.hidden = false;
  root.innerHTML = `
    <section class="island-plant-card" role="dialog" aria-label="种植">
      <header class="island-plant-head">
        <div>
          <h2>种植</h2>
          <p id="island-plant-sub">${esc(panelSubtitle())}</p>
        </div>
        <button type="button" class="island-plant-x" data-act="close" aria-label="关闭">×</button>
      </header>
      <div class="island-plant-grid">
        ${crops.map((crop) => cropTile(crop, selected)).join("")}
      </div>
      <div class="island-plant-meta">
        <span>成熟时间 ${esc(selected ? selected.grow_text : "—")}</span>
        <span>预计收获 ${esc(selected ? `${selected.yield}棵` : "—")}</span>
      </div>
      <button type="button" class="island-plant-go" data-act="plant" ${selected ? "" : "disabled"}>
        ${selected ? `种下${esc(selected.label)}` : "选择作物"}
      </button>
    </section>
  `;
  root.querySelectorAll("[data-crop]").forEach((btn) => {
    btn.addEventListener("click", () => onSelect(btn.getAttribute("data-crop")));
  });
  root.querySelector("[data-act=close]").addEventListener("click", onClose);
  root.querySelector("[data-act=plant]").addEventListener("click", () => {
    if (full) {
      onPlant(null);
      return;
    }
    if (selected) onPlant(selected);
  });
}

function firstIdleMissing() {
  const plots = (state.farm && state.farm.home) || [];
  return !plots.some((p) => p.can_sow);
}

function cropTile(crop, selected) {
  const on = selected && selected.key === crop.key ? " is-on" : "";
  const art = ART[crop.key] || ART.kale;
  return `
    <button type="button" class="island-crop${on}" data-crop="${esc(crop.key)}">
      ${on ? `<span class="island-crop-check" aria-hidden="true">✓</span>` : ""}
      <span class="island-crop-art">${art}</span>
      <b>${esc(crop.label)}</b>
      <small>${esc(crop.name)}种 ×${esc(crop.seed_qty)}</small>
    </button>
  `;
}

export function hidePlantPanel(root) {
  if (!root) return;
  root.hidden = true;
  root.innerHTML = "";
}
