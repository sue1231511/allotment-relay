import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=island-hui1";

/** 热区按广场图 941×1672 上的房子和公告栏。图上已有店招，再叠游戏用地名。 */
const HOTS = [
  { go: "shop", cls: "is-shop", name: "杂货铺", left: 3, top: 28, w: 32, h: 24 },
  { go: "lighthouse", cls: "is-lighthouse", name: "灯塔", left: 50, top: 6, w: 22, h: 28 },
  { go: "workshop", cls: "is-workshop", name: "岸工坊", left: 65, top: 28, w: 32, h: 24 },
  { go: "notice", cls: "is-notice", name: "潮汐公告", left: 52, top: 68, w: 44, h: 26 },
];

export function renderPlaza(root, { onOpen } = {}) {
  root.innerHTML = `
    <div class="island-plaza">
      <div class="island-plaza-board">
        ${sceneArt("plaza")}
        ${HOTS.map((p) => hotMarkup(p)).join("")}
      </div>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
  layoutCoverBoard(root.querySelector(".island-plaza"), ".island-plaza-board", 941, 1672);
  if (typeof onOpen !== "function") return;
  root.querySelectorAll("[data-go]").forEach((btn) => {
    btn.addEventListener("click", (ev) => {
      ev.stopPropagation();
      onOpen(btn.getAttribute("data-go"));
    });
  });
}

function hotMarkup(p) {
  const style = `left:${p.left}%;top:${p.top}%;width:${p.w}%;height:${p.h}%`;
  return `<button type="button" class="island-hot ${p.cls}" data-go="${p.go}" style="${style}" aria-label="${p.name}"><span>${p.name}</span></button>`;
}
