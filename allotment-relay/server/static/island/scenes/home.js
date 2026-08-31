import {
  formatRemain,
  growStatusLine,
  landSnap,
  panelSubtitle,
  plotLabel,
  plotToken,
  ripeYard,
  state,
  yardMeta,
  yardPlots,
  YARDS,
} from "../store.js?v=island-port1";
import { sceneArt } from "../ui/art.js?v=island-port1";
import { cropArt } from "../ui/crops.js?v=island-port1";
import { esc } from "../ui/modal.js?v=island-port1";

export function renderHome(root, { onOpenLand }) {
  root.innerHTML = `
    <div class="island-home">
      ${sceneArt("home")}
      <button type="button" class="island-garden-hot" data-act="land" aria-label="查看土地"></button>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
  root.querySelector("[data-act=land]").addEventListener("click", onOpenLand);
}

export function renderYards(root, { onTapPlot, onTapGrass, onHarvestAll, onSwitchYard }) {
  const ripe = ripeYard().length;
  root.innerHTML = `
    <div class="island-yards">
      ${sceneArt("yards")}
      <div class="island-yard-tabs" role="tablist" aria-label="地块类型">
        ${yardTabs()}
      </div>
      <p class="island-grow-status" id="island-grow-status">${esc(growStatusLine())}</p>
      <div class="island-plot-grid" id="island-plot-grid">${plotGridMarkup()}</div>
      <div class="island-plot-pager" id="island-plot-pager">${pagerMarkup()}</div>
      <button type="button" class="island-harvest-fab" id="island-harvest-all" data-act="harvest" ${ripe ? "" : "hidden"}>${harvestLabel(ripe)}</button>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
  root.querySelectorAll("[data-yard]").forEach((btn) => {
    btn.addEventListener("click", () => onSwitchYard(btn.getAttribute("data-yard")));
  });
  const harvest = root.querySelector("[data-act=harvest]");
  if (harvest) harvest.addEventListener("click", onHarvestAll);
  bindGrid(onTapPlot, onTapGrass);
  bindPager();
  bindSwipe();
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
  const pager = document.getElementById("island-plot-pager");
  if (pager) pager.innerHTML = pagerMarkup();
  document.querySelectorAll(".island-yard-tabs [data-yard]").forEach((btn) => {
    const kind = btn.getAttribute("data-yard");
    btn.classList.toggle("is-on", kind === state.yard);
    btn.setAttribute("aria-selected", kind === state.yard ? "true" : "false");
    const count = btn.querySelector("small");
    if (count) count.textContent = String(yardPlots(kind).length);
  });
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
const PAGE_SIZE = 9;

function pageCount() {
  const n = yardPlots().length;
  const filled = Math.ceil(n / PAGE_SIZE);
  const extra = (n % PAGE_SIZE === 0) ? 1 : 0;
  return Math.max(1, filled + extra);
}

function clampPage() {
  const last = pageCount() - 1;
  if (state.yardPage > last) state.yardPage = last;
  if (state.yardPage < 0) state.yardPage = 0;
}

function pagePlots() {
  clampPage();
  const plots = yardPlots();
  const start = state.yardPage * PAGE_SIZE;
  return plots.slice(start, start + PAGE_SIZE);
}

function plotGridMarkup() {
  const plots = pagePlots();
  const tiles = plots.map((plot) => {
    const stage = plot.appearance || (plot.can_sow ? "empty" : "growing");
    const art = cropArt(plot.crop, stage);
    const token = plotToken(plot);
    const label = plotLabel(plot);
    return `<button type="button" class="island-plot-tile is-${esc(stage)}" data-token="${esc(token)}" aria-label="${esc(label)}">
      <img class="island-plot-grass" src="${GRASS}" alt="" draggable="false">
      <img class="island-plot-bed" src="${PLOT}" alt="" draggable="false">
      <span class="island-plot-soil">${art}</span>
      <span class="island-plot-meta"><b>${esc(label)}</b><small>${esc(tileCaption(plot))}</small></span>
    </button>`;
  });
  const pad = PAGE_SIZE - plots.length;
  if (pad) tiles.push(grassPad(pad));
  return tiles.join("");
}

function pagerMarkup() {
  if (pageCount() <= 1) return "";
  clampPage();
  const pages = pageCount();
  const cur = state.yardPage + 1;
  return `
    <button type="button" class="island-btn" data-page="-1" ${state.yardPage <= 0 ? "disabled" : ""}>上一页</button>
    <span>${cur} / ${pages} · 左右滑</span>
    <button type="button" class="island-btn" data-page="1" ${state.yardPage >= pages - 1 ? "disabled" : ""}>下一页</button>
  `;
}

function turnPage(delta) {
  if (pageCount() <= 1) return false;
  const next = state.yardPage + delta;
  if (next < 0 || next >= pageCount()) return false;
  state.yardPage = next;
  syncHomeChrome();
  return true;
}

function bindGrid(onTapPlot, onTapGrass) {
  const grid = document.getElementById("island-plot-grid");
  if (!grid || grid._bound) return;
  grid._bound = true;
  grid.addEventListener("click", (ev) => {
    if (grid._ignoreClick) return;
    const grass = ev.target.closest("[data-act=expand]");
    if (grass) {
      if (onTapGrass) onTapGrass();
      return;
    }
    const tile = ev.target.closest("[data-token]");
    if (!tile) return;
    onTapPlot(tile.getAttribute("data-token"));
  });
}

function bindPager() {
  const pager = document.getElementById("island-plot-pager");
  if (!pager || pager._bound) return;
  pager._bound = true;
  pager.addEventListener("click", (ev) => {
    const btn = ev.target.closest("[data-page]");
    if (!btn || btn.disabled) return;
    turnPage(Number(btn.getAttribute("data-page")));
  });
}

function bindSwipe() {
  const grid = document.getElementById("island-plot-grid");
  if (!grid || grid._swiped) return;
  grid._swiped = true;
  let x0 = 0;
  let y0 = 0;
  let tracking = false;
  const start = (x, y) => {
    x0 = x;
    y0 = y;
    tracking = true;
  };
  const finish = (x, y) => {
    if (!tracking) return;
    tracking = false;
    const dx = x - x0;
    const dy = y - y0;
    if (Math.abs(dx) < 48 || Math.abs(dx) <= Math.abs(dy)) return;
    if (turnPage(dx < 0 ? 1 : -1)) {
      grid._ignoreClick = true;
      setTimeout(() => {
        grid._ignoreClick = false;
      }, 320);
    }
  };
  grid.addEventListener("touchstart", (ev) => {
    const t = ev.changedTouches[0];
    if (t) start(t.clientX, t.clientY);
  }, { passive: true });
  grid.addEventListener("touchend", (ev) => {
    const t = ev.changedTouches[0];
    if (t) finish(t.clientX, t.clientY);
  }, { passive: true });
  grid.addEventListener("pointerdown", (ev) => {
    if (ev.pointerType === "touch") return;
    start(ev.clientX, ev.clientY);
  });
  grid.addEventListener("pointerup", (ev) => {
    if (ev.pointerType === "touch") return;
    finish(ev.clientX, ev.clientY);
  });
}

function grassPad(count) {
  const cap = grassCaption();
  return Array.from({ length: count }, () => (
    `<button type="button" class="island-plot-tile is-pad" data-act="expand" aria-label="开垦草地">
      <img class="island-plot-grass" src="${GRASS}" alt="" draggable="false">
      <span class="island-plot-meta"><b>草地</b><small>${esc(cap)}</small></span>
    </button>`
  )).join("");
}

function grassCaption() {
  const snap = landSnap();
  if (snap && snap.clearing) return snap.clearing_eta || "开垦中";
  if (snap && snap.offer && snap.offer.cost != null) return `${snap.offer.cost} 票`;
  return "开垦";
}

function tileCaption(plot) {
  if (plot.state === "clearing") return plot.detail || "开垦中";
  if (plot.can_sow) return "空闲";
  if (plot.can_harvest) return "可收";
  if ((plot.remain_sec || 0) > 0) return formatRemain(plot.remain_sec);
  return plot.label || plot.name || "生长中";
}
