import { sceneArt } from "../ui/art.js";
import { esc } from "../ui/modal.js";

export function renderPlace(root, { id, title, body, actions, onAct }) {
  const acts = actions || [];
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
  if (!bar) return;
  if (!acts.length) {
    bar.innerHTML = "";
    bar.hidden = true;
    return;
  }
  bar.hidden = false;
  bar.removeAttribute("hidden");
  bar.innerHTML = acts.map((act) => (
    `<button type="button" class="island-btn ${act.primary ? "primary" : ""}" data-act="${esc(act.id)}" ${act.disabled ? "disabled" : ""}>${esc(act.label)}</button>`
  )).join("");
  acts.forEach((act) => {
    const btn = bar.querySelector(`[data-act="${act.id}"]`);
    if (btn) btn.addEventListener("click", () => onAct(act.id));
  });
}
