import { api, loadKey } from "../api.js?v=farm-events1";
import { esc } from "./modal.js?v=island-modulefix2";

let panel = null;
let epoch = 0;
let timer = 0;

export function closeFarmEvents() {
  epoch++;
  clearTimeout(timer);
  if (panel) panel.remove();
  panel = null;
}

export function openFarmEvents(wrap, onSnapshot) {
  closeFarmEvents();
  const gen = epoch;
  const key = loadKey();
  panel = document.createElement("section");
  panel.className = "island-farm-events";
  panel.setAttribute("aria-label", "田间事件");
  wrap.append(panel);
  const host = panel;
  let data = null, busy = false, loading = false, notice = "", selection = null, revision = 0;
  const current = () => gen === epoch && key === loadKey() && host.isConnected;

  function draw() {
    if (!current()) return;
    const scroll = host.querySelector(".island-farm-event-list")?.scrollTop || 0;
    const rows = data?.incidents || [];
    host.innerHTML = `
      <header><h3>田间事件</h3><button type="button" data-close-events>返回</button></header>
      <p class="island-farm-event-note">和岛民 AI 共用记录。查看不会触发事件或扣费；处理费用另算，不退回当场损失。</p>
      <div class="island-farm-event-tools"><span>${data ? `口袋 ${esc(data.tickets)} 票` : "正在读取…"}</span><button type="button" data-refresh-events ${busy || loading || selection ? "disabled" : ""}>刷新</button></div>
      <p role="status">${esc(notice)}</p>
      <div class="island-farm-event-list">
      ${selection ? `<article><h4>确认处理 · ${esc(selection.row.label)}</h4><p>${esc(selection.label)}，只处理这一条意外。已经发生的损失不会返还。</p><button type="button" data-confirm-repair ${busy ? "disabled" : ""}>${busy ? "处理中…" : "确认处理"}</button><button type="button" data-cancel-repair ${busy ? "disabled" : ""}>先不忙</button></article>` : `
        <h4>待处理意外</h4>
        ${rows.map(row => `<article><h4>#${esc(row.id)} · ${esc(row.label)}</h4><p>${esc(row.detail)}</p><div class="island-farm-event-actions">
          <button type="button" data-repair="${esc(row.id)}" data-payment="tickets" ${row.can_pay_tickets ? "" : "disabled"}>花 ${esc(row.repair_tickets)} 票处理${row.can_pay_tickets ? "" : "（票不够）"}</button>
          ${row.repair_item ? `<button type="button" data-repair="${esc(row.id)}" data-payment="item" ${row.can_pay_item ? "" : "disabled"}>用${esc(row.repair_item_label)} ×${esc(row.repair_qty)}${row.can_pay_item ? "" : "（材料不够）"}</button>` : ""}
        </div></article>`).join("") || `<p>${data ? "目前没有待处理意外。" : "正在读取事件…"}</p>`}
        <h4>最近事件</h4><p class="island-farm-event-note">最近 20 条岛上意外与田间插曲；即时效果已经结算。旧的田间插曲没有留存正文，不会补造。</p>
        ${(data?.history || []).map(row => `<article><small>${esc(new Date(row.created_at * 1000).toLocaleString())}</small><p>${esc(row.text)}</p></article>`).join("") || "<p>暂时没有事件记录。</p>"}
      `}</div>`;
    host.querySelector("[data-close-events]").onclick = closeFarmEvents;
    host.querySelector("[data-refresh-events]").onclick = () => refresh();
    host.querySelectorAll("[data-repair]").forEach(button => {
      button.onclick = () => {
        const row = rows.find(r => String(r.id) === button.dataset.repair);
        if (!row || busy) return;
        selection = { row, payment: button.dataset.payment, label: button.dataset.payment === "item"
          ? `消耗${row.repair_item_label} ×${row.repair_qty}` : `花 ${row.repair_tickets} 票` };
        clearTimeout(timer);
        draw();
      };
    });
    const cancel = host.querySelector("[data-cancel-repair]");
    if (cancel) cancel.onclick = () => { selection = null; refresh(); };
    const confirm = host.querySelector("[data-confirm-repair]");
    if (confirm) confirm.onclick = repair;
    host.querySelector(".island-farm-event-list").scrollTop = scroll;
  }

  async function refresh() {
    if (!current() || loading || busy || selection) return;
    clearTimeout(timer);
    loading = true;
    const version = revision;
    draw();
    try {
      const result = await api.farmEvents();
      if (!current() || version !== revision) return;
      data = result;
      notice = "";
    } catch (error) {
      if (current() && version === revision) notice = error.message || "暂时没读到事件，点刷新重试。";
    } finally {
      loading = false;
      if (current()) {
        draw();
        timer = setTimeout(refresh, 10000);
      }
    }
  }

  async function repair() {
    if (!current() || busy || !selection) return;
    const choice = selection;
    revision++;
    busy = true;
    clearTimeout(timer);
    draw();
    try {
      const result = await api.repairFarmEvent(choice.row.id, choice.payment);
      if (!current()) return;
      data = result;
      notice = result.event?.narrative || "已处理。";
      if (onSnapshot) onSnapshot(result);
    } catch (error) {
      if (current()) notice = error.message || "没能确认结果，请刷新查看；已处理的事件不会再次扣费。";
    } finally {
      busy = false;
      selection = null;
      if (current()) {
        draw();
        timer = setTimeout(refresh, 10000);
      }
    }
  }
  refresh();
}
