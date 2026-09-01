import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=undertide-map1";

/** 井下入口先展示完整总览；地点名已经直接标在图上。 */
export function renderUndertide(root) {
  root.innerHTML = `
    <div class="island-map island-undertide-map">
      <div class="island-map-board island-undertide-board">
        ${sceneArt("undertide-map")}
      </div>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
  layoutCoverBoard(root.querySelector(".island-undertide-map"), ".island-undertide-board", 941, 1672);
}
