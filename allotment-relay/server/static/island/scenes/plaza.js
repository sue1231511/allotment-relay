import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=island-yardspeek1";

/** 热区按广场图 941×1672：左杂货、右诊所、后灯塔、前栗栗摊、右下公告栏。 */
const HOTS = [
  { go: "shop", cls: "is-shop", name: "杂货铺", left: 2, top: 22, w: 32, h: 20 },
  { go: "lighthouse", cls: "is-lighthouse", name: "灯塔", left: 40, top: 6, w: 22, h: 20 },
  { go: "clinic", cls: "is-clinic", name: "乔乔诊所", left: 64, top: 18, w: 34, h: 24 },
  { go: "lili", cls: "is-lili", name: "栗栗流动摊", left: 46, top: 44, w: 38, h: 22 },
  { go: "notice", cls: "is-notice", name: "潮汐公告", left: 52, top: 72, w: 44, h: 24 },
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
