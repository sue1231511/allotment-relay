import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=island-portchat1";

/** 热区按剧场院景 1080×1920：贝壳台是剧场，右侧小屋是衣泊坊，右下收稿桌是编剧社。 */
const HOTS = [
  { go: "hall", cls: "is-hall", name: "剧场", left: 18, top: 20, w: 50, h: 34 },
  { go: "atelier", cls: "is-atelier", name: "衣泊坊", left: 66, top: 36, w: 30, h: 24 },
  { go: "writers", cls: "is-writers", name: "编剧社", left: 52, top: 68, w: 42, h: 24 },
];

export function renderTheater(root, { onOpen } = {}) {
  root.innerHTML = `
    <div class="island-plaza island-theater">
      <div class="island-plaza-board island-theater-board">
        ${sceneArt("theater")}
        ${HOTS.map((p) => hotMarkup(p)).join("")}
      </div>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
  layoutCoverBoard(root.querySelector(".island-theater"), ".island-theater-board", 1080, 1920);
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
