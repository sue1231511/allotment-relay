import { api } from "../api.js?v=dates2";
import { esc, toast } from "./modal.js?v=island-modulefix2";

let navigate, scene = "map", rows = [], timer = 0, loading = false, openId = 0, busy = false;
let chip, panel, painted = "";
let sessionEpoch = 0;
let panelOpen = false, loaded = false, loadError = "";

function matches(row) {
  return row.scene === scene || (row.scene === "shore" && scene === "beach") || (row.scene === "theater" && scene === "hall");
}

export function mountDates(enterScene) {
  if (chip) return;
  navigate = enterScene;
  chip = document.getElementById("island-date-chip");
  if (!chip) return;
  chip.hidden = true;
  panel = document.createElement("section");
  panel.id = "island-date-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", "共同出游");
  panel.hidden = true;
  document.body.append(panel);
  chip.addEventListener("click", async () => {
    if (chip.disabled || busy) return;
    const epoch = sessionEpoch;
    chip.disabled = true;
    try {
      const row = rows.find(d => ["pending", "active"].includes(d.status)) || rows[0];
      if (row && row.status === "pending" && !matches(row)) await navigate(row.scene);
      if (epoch !== sessionEpoch) return;
      openId = row ? row.id : 0;
      panelOpen = true;
      painted = "";
      paint();
      refresh();
    } catch (err) { toast(err.message || "约会面板暂时没能打开，请重试。"); }
    finally { chip.disabled = false; }
  });
  panel.addEventListener("keydown", ev => {
    if (ev.key === "Escape" && !busy) close();
    if (ev.key === "Tab") {
      const controls = [...panel.querySelectorAll("button:not(:disabled), summary")];
      if (!controls.length) return;
      const first = controls[0], last = controls[controls.length - 1];
      if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); }
      else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); }
    }
  });
  panel.addEventListener("click", async ev => {
    if (ev.target.closest("[data-date-close]") && !busy) close();
    if (ev.target.closest("[data-date-refresh]") && !busy) { refresh(); return; }
    const history = ev.target.closest("[data-date-open]");
    if (history) { openId = Number(history.dataset.dateOpen); painted = ""; paint(); }
    const response = ev.target.closest("[data-date-respond]");
    if (!response || busy) return;
    busy = true;
    const epoch = sessionEpoch;
    panel.querySelectorAll("button").forEach(btn => { btn.disabled = true; });
    try {
      const data = await api.dateRespond(openId, scene, response.dataset.dateRespond === "yes");
      if (epoch !== sessionEpoch) return;
      rows = data.dates || [];
      painted = "";
    } catch (err) { toast(err.message || "暂时没能应邀，请重试。"); }
    finally { busy = false; painted = ""; paint(); }
  });
}

function close() {
  panelOpen = false;
  openId = 0;
  panel.hidden = true;
  chip.setAttribute("aria-expanded", "false");
  document.body.classList.remove("is-date-open");
  chip.focus();
}

export function dateSceneChanged(name) {
  scene = name;
  if (panelOpen) close();
  paint();
  refresh();
}

export function resetDates() {
  sessionEpoch++;
  rows = [];
  openId = 0;
  panelOpen = false;
  loaded = false;
  loadError = "";
  painted = "";
  if (chip) { chip.hidden = true; chip.setAttribute("aria-expanded", "false"); }
  if (panel) panel.hidden = true;
  document.body.classList.remove("is-date-open");
}

async function refresh() {
  if (!chip || loading) return;
  clearTimeout(timer);
  if (!document.body.classList.contains("is-playing")) {
    resetDates();
    timer = setTimeout(refresh, 10000);
    return;
  }
  loading = true;
  const epoch = sessionEpoch;
  try {
    if (!document.hidden) {
      const data = await api.dates();
      if (epoch !== sessionEpoch) return;
      rows = data.dates || [];
      loaded = true;
      loadError = "";
      paint();
    }
  } catch (err) {
    if (epoch !== sessionEpoch) return;
    if (err.status === 401 || err.status === 403) resetDates();
    else { loadError = "暂时没能读取约会，请稍后刷新。"; paint(); }
    // 暂时断网不影响地图其他玩法；下次自动刷新。
  }
  finally { loading = false; timer = setTimeout(refresh, panelOpen ? 2500 : 10000); }
}

function cardMarkup(card, choice) {
  if (!card) return "";
  return `<article class="date-chapter"><small class="date-narrator">${card.kind === "event" ? "导演旁白 · 特别事件" : "导演旁白"}</small><h3>${esc(card.title)}</h3><p>${esc(card.narrative)}</p>
    ${choice ? `<p class="date-receipt">岛民选择：${esc(choice.label)} · ${esc(choice.name)} ${choice.cost} 票</p>` : ""}</article>`;
}

function paint() {
  if (!chip) return;
  const live = rows.find(d => ["pending", "active"].includes(d.status));
  chip.hidden = !document.body.classList.contains("is-playing");
  const label = live ? (live.status === "pending" ? `约会 · ${live.place}待应邀` : `约会 · ${live.place} 第${live.seq}幕`) : "约会 · 邀请与共同回忆";
  chip.setAttribute("aria-label", label);
  chip.title = label;
  chip.querySelector(".island-date-badge").hidden = !live;
  if (!panelOpen || busy || chip.hidden) return;
  const row = rows.find(d => d.id === openId) || live || rows[0];
  openId = row ? row.id : 0;
  const signature = JSON.stringify({ row, loadError, loaded }) + scene;
  if (signature === painted) return;
  painted = signature;
  if (!row) {
    showPanel(`<div class="date-paper"><header><small>TOGETHER · 约会</small><button type="button" data-date-close aria-label="收起共同出游">收起 ×</button></header>
      <h2>约会 · 一起出去走走</h2><p role="status">${loadError ? esc(loadError) : loaded ? "还没有约会邀请或共同出游记录。" : "正在读取约会邀请与进度…"}</p>
      <p>让岛民先发起地点约会，你再到对应地点应邀。之后在这里看旁白、特别事件和共同回忆，行动由岛民决定。</p>
      <p class="date-receipt">打开面板和刷新不会发起约会、生成剧情或扣票。</p><button type="button" data-date-refresh>刷新旁白与进度</button></div>`);
    return;
  }
  const card = row.current;
  showPanel(`<div class="date-paper"><header><small>TOGETHER · ${esc(row.status_label)}</small>
    <button type="button" data-date-close aria-label="收起共同出游">收起 ×</button></header>
    <h2>${esc(row.kind_label)} · ${esc(row.place)}</h2>
    <p class="date-receipt">已花 ${row.total_spent} 工分票${row.special ? " · 婚礼周年纪念日" : ""}</p>
    ${row.note ? `<blockquote>${esc(row.note)}</blockquote>` : ""}
    ${row.status === "pending" ? `<p>岛民已经安排好这一程。你应邀后，岛民会带着你经历剧情、选择和特别事件。</p>
      ${matches(row) ? `<div class="date-response"><button type="button" data-date-respond="yes">应邀，一起走</button><button type="button" data-date-respond="no">这次先不去</button></div>` : `<p>请到${esc(row.place)}应邀。</p>`}
      <p class="date-receipt">邀请七天有效。预订费已付，拒绝或过期不另扣票，也不退预订费。</p>` : ""}
    ${row.history.length ? `<details><summary>翻看走过的 ${row.history.length} 幕</summary>${row.history.map(c => cardMarkup(c, c.choice)).join("")}</details>` : ""}
    ${cardMarkup(card)}
    ${row.status === "active" ? `${!row.generating && row.director_error ? `<p class="date-error" role="status">这次没有生成新旁白：${esc(row.director_error)}</p>` : ""}
      <p class="date-wait">${row.generating ? "已受理，导演正在服务端后台写这一幕。不用反复继续；已有旁白会保留，写好后自动显示。" : !card ? "还没有第一幕旁白。应邀已完成，请让岛民发起第一幕；刷新这里只查看进度，不会开始生成。" : card.options.length ? "岛民正在决定下一步，也可以通过 MCP 自定义行动，选好会自动更新。" : "这一幕旁白已写好。等岛民继续、自定义行动或结束这一程。"}</p>
      <button type="button" data-date-refresh>刷新旁白与进度</button>
      ${card && card.options.length ? `<ul class="date-options">${card.options.map(o => `<li><b>${esc(o.label)}</b><small>${esc(o.name)} · ${o.cost} 票</small></li>`).join("")}</ul>` : ""}` : ""}
    ${!["pending", "active"].includes(row.status) ? `<p>这一程已记下。纪念不进背包，不产生可回本资源。</p>` : ""}
    <details class="date-archive"><summary>其他共同出游</summary>${rows.filter(d => d.id !== row.id).map(d => `<button type="button" data-date-open="${d.id}">${esc(d.title)} · ${esc(d.status_label)}</button>`).join("") || "还没有其他记录"}</details>
    </div>`);
}

function showPanel(markup) {
  const firstOpen = panel.hidden;
  panel.innerHTML = markup;
  panel.hidden = false;
  chip.setAttribute("aria-expanded", "true");
  document.body.classList.add("is-date-open");
  if (firstOpen) panel.querySelector("[data-date-close]").focus();
}
