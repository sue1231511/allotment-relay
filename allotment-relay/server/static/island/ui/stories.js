import { api } from "../api.js?v=mod-unify1";
import { esc, toast } from "./modal.js?v=mod-unify1";
import { hidePanel, setPanel, showPanel } from "./panel.js?v=story1";

/** story_progress 里的 place 码 → 人话地名；空码＝对不上地点，只能在故事册里点。 */
export const PLACE_NAME = { tide: "海边", plot: "份地", bar: "酒吧", undertide: "井下", clinic: "乔乔诊所", market: "集市" };

/** 地点码 → 在 /island 里算「走到了」的场景名。 */
export const PLACE_SCENES = {
  tide: ["shore", "port", "beach"],
  plot: ["yards"],
  bar: ["bar"],
  undertide: ["undertide"],
  clinic: ["clinic"],
  market: ["market", "market_stalls"],
};

const BOOK_SVG = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false"><path d="M4 5.5C4 4.7 4.7 4 5.5 4H11v15H5.5C4.7 19 4 18.3 4 17.5Zm16 0c0-.8-.7-1.5-1.500-1.500H13v15h5.500c.8 0 1.500-.7 1.500-1.500Z" fill="none" stroke="currentColor" stroke-width="1.700" stroke-linejoin="round"/><path d="M7 8h2.500M7 11h2.500M15 8h2M15 11h2" stroke="currentColor" stroke-width="1.400" stroke-linecap="round"/></svg>`;
export { BOOK_SVG };

let cache = null;
let cachedAt = 0;
const listeners = new Set();

export function onStoryChange(fn) {
  listeners.add(fn);
  return () => listeners.delete(fn);
}

function notify() {
  listeners.forEach((fn) => {
    try {
      fn(cache);
    } catch (err) {
      console.error("[stories] 监听出错", err);
    }
  });
}

export async function loadStories({ force = false } = {}) {
  if (!force && cache && Date.now() - cachedAt < 45000) return cache;
  const snap = await api.story();
  cache = snap.story || { available: [], active: [], done: [] };
  cachedAt = Date.now();
  notify();
  return cache;
}

export function resetStories() {
  cache = null;
  cachedAt = 0;
}

async function run(kind, target, afterView) {
  try {
    const snap = await api.storyAct(kind, target);
    cache = snap.story || cache;
    cachedAt = Date.now();
    notify();
    return snap;
  } catch (err) {
    console.error("[stories] 动作失败", kind, target, err);
    toast(err.message || "这一下没做成。");
    return null;
  } finally {
    if (typeof afterView === "function") afterView();
  }
}

/** place 有值＝要走到那个地点才点（run=false 时只写提示）；place 为空＝对不上地点，故事册里直接点。 */
function stepButton(step, key, idx, { run = true } = {}) {
  const where = PLACE_NAME[step.place];
  const tail = step.hint ? `<small>${esc(step.hint)}</small>` : "";
  const action = where && !run
    ? `<small class="island-panel-where">走到${esc(where)}再点</small>`
    : `<button type="button" class="island-btn" data-step="${esc(step.tool)}|${esc(step.command)}" data-step-key="${esc(key)}-${idx}">${where ? "走这一步" : "就这一步"}</button>`;
  return `<div class="island-panel-step">
    <div><b>${esc(step.label)}</b><small>${esc(step.note || "")}</small>${tail}</div>
    ${action}
  </div>`;
}

function listHtml(data) {
  const avail = data.available || [];
  const active = data.active || [];
  const done = data.done || [];
  const availHtml = avail.length
    ? avail.map((row) => `<article class="island-panel-item">
        <b>${esc(row.title)}</b><p>${esc(row.blurb || "")}</p><small>${esc(row.note || "")}</small>
        <button type="button" class="island-btn primary" data-${row.kind === "tale" ? "accept" : "start"}="${esc(row.key)}">${esc(row.kind === "tale" ? "接取" : "开始")}</button>
      </article>`).join("")
    : `<p class="island-fine">眼下没有新的可接。</p>`;
  const activeHtml = active.length
    ? active.map((row) => `<article class="island-panel-item">
        <b>${esc(row.title)}</b><p>${esc(row.blurb || "")}</p>
        ${(row.actions || []).map((step, i) => stepButton(step, row.key, i, { run: false })).join("") || `<small>这一步要走到对应地点才会出现。</small>`}
      </article>`).join("")
    : `<p class="island-fine">没有进行中的。</p>`;
  const doneHtml = done.length
    ? done.map((row) => `<article class="island-panel-item is-done">
        <b>${esc(row.title)}</b>${row.ending ? `<small>结局：${esc(row.ending)}</small>` : ""}
        <div class="island-panel-row">
          <button type="button" class="island-btn" data-review="${esc(row.kind)}|${esc(row.key)}">回看</button>
          ${row.replay ? `<button type="button" class="island-btn" data-start="${esc(row.key)}">重玩</button>` : ""}
        </div>
      </article>`).join("")
    : `<p class="island-fine">还没有走完的。</p>`;
  return `
    <p class="island-fine">当前一步对得上地点的，走到那个地点才点；对不上的在这里点。不是任务栏。</p>
    <h3 class="island-panel-sec">进行中</h3>${activeHtml}
    <h3 class="island-panel-sec">可接</h3>${availHtml}
    <h3 class="island-panel-sec">已完成</h3>${doneHtml}`;
}

function textHtml(title, text, backLabel = "回到故事册") {
  return `<article class="island-panel-item"><b>${esc(title)}</b><p class="island-panel-text">${esc(text)}</p></article>
    <button type="button" class="island-btn wide" data-back>${esc(backLabel)}</button>`;
}

function reviewHtml(review) {
  const chapters = review.chapters || [];
  return `<article class="island-panel-item"><b>${esc(review.title || "回忆")}</b>${review.ending ? `<small>结局：${esc(review.ending)}</small>` : ""}
    ${review.notice ? `<small>${esc(review.notice)}</small>` : ""}</article>
    ${chapters.map((ch) => `<article class="island-panel-item"><b>${esc(ch.title)}</b><p class="island-panel-text">${esc(ch.text)}</p></article>`).join("")}
    <button type="button" class="island-btn wide" data-back>回到故事册</button>`;
}

function bind(body, paint) {
  body.querySelectorAll("[data-accept]").forEach((btn) => btn.addEventListener("click", async () => {
    const snap = await run("accept", btn.getAttribute("data-accept"));
    if (snap) {
      setPanel({ title: "接取了", html: textHtml("潮闻", snap.event?.narrative || "接上了。") });
      bindBack(paint);
    }
  }));
  body.querySelectorAll("[data-start]").forEach((btn) => btn.addEventListener("click", async () => {
    const snap = await run("start", btn.getAttribute("data-start"));
    if (snap) {
      setPanel({ title: "开始了", html: textHtml("故事", snap.event?.narrative || "开始了。") });
      bindBack(paint);
    }
  }));
  body.querySelectorAll("[data-step]").forEach((btn) => btn.addEventListener("click", async () => {
    const snap = await run("step", btn.getAttribute("data-step"));
    if (snap) {
      setPanel({ title: "这一步", html: textHtml("故事", snap.event?.narrative || "走完了这一步。") });
      bindBack(paint);
    }
  }));
  body.querySelectorAll("[data-review]").forEach((btn) => btn.addEventListener("click", async () => {
    try {
      const snap = await api.storyAct("review", btn.getAttribute("data-review"));
      setPanel({ title: "回看", html: reviewHtml(snap.review || {}) });
      bindBack(paint);
    } catch (err) {
      console.error("[stories] 回看失败", err);
      toast(err.message || "这一篇现在翻不开。");
    }
  }));
}

function bindBack(paint) {
  const body = document.querySelector("[data-panel-body]");
  if (!body) return;
  body.querySelectorAll("[data-back]").forEach((btn) => btn.addEventListener("click", paint));
}

/** 潮汐公告木牌里的「潮闻与故事」入口打开它。 */
export async function openStories() {
  const body = showPanel({ title: "潮闻与故事", html: `<p class="island-fine">翻故事册…</p>` });
  if (!body) return;
  const paint = async () => {
    try {
      const data = await loadStories({ force: true });
      const view = setPanel({ title: "潮闻与故事", html: listHtml(data) });
      if (view) bind(view, paint);
    } catch (err) {
      console.error("[stories] 故事册读取失败", err);
      setPanel({ title: "潮闻与故事", html: `<p class="island-fine">${esc(err.message || "故事册这会儿翻不开。")}</p><button type="button" class="island-btn wide" data-back>再翻一次</button>` });
      bindBack(paint);
    }
  };
  await paint();
}

/** 走到对应地点时出现的「本处的故事」：只列这个地点的当前一步。 */
export async function openPlaceStory(place) {
  const body = showPanel({ title: `${PLACE_NAME[place] || "这里"}的故事`, html: `<p class="island-fine">翻开…</p>` });
  if (!body) return;
  const paint = async () => {
    try {
      const data = await loadStories({ force: true });
      const rows = (data.active || []).map((row) => ({ ...row, actions: (row.actions || []).filter((s) => s.place === place) })).filter((row) => row.actions.length);
      const html = rows.length
        ? rows.map((row) => `<article class="island-panel-item"><b>${esc(row.title)}</b>${row.actions.map((s, i) => stepButton(s, row.key, i)).join("")}</article>`).join("")
        : `<p class="island-fine">这里眼下没有要走的一步。</p>`;
      const view = setPanel({ title: `${PLACE_NAME[place] || "这里"}的故事`, html });
      if (view) bind(view, paint);
    } catch (err) {
      console.error("[stories] 本处故事读取失败", place, err);
      hidePanel();
      toast(err.message || "这会儿翻不开。");
    }
  };
  await paint();
}
