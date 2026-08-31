import { hutScene } from "../store.js?v=island-hutscene1";
import { sceneArt } from "../ui/art.js?v=island-hutscene1";
import { esc } from "../ui/modal.js?v=island-hutscene1";

/** 没买房看不见棚屋场景。买了才按等级换景。 */
export function renderHut(root, { onBuild }) {
  const info = hutScene();
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
  if (!info.built) {
    root.innerHTML = `
      <div class="island-place is-locked">
        <article class="island-place-card is-lock">
          <b>还没买房</b>
          <p>棚屋场景还锁着。搭好才看得见棚屋，再升到岸畔小屋、联盟小宅、临海邸会换景。睡觉、升级仍去上手页。</p>
          <button type="button" class="island-btn primary wide" data-act="build">搭棚屋 · ${esc(String(info.cost))} 票</button>
        </article>
      </div>
    `;
    const btn = root.querySelector("[data-act=build]");
    if (btn && typeof onBuild === "function") btn.addEventListener("click", onBuild);
    return;
  }
  root.innerHTML = `
    <div class="island-place">
      ${sceneArt(info.sceneId)}
      <article class="island-place-card">
        <b>${esc(info.title)}</b>
      </article>
    </div>
  `;
}
