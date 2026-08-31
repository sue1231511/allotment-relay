import { sceneArt } from "../ui/art.js?v=island-plazalili1";
import { esc } from "../ui/modal.js?v=island-plazalili1";

/** 具体地点只铺图和地名，不放洗碗、交税这些按钮。 */
export function renderPlace(root, { id, title }) {
  root.innerHTML = `
    <div class="island-place">
      ${sceneArt(id)}
      <article class="island-place-card">
        <b>${esc(title)}</b>
      </article>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  if (!bar) return;
  bar.innerHTML = "";
  bar.hidden = true;
}
