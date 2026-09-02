import { sceneArt } from "../ui/art.js?v=flowers1";
import { esc } from "../ui/modal.js?v=island-modulefix2";
import { state } from "../store.js?v=island-modulefix2";

export function renderFlorist(root, { onAct, onMeet } = {}) {
  const shop = state.florist || {};
  let wrap = root.querySelector(".island-florist");
  if (!wrap) {
    root.innerHTML = `<div class="island-vn island-florist"><div class="island-vn-board">
      ${sceneArt("florist")}
      <div class="island-vn-stand"><img class="island-vn-sprite" src="/static/island/assets/sprites/momo.png" alt="花店店主默默" draggable="false"></div>
      <div class="island-vn-talk is-line">
        <button type="button" class="island-vn-box" aria-label="点对话查看选项">
          <span class="island-vn-name">默默 · 默语花房</span><p class="island-vn-line" aria-live="polite"></p><i class="island-vn-more" aria-hidden="true"></i>
        </button>
        <div class="island-vn-choices"></div>
      </div>
      <button type="button" class="island-scene-tap">点一下见默默</button>
    </div></div>`;
    wrap = root.firstElementChild;
    wrap.querySelector(".island-vn-board").addEventListener("click", () => {
      if (wrap.classList.contains("is-peek") && !state.busy) onMeet?.();
    });
    wrap.querySelector(".island-vn-box").addEventListener("click", () => {
      if (state.busy) return;
      const talk = wrap.querySelector(".island-vn-talk");
      talk.classList.toggle("is-picks");
      talk.classList.toggle("is-line", !talk.classList.contains("is-picks"));
    });
  }
  const bar = document.getElementById("island-actionbar");
  if (bar) { bar.innerHTML = ""; bar.hidden = true; }
  wrap.classList.toggle("is-peek", !state.floristMeet);
  wrap.setAttribute("aria-busy", String(state.busy));
  wrap.querySelector(".island-vn-line").textContent = shop.line || "进来坐，花和茶都在这里。";
  const talk = wrap.querySelector(".island-vn-talk");
  talk.classList.add("is-line");
  talk.classList.remove("is-picks");
  const choices = wrap.querySelector(".island-vn-choices");
  const rows = shop.pending ? [{ kind: "retry", label: "重试刚才那一下", cost: null }]
    : [{ kind: "visit", label: shop.visited_today ? "再聊两句" : "打个招呼 · 今日见面礼", cost: 0 }, ...(shop.actions || [])];
  choices.innerHTML = rows.map(row => `<button type="button" class="island-vn-choice" data-act="${esc(row.kind)}" data-target="${esc(row.target || "")}" ${state.busy ? "disabled" : ""}>
    <b>${esc(row.label)}</b><small>${row.cost == null ? "核对结果，不重复扣款" : row.cost ? `${Number(row.cost)} 工分票` : "不收票"}</small>
  </button>`).join("");
  choices.querySelectorAll("[data-act]").forEach(btn => btn.addEventListener("click", ev => {
    ev.stopPropagation();
    if (!state.busy) onAct?.(btn.dataset.act, btn.dataset.target);
  }));
}
