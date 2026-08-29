import { homePlots, selectedPlot, state } from "../store.js";
import { esc } from "../ui/modal.js";

export function renderHome(root, { onSelect, onSow, onWater, onLook, onHarvest, onBack }) {
  const plots = homePlots();
  root.innerHTML = `
    <div class="island-home">
      <div class="island-home-sky"></div>
      <div class="island-farmer" aria-hidden="true"><div class="head"></div><div class="body"></div></div>
      <div class="island-plots">
        ${plots.slice(0, 3).map(plotHtml).join("") || "<p style='padding:16px'>还看不见份地。</p>"}
      </div>
    </div>
  `;
  root.querySelectorAll("[data-slot]").forEach((btn) => {
    btn.addEventListener("click", () => onSelect(btn.getAttribute("data-slot")));
  });
  const bar = document.getElementById("island-actionbar");
  const plot = selectedPlot();
  const seeds = (state.me && state.me.seeds) || [];
  const seed = seeds.find((s) => !s.tree) || seeds[0];
  bar.innerHTML = `
    <button type="button" class="island-btn" data-act="back">回地图</button>
    <button type="button" class="island-btn" data-act="look" ${plot ? "" : "disabled"}>查看</button>
    <button type="button" class="island-btn primary" data-act="sow" ${plot && plot.can_sow && seed ? "" : "disabled"}>播种</button>
    <button type="button" class="island-btn" data-act="water" ${plot && plot.can_water ? "" : "disabled"}>浇水</button>
    <button type="button" class="island-btn primary" data-act="harvest" ${plot && plot.can_harvest ? "" : "disabled"}>收获</button>
  `;
  bar.querySelector("[data-act=back]").addEventListener("click", onBack);
  bar.querySelector("[data-act=look]").addEventListener("click", () => plot && onLook(plot));
  bar.querySelector("[data-act=sow]").addEventListener("click", () => {
    if (!plot || !seed) return;
    onSow(plot.slot, seed.name || seed.crop);
  });
  bar.querySelector("[data-act=water]").addEventListener("click", () => plot && onWater(plot.slot));
  bar.querySelector("[data-act=harvest]").addEventListener("click", () => plot && onHarvest(plot.slot));
}

function plotHtml(p) {
  const on = String(state.selectedSlot) === String(p.slot) ? " is-on" : "";
  return `
    <button type="button" class="island-plot${on}" data-slot="${esc(p.slot)}">
      <span class="meta">${esc(p.token || p.slot)} · ${esc(p.name || "空地")}<br>${esc(p.detail || "")}</span>
      <span class="crop ${esc(p.appearance || "empty")}"></span>
    </button>
  `;
}
