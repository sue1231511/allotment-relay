import { state } from "../store.js?v=island-mapbgm1";
import { esc } from "./modal.js?v=island-climate4";
import { popIn, popOut } from "./pop.js?v=island-climate4";

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
  return `
    <section class="island-climate is-${esc(c.phase_code || "day")}" role="dialog" aria-label="天气潮汐时辰季节" style="background-image:url('/static/island/assets/climate-frame.png')">
      ${closeable ? `<button type="button" class="island-climate-x" data-climate-close aria-label="关闭"></button>` : ""}
      <span class="island-climate-lab" data-k="weather">天气</span>
      <span class="island-climate-lab" data-k="tide">潮汐</span>
      <span class="island-climate-lab" data-k="phase">时辰</span>
      <span class="island-climate-lab" data-k="season">季节</span>
      <b class="island-climate-val" data-k="weather">${esc(c.weather)}</b>
      <b class="island-climate-val" data-k="tide">${esc(c.tide)}</b>
      <b class="island-climate-val" data-k="phase">${esc(c.phase)}</b>
      <b class="island-climate-val" data-k="season">${esc(c.season)}</b>
    </section>
  `;
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
