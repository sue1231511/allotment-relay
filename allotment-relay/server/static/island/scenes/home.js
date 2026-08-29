import { growStatusLine, panelSubtitle, ripeHome } from "../store.js";
import { esc } from "../ui/modal.js";

export function renderHome(root, { onOpenGarden, onHarvestAll, onBack }) {
  const ripe = ripeHome().length;
  root.innerHTML = `
    <div class="island-home">
      <p class="island-grow-status" id="island-grow-status">${esc(growStatusLine())}</p>
      <button type="button" class="island-garden-hot" data-act="garden" aria-label="打开种植面板"></button>
      <button type="button" class="island-harvest-fab" id="island-harvest-all" data-act="harvest" ${ripe ? "" : "hidden"}>一键收获</button>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  bar.innerHTML = `
    <button type="button" class="island-btn" data-act="back">回地图</button>
    <button type="button" class="island-btn primary" data-act="garden">种植</button>
  `;
  root.querySelector("[data-act=garden]").addEventListener("click", onOpenGarden);
  const harvest = root.querySelector("[data-act=harvest]");
  if (harvest) harvest.addEventListener("click", onHarvestAll);
  bar.querySelector("[data-act=back]").addEventListener("click", onBack);
  bar.querySelector("[data-act=garden]").addEventListener("click", onOpenGarden);
}

export function syncHomeChrome() {
  const status = document.getElementById("island-grow-status");
  if (status) status.textContent = growStatusLine();
  const harvest = document.getElementById("island-harvest-all");
  if (harvest) harvest.hidden = ripeHome().length === 0;
  const sub = document.getElementById("island-plant-sub");
  if (sub) sub.textContent = panelSubtitle();
}
