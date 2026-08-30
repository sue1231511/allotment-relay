import { state } from "../store.js";
import { sceneArt } from "../ui/art.js";
import { esc } from "../ui/modal.js";

export function renderShore(root, { onCast }) {
  const w = state.world || {};
  const shore = state.shore || {};
  root.innerHTML = `
    <div class="island-place">
      ${sceneArt("shore")}
      <article class="island-place-card">
        <b>港口</b>
        <p>${esc(w.tide || "潮位")} · ${esc(w.weather || "天气")} · ${esc(w.phase || "")} · ${esc(w.season || "")}</p>
        <p>${esc(w.line || "码头风很轻。")}</p>
        <p>渔网 T${esc(shore.net_tier || 0)} · 钓竿 T${esc(shore.rod_tier || 0)} · 蚯蚓 ${esc(shore.bait_worm || 0)}</p>
      </article>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  bar.hidden = false;
  bar.removeAttribute("hidden");
  bar.innerHTML = `
    <button type="button" class="island-btn primary" data-act="net" ${shore.can_net ? "" : "disabled"}>撒网</button>
    <button type="button" class="island-btn" data-act="cast" ${shore.can_cast ? "" : "disabled"}>坐钓</button>
  `;
  bar.querySelector("[data-act=net]").addEventListener("click", () => onCast("net"));
  bar.querySelector("[data-act=cast]").addEventListener("click", () => onCast("cast"));
}
