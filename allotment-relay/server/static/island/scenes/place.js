import { sceneArt } from "../ui/art.js";
import { esc } from "../ui/modal.js";

export function renderPlace(root, { id, title, body, actions, onAct, onBack }) {
  root.innerHTML = `
    <div class="island-place">
      ${sceneArt(id)}
      <article class="island-place-card">
        <b>${esc(title)}</b>
        ${body.map((line) => `<p>${esc(line)}</p>`).join("")}
      </article>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  bar.innerHTML = [
    `<button type="button" class="island-btn" data-act="back">回地图</button>`,
    ...actions.map((act) => (
      `<button type="button" class="island-btn ${act.primary ? "primary" : ""}" data-act="${esc(act.id)}" ${act.disabled ? "disabled" : ""}>${esc(act.label)}</button>`
    )),
  ].join("");
  bar.querySelector("[data-act=back]").addEventListener("click", onBack);
  actions.forEach((act) => {
    const btn = bar.querySelector(`[data-act="${act.id}"]`);
    if (btn) btn.addEventListener("click", () => onAct(act.id));
  });
}
