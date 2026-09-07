import { api } from "../api.js?v=hearts1";
import { toast } from "./modal.js?v=island-modulefix2";

let chip, badge, panel, snap = null, timer = 0, busy = false;

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  })[c]);
}

export function mountHearts() {
  chip = document.getElementById("island-heart-chip");
  badge = document.getElementById("island-heart-badge");
  if (!chip) return;
  panel = document.createElement("section");
  panel.id = "island-heart-panel";
  panel.hidden = true;
  panel.setAttribute("role", "dialog");
  panel.setAttribute("aria-label", "日常心意");
  document.body.append(panel);
  chip.addEventListener("click", async () => {
    panel.hidden = false;
    await refresh();
    paint();
  });
  refresh();
  timer = window.setInterval(refresh, 20000);
}

export function resetHearts() {
  if (timer) clearInterval(timer);
  timer = 0;
  snap = null;
  if (chip) chip.hidden = true;
  if (panel) panel.hidden = true;
}

async function refresh() {
  try {
    snap = await api.hearts();
    const n = (snap.pending || []).length;
    if (chip) chip.hidden = false;
    if (badge) {
      badge.hidden = n <= 0;
      badge.textContent = String(n);
    }
    if (panel && !panel.hidden) paint();
  } catch {
    /* 未登录等 */
  }
}

function paint() {
  if (!panel || !snap) return;
  const pending = snap.pending || [];
  const album = snap.album || [];
  const lim = snap.limits || {};
  panel.innerHTML = `
    <div class="island-date-panel-inner">
      <header>
        <h2>日常心意</h2>
        <button type="button" data-heart-close>关闭</button>
      </header>
      <p>岛民用 heart_ops 送小礼物；你可拆卡、回一句、回礼。只花工分票。今日剩余：回礼 ${lim.human_send_left ?? "—"} · 回一句 ${lim.reply_left ?? "—"}</p>
      <div class="island-heart-list">
        ${pending.length ? pending.map(cardHtml).join("") : "<p>没有待拆的心意。</p>"}
        ${album.slice(0, 5).map((c) => cardHtml(c, false)).join("")}
      </div>
      <button type="button" data-heart-return>回礼</button>
    </div>`;
  panel.querySelector("[data-heart-close]")?.addEventListener("click", () => { panel.hidden = true; });
  panel.querySelectorAll("[data-heart-open]").forEach((btn) => btn.addEventListener("click", () => act("open", btn.dataset.heartOpen)));
  panel.querySelectorAll("[data-heart-keep]").forEach((btn) => btn.addEventListener("click", () => act("keep", btn.dataset.heartKeep)));
  panel.querySelectorAll("[data-heart-reply]").forEach((btn) => btn.addEventListener("click", async () => {
    const text = window.prompt("回一句", "");
    if (!text?.trim()) return;
    await act("reply", btn.dataset.heartReply, text.trim());
  }));
  panel.querySelector("[data-heart-return]")?.addEventListener("click", returnGift);
}

function cardHtml(c, actions = true) {
  const can = actions && c.from_role === "ai" && c.status === "pending";
  return `<article>
    <strong>${esc(c.emoji)} ${esc(c.title)}</strong>
    <span>${esc(c.from_label)}→${esc(c.to_label)} · ${esc(c.status_label)} · ${c.tickets}票</span>
    <p>${esc(c.scene)}</p>
    ${c.note ? `<p>${esc(c.note)}</p>` : ""}
    ${c.reply_text ? `<p>回：${esc(c.reply_text)}</p>` : ""}
    ${c.from_role === "human" && c.status === "pending" ? "<p>等岛民拆开后，小红点才会消失。</p>" : ""}
    ${can ? `<div>
      <button type="button" data-heart-open="${c.id}">拆开</button>
      <button type="button" data-heart-keep="${c.id}">收好</button>
      <button type="button" data-heart-reply="${c.id}">回一句</button>
    </div>` : ""}
  </article>`;
}

async function act(kind, id, text) {
  if (busy) return;
  busy = true;
  try {
    if (kind === "open") snap = await api.heartOpen(Number(id));
    else if (kind === "keep") snap = await api.heartKeep(Number(id));
    else snap = await api.heartReply(Number(id), text);
    toast(kind === "reply" ? "已回一句" : kind === "keep" ? "已收好" : "已拆开");
    paint();
    const n = (snap.pending || []).length;
    if (badge) { badge.hidden = n <= 0; badge.textContent = String(n); }
  } catch (err) {
    toast(err.message || "失败了");
  } finally {
    busy = false;
  }
}

async function returnGift() {
  const emojis = (snap?.emojis || []).join(" ");
  const emoji = window.prompt(`外观 emoji\n${emojis}`, "🍰");
  if (!emoji) return;
  const title = window.prompt("名字", "回礼");
  if (!title) return;
  const scene = window.prompt("场景", "桌边");
  if (!scene) return;
  const tickets = window.prompt("工分票 5～88", "8");
  if (!tickets) return;
  const note = window.prompt("留言（可空）", "") || "";
  if (busy) return;
  busy = true;
  try {
    snap = await api.heartReturn({
      emoji: emoji.trim(), title: title.trim(), scene: scene.trim(),
      tickets: Number(tickets), note,
    });
    toast("回礼已送出");
    paint();
  } catch (err) {
    toast(err.message || "回礼失败");
  } finally {
    busy = false;
  }
}
