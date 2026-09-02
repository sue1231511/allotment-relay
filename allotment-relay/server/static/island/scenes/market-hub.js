import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=island-modulefix2";

/** 总览仍只有集市入口，内层像广场一样点地名。 */
export function renderMarketHub(root, { onOpen } = {}) {
  root.innerHTML = `<div class="island-plaza island-market-hub"><div class="island-plaza-board">
    ${sceneArt("market")}
    <button type="button" class="island-hot" data-go="market_stalls" style="left:16%;top:34%;width:30%;height:22%"><span>集市</span></button>
    <button type="button" class="island-hot" data-go="florist" style="left:56%;top:51%;width:30%;height:22%"><span>花店</span></button>
  </div></div>`;
  const bar = document.getElementById("island-actionbar");
  if (bar) { bar.innerHTML = ""; bar.hidden = true; }
  layoutCoverBoard(root.firstElementChild, ".island-plaza-board", 941, 1672);
  root.querySelectorAll("[data-go]").forEach(btn => btn.addEventListener("click", () => onOpen?.(btn.dataset.go)));
}
