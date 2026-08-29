import { neighborCrop, cropArt } from "./crops.js";
import { firstIdleYard, panelCrops, panelSubtitle, state, yardMeta } from "../store.js";
import { esc } from "./modal.js";

export function renderPlantPanel(root, { onSelect, onPlant, onClose }) {
  const crops = panelCrops();
  const selected = crops.find((c) => c.key === state.plantKey) || crops[0];
  if (selected) state.plantKey = selected.key;
  const idle = firstIdleYard();
  const meta = yardMeta();
  const prev = neighborCrop(crops, state.plantKey, -1);
  const next = neighborCrop(crops, state.plantKey, 1);
  root.hidden = false;
  root.innerHTML = `
    <section class="island-plant-card" role="dialog" aria-label="${esc(meta.plant)}">
      <header class="island-plant-head">
        <div>
          <h2>${esc(meta.plant)}</h2>
          <p id="island-plant-sub">${esc(panelSubtitle())}</p>
        </div>
        <button type="button" class="island-plant-x" data-act="close" aria-label="关闭">×</button>
      </header>
      <div class="island-plant-pick" id="island-plant-pick">
        <button type="button" class="island-plant-arrow" data-act="prev" aria-label="上一种">‹</button>
        <div class="island-plant-hero">
          <span class="island-crop-art is-lg">${selected ? cropArt(selected.key, "ripe") : ""}</span>
          <b>${esc(selected ? selected.label : "—")}</b>
          <small>${esc(selected ? `${selected.name}种 ×${selected.seed_qty}` : "")}</small>
        </div>
        <button type="button" class="island-plant-arrow" data-act="next" aria-label="下一种">›</button>
      </div>
      <p class="island-plant-index">${crops.length ? `${crops.findIndex((c) => c.key === state.plantKey) + 1} / ${crops.length}` : "0 / 0"}</p>
      <div class="island-plant-meta">
        <span>成熟时间 ${esc(selected ? selected.grow_text : "—")}</span>
        <span>预计收获 ${esc(selected ? `${selected.yield}棵` : "—")}</span>
      </div>
      <button type="button" class="island-plant-go" data-act="plant" ${selected && selected.seed_qty > 0 ? "" : "disabled"}>
        ${!selected ? "选择作物" : selected.seed_qty > 0 ? `种下${esc(selected.label)}` : `没有${esc(selected.label)}种`}
      </button>
    </section>
  `;
  root.querySelector("[data-act=close]").addEventListener("click", onClose);
  root.querySelector("[data-act=prev]").addEventListener("click", () => prev && onSelect(prev));
  root.querySelector("[data-act=next]").addEventListener("click", () => next && onSelect(next));
  root.querySelector("[data-act=plant]").addEventListener("click", () => {
    if (!idle) {
      onPlant(null);
      return;
    }
    if (selected) onPlant(selected);
  });
  bindSwipe(root.querySelector("#island-plant-pick"), {
    onLeft: () => next && onSelect(next),
    onRight: () => prev && onSelect(prev),
  });
}

function bindSwipe(el, { onLeft, onRight }) {
  if (!el) return;
  let x0 = 0;
  el.addEventListener("touchstart", (ev) => {
    x0 = ev.changedTouches[0].clientX;
  }, { passive: true });
  el.addEventListener("touchend", (ev) => {
    const dx = ev.changedTouches[0].clientX - x0;
    if (dx > 40) onRight();
    if (dx < -40) onLeft();
  }, { passive: true });
}

export function hidePlantPanel(root) {
  if (!root) return;
  root.hidden = true;
  root.innerHTML = "";
}
