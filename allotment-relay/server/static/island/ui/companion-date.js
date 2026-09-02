import { api } from "../api.js?v=dates2";
import { esc, toast } from "./modal.js?v=island-modulefix2";

let navigate, scene = "map", rows = [], timer = 0, loading = false, openId = 0, busy = false;
let chip, panel, painted = "";
let sessionEpoch = 0;

function matches(row) {
  return row.scene === scene || (row.scene === "shore" && scene === "beach") || (row.scene === "theater" && scene === "hall");
}

export function mountDates(enterScene) {
  if (chip) return;
  navigate = enterScene;
  chip = document.createElement("button");
  chip.type = "button";
  chip.id = "island-date-chip";
  chip.hidden = true;
  document.body.append(chip);
  panel = document.createElement("section");
  panel.id = "island-date-panel";
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-modal", "true");
  panel.setAttribute("aria-label", "共同出游");
  panel.hidden = true;
  document.body.append(panel);
  chip.addEventListener("click", async () => {
    const row = rows.find(d => ["pending", "active"].includes(d.status)) || rows[0];
    if (!row) return;
    if (row.status === "pending" && !matches(row)) await navigate(row.scene);
    openId = row.id;
    painted = "";
    paint();
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
  openId = 0;
  panel.hidden = true;
  document.body.classList.remove("is-date-open");
  chip.focus();
}

export function dateSceneChanged(name) {
  scene = name;
  if (openId) close();
  refresh();
}

export function resetDates() {
  sessionEpoch++;
  rows = [];
  openId = 0;
  painted = "";
  if (chip) chip.hidden = true;
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
      paint();
    }
  } catch (err) {
    if (err.status === 401 || err.status === 403) resetDates();
    // 暂时断网不影响地图其他玩法；下次自动刷新。
  }
  finally { loading = false; timer = setTimeout(refresh, 10000); }
}

function cardMarkup(card, choice) {
  if (!card) return "";
  return `<article class="date-chapter"><h3>${esc(card.title)}</h3><p>${esc(card.narrative)}</p>
    ${choice ? `<p class="date-receipt">岛民选择：${esc(choice.label)} · ${esc(choice.name)} ${choice.cost} 票</p>` : ""}</article>`;
}

function paint() {
  if (!chip) return;
  const live = rows.find(d => ["pending", "active"].includes(d.status));
  chip.hidden = !rows.length;
  chip.textContent = live ? (live.status === "pending" ? `有约 · ${live.place}应邀` : `同行 · ${live.place} 第${live.seq}幕`) : "共同出游 · 回忆";
  if (!openId || busy) return;
  const row = rows.find(d => d.id === openId);
  if (!row) { close(); return; }
  const signature = JSON.stringify(row) + scene;
  if (signature === painted) return;
  painted = signature;
  const firstOpen = panel.hidden;
  const card = row.current;
  panel.innerHTML = `<div class="date-paper"><header><small>TOGETHER · ${esc(row.status_label)}</small>
    <button type="button" data-date-close aria-label="收起共同出游">收起 ×</button></header>
    <h2>${esc(row.kind_label)} · ${esc(row.place)}</h2>
    <p class="date-receipt">已花 ${row.total_spent} 工分票${row.special ? " · 婚礼周年纪念日" : ""}</p>
    ${row.note ? `<blockquote>${esc(row.note)}</blockquote>` : ""}
    ${row.status === "pending" ? `<p>岛民已经安排好这一程。你应邀后，岛民会带着你经历剧情、选择和特别事件。</p>
      ${matches(row) ? `<div class="date-response"><button type="button" data-date-respond="yes">应邀，一起走</button><button type="button" data-date-respond="no">这次先不去</button></div>` : `<p>请到${esc(row.place)}应邀。</p>`}
      <p class="date-receipt">邀请七天有效。预订费已付，拒绝或过期不另扣票，也不退预订费。</p>` : ""}
    ${row.history.length ? `<details><summary>翻看走过的 ${row.history.length} 幕</summary>${row.history.map(c => cardMarkup(c, c.choice)).join("")}</details>` : ""}
    ${cardMarkup(card)}
    ${row.status === "active" ? `<p class="date-wait">${row.generating ? "导演正在写下一幕…" : card && card.options.length ? "岛民正在决定下一步，选好会自动更新在这里。" : "已应邀，等岛民继续这一程。"}</p>
      ${card && card.options.length ? `<ul class="date-options">${card.options.map(o => `<li><b>${esc(o.label)}</b><small>${esc(o.name)} · ${o.cost} 票</small></li>`).join("")}</ul>` : ""}` : ""}
    ${!["pending", "active"].includes(row.status) ? `<p>这一程已记下。纪念不进背包，不产生可回本资源。</p>` : ""}
    <details class="date-archive"><summary>其他共同出游</summary>${rows.filter(d => d.id !== row.id).map(d => `<button type="button" data-date-open="${d.id}">${esc(d.title)} · ${esc(d.status_label)}</button>`).join("") || "还没有其他记录"}</details>
    </div>`;
  panel.hidden = false;
  document.body.classList.add("is-date-open");
  if (firstOpen) panel.querySelector("[data-date-close]").focus();
}
