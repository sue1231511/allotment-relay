import { esc } from "./modal.js?v=mod-unify1";

/**
 * 通用面板：深色玻璃卡 + 金边，顶上标题和关闭，中间可滚动。
 * 「这一号」「潮闻与故事」「本处的故事」都用它；表单、提示仍走 modal.js（面板打开时 modal 抬到面板上面）。
 */
const CLOSE_SVG = `<svg viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false"><path d="M6 6 18 18M18 6 6 18" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>`;

let closeHandler = null;

function rootEl() {
  return document.getElementById("island-panel");
}

export function panelOpen() {
  const root = rootEl();
  return Boolean(root && !root.hidden);
}

export function showPanel({ title = "", html = "", onClose } = {}) {
  const root = rootEl();
  if (!root) return null;
  closeHandler = typeof onClose === "function" ? onClose : null;
  root.innerHTML = `
    <section class="island-panel-card" role="dialog" aria-label="${esc(title)}">
      <header class="island-panel-head">
        <h2 data-panel-title>${esc(title)}</h2>
        <button type="button" class="island-panel-x" data-panel-close aria-label="关闭">${CLOSE_SVG}</button>
      </header>
      <div class="island-panel-body" data-panel-body>${html}</div>
    </section>
  `;
  root.hidden = false;
  root.removeAttribute("hidden");
  document.body.classList.add("is-panel-open");
  root.querySelector("[data-panel-close]").addEventListener("click", hidePanel);
  root.addEventListener("click", (ev) => {
    if (ev.target === root) hidePanel();
  }, { once: true });
  return root.querySelector("[data-panel-body]");
}

export function setPanel({ title, html }) {
  const root = rootEl();
  if (!root || root.hidden) return null;
  if (title != null) {
    const head = root.querySelector("[data-panel-title]");
    if (head) head.textContent = title;
  }
  const body = root.querySelector("[data-panel-body]");
  if (body) {
    body.innerHTML = html;
    body.scrollTop = 0;
  }
  return body;
}

export function hidePanel() {
  const root = rootEl();
  if (!root || root.hidden) return;
  root.hidden = true;
  root.innerHTML = "";
  document.body.classList.remove("is-panel-open");
  const cb = closeHandler;
  closeHandler = null;
  if (cb) {
    try {
      cb();
    } catch (err) {
      console.error("[panel] 关闭回调出错", err);
    }
  }
}
