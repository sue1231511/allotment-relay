import { state } from "../store.js?v=island-climate1";
import { esc } from "./modal.js?v=island-climate1";
import { popIn, popOut } from "./pop.js?v=island-climate1";

const WEATHER_CODE = { 晴朗: "clear", 海雾: "misty", 阵风: "gale" };
const TIDE_CODE = { 退潮: "ebb", 平潮: "slack", 涨潮: "flood" };
const PHASE_CODE = { 昼: "day", 暮: "dusk", 夜: "night" };

export function climateOf() {
  const w = state.world || {};
  const weather = w.weather || "—";
  const tide = w.tide || "—";
  const phase = w.phase || "—";
  return {
    weather,
    weather_code: w.weather_code || WEATHER_CODE[weather] || "",
    tide,
    tide_code: w.tide_code || TIDE_CODE[tide] || "",
    phase,
    phase_code: w.phase_code || PHASE_CODE[phase] || "",
    season: w.season || "—",
    season_left: w.season_left || "",
    weather_hint: w.weather_hint || "",
    tide_hint: w.tide_hint || "",
    phase_hint: w.phase_hint || "",
    season_hint: w.season_hint || "",
  };
}

export function climatePanelHtml(c, { closeable = false } = {}) {
  const left = c.season_left ? `一周一季 · 还剩 ${esc(c.season_left)} 天` : "一周一季";
  const note = c.weather_hint || c.season_hint || "";
  return `
    <section class="island-climate is-${esc(c.phase_code || "day")}" role="dialog" aria-label="天气潮汐时辰季节" style="background-image:url('/static/island/assets/climate-frame.png')">
      ${closeable ? `<button type="button" class="island-climate-x" data-climate-close aria-label="关闭"></button>` : ""}
      <h2 class="island-climate-title">${esc(c.season)}</h2>
      <p class="island-climate-sub">${esc(left)}</p>
      <div class="island-climate-grid">
        <div class="island-climate-cell" data-k="weather">
          <small>天气</small>
          <b>${esc(c.weather)}</b>
        </div>
        <div class="island-climate-cell" data-k="tide">
          <small>潮汐</small>
          <b>${esc(c.tide)}</b>
        </div>
        <div class="island-climate-cell" data-k="phase">
          <small>时辰</small>
          <b>${esc(c.phase)}</b>
        </div>
        <div class="island-climate-cell" data-k="season">
          <small>季节</small>
          <b>${esc(c.season)}</b>
        </div>
      </div>
      <p class="island-climate-note">${esc(note)}</p>
    </section>
  `;
}

export function renderNotice(root) {
  const c = climateOf();
  root.innerHTML = `
    <div class="island-notice">
      ${climatePanelHtml(c)}
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  if (!bar) return;
  bar.innerHTML = "";
  bar.hidden = true;
}

export function showClimateSheet(sheet, { onClose } = {}) {
  const c = climateOf();
  const already = sheet.classList.contains("is-climate") && !sheet.hidden;
  sheet.classList.add("is-climate");
  document.body.classList.add("is-climate-open");
  sheet.innerHTML = climatePanelHtml(c, { closeable: true });
  if (already) sheet.hidden = false;
  else popIn(sheet);
  sheet.querySelectorAll("[data-climate-close]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      hideClimateSheet(sheet, onClose);
    });
  });
  sheet.addEventListener("click", (ev) => {
    if (ev.target === sheet) hideClimateSheet(sheet, onClose);
  }, { once: true });
}

export function hideClimateSheet(sheet, onClose) {
  if (!sheet) return;
  const finish = () => {
    sheet.classList.remove("is-climate");
    document.body.classList.remove("is-climate-open");
    sheet.innerHTML = "";
    if (typeof onClose === "function") onClose();
  };
  if (sheet.hidden) {
    finish();
    return;
  }
  popOut(sheet, finish);
}

export function paintClimateChip() {
  const btn = document.getElementById("island-climate-chip");
  if (!btn) return;
  const c = climateOf();
  const season = btn.querySelector("[data-climate-season]");
  const weather = btn.querySelector("[data-climate-weather]");
  if (season) season.textContent = c.season || "—";
  if (weather) weather.textContent = c.weather || "—";
  btn.setAttribute("aria-label", `天气 ${c.weather}，季节 ${c.season}。点开潮汐木牌。`);
}

export function setClimateChip(on) {
  const btn = document.getElementById("island-climate-chip");
  if (!btn) return;
  btn.hidden = !on;
  if (on) {
    btn.removeAttribute("hidden");
    paintClimateChip();
  }
}
