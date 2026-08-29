import {
  formatRemain,
  growStatusLine,
  panelSubtitle,
  plotLabel,
  ripeYard,
  state,
  yardMeta,
  yardPlots,
  YARDS,
} from "../store.js";
import { cropArt } from "../ui/crops.js";
import { esc } from "../ui/modal.js";

export function renderHome(root, { onOpenLand, onBack }) {
  root.innerHTML = `
    <div class="island-home">
      <button type="button" class="island-garden-hot" data-act="land" aria-label="查看土地"></button>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  bar.innerHTML = `
    <button type="button" class="island-btn" data-act="back">回地图</button>
    <button type="button" class="island-btn primary" data-act="land">看土地</button>
  `;
  root.querySelector("[data-act=land]").addEventListener("click", onOpenLand);
  bar.querySelector("[data-act=back]").addEventListener("click", onBack);
  bar.querySelector("[data-act=land]").addEventListener("click", onOpenLand);
}

export function renderYards(root, { onOpenGarden, onHarvestAll, onSwitchYard, onBack }) {
  const ripe = ripeYard().length;
  root.innerHTML = `
    <div class="island-yards">
      <div class="island-yard-tabs" role="tablist" aria-label="地块类型">
        ${yardTabs()}
      </div>
      <p class="island-grow-status" id="island-grow-status">${esc(growStatusLine())}</p>
      <div class="island-plot-grid" id="island-plot-grid">${plotGridMarkup()}</div>
      <button type="button" class="island-harvest-fab" id="island-harvest-all" data-act="harvest" ${ripe ? "" : "hidden"}>${harvestLabel(ripe)}</button>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  bar.innerHTML = `
    <button type="button" class="island-btn" data-act="back">回家园</button>
    <button type="button" class="island-btn primary" data-act="garden">${esc(yardMeta().plant)}</button>
  `;
  root.querySelectorAll("[data-yard]").forEach((btn) => {
    btn.addEventListener("click", () => onSwitchYard(btn.getAttribute("data-yard")));
  });
  root.querySelectorAll("[data-act=garden]").forEach((btn) => {
    btn.addEventListener("click", onOpenGarden);
  });
  const harvest = root.querySelector("[data-act=harvest]");
  if (harvest) harvest.addEventListener("click", onHarvestAll);
  bar.querySelector("[data-act=back]").addEventListener("click", onBack);
  bar.querySelector("[data-act=garden]").addEventListener("click", onOpenGarden);
}

export function syncHomeChrome() {
  const status = document.getElementById("island-grow-status");
  if (status) status.textContent = growStatusLine();
  const harvest = document.getElementById("island-harvest-all");
  if (harvest) {
    const ripe = ripeYard().length;
    harvest.hidden = ripe === 0;
    harvest.textContent = harvestLabel(ripe);
  }
  const grid = document.getElementById("island-plot-grid");
  if (grid) grid.innerHTML = plotGridMarkup();
  document.querySelectorAll(".island-yard-tabs [data-yard]").forEach((btn) => {
    const kind = btn.getAttribute("data-yard");
    btn.classList.toggle("is-on", kind === state.yard);
    btn.setAttribute("aria-selected", kind === state.yard ? "true" : "false");
    const count = btn.querySelector("small");
    if (count) count.textContent = String(yardPlots(kind).length);
  });
  const plantBtn = document.querySelector("#island-actionbar [data-act=garden]");
  if (plantBtn) plantBtn.textContent = yardMeta().plant;
  const sub = document.getElementById("island-plant-sub");
  if (sub) sub.textContent = panelSubtitle();
}

function yardTabs() {
  return Object.values(YARDS).map((yard) => {
    const n = yardPlots(yard.key).length;
    const on = yard.key === state.yard;
    return `<button type="button" role="tab" class="${on ? "is-on" : ""}" data-yard="${esc(yard.key)}" aria-selected="${on ? "true" : "false"}">${esc(yard.label)} <small>${n}</small></button>`;
  }).join("");
}

function harvestLabel(ripe) {
  return ripe > 1 ? `一键收获 ${ripe}` : "一键收获";
}

const GRASS = "/static/island/assets/grass.png";
const PLOT = "/static/island/assets/plot.png";
const COLS = 3;

function plotGridMarkup() {
  const plots = yardPlots();
  const meta = yardMeta();
  if (!plots.length) {
    return `<p class="island-plot-empty">${esc(meta.empty)}</p>`;
  }
  const tiles = plots.map((plot) => {
    const stage = plot.appearance || (plot.can_sow ? "empty" : "growing");
    const art = cropArt(plot.crop, stage);
    const token = plotLabel(plot);
    return `<button type="button" class="island-plot-tile is-${esc(stage)}" data-act="garden" data-token="${esc(token)}" aria-label="${esc(token)}">
      <img class="island-plot-grass" src="${GRASS}" alt="" draggable="false">
      <img class="island-plot-bed" src="${PLOT}" alt="" draggable="false">
      <span class="island-plot-soil">${art}</span>
      <span class="island-plot-meta"><b>${esc(token)}</b><small>${esc(tileCaption(plot))}</small></span>
    </button>`;
  });
  const pad = (COLS - (plots.length % COLS)) % COLS;
  if (pad) tiles.push(grassPad(pad));
  return tiles.join("");
}

function grassPad(count) {
  return Array.from({ length: count }, () => (
    `<span class="island-plot-tile is-pad" aria-hidden="true"><img class="island-plot-grass" src="${GRASS}" alt="" draggable="false"></span>`
  )).join("");
}

function tileCaption(plot) {
  if (plot.state === "clearing") return plot.detail || "开垦中";
  if (plot.can_sow) return "空闲";
  if (plot.can_harvest) return "可收";
  if ((plot.remain_sec || 0) > 0) return formatRemain(plot.remain_sec);
  return plot.label || plot.name || "生长中";
}
