import { layoutCoverBoard, sceneArt } from "./ui/art.js?v=island-plantbag1";

/** 热区百分比按总览图 972×1619 的标签位置。图上已有地名，不再叠钉子。 */
const HOTS = [
  { go: "hut", cls: "is-hut", name: "岸畔小屋", left: 8, top: 5, w: 24, h: 16 },
  { go: "yards", cls: "is-home", name: "份地", label: "家园", left: 36, top: 7, w: 26, h: 18 },
  { go: "shore", cls: "is-shore", name: "海边", left: 66, top: 10, w: 30, h: 16 },
  { go: "workshop", cls: "is-workshop", name: "岸工坊", left: 56, top: 27, w: 24, h: 13 },
  { go: "quarry", cls: "is-quarry", name: "盐风崖", left: 3, top: 35, w: 22, h: 14 },
  { go: "plaza", cls: "is-plaza", name: "广场", left: 36, top: 40, w: 28, h: 16 },
  { go: "theater", cls: "is-theater", name: "剧场", left: 70, top: 40, w: 28, h: 14 },
  { go: "bar", cls: "is-bar", name: "酒吧", left: 5, top: 50, w: 24, h: 14 },
  { go: "eatery", cls: "is-eatery", name: "岸畔小馆", left: 70, top: 54, w: 28, h: 14 },
  { go: "market", cls: "is-market", name: "集市", left: 8, top: 62, w: 24, h: 12 },
  { go: "ting", cls: "is-ting", name: "听潮亭", left: 34, top: 66, w: 26, h: 12 },
  { go: "hui", cls: "is-hui", name: "潮生会", left: 70, top: 68, w: 26, h: 12 },
  { go: "lianli", cls: "is-lianli", name: "连理所", left: 16, top: 82, w: 26, h: 12 },
  { href: "/undertide", cls: "is-well", name: "井下入口", left: 44, top: 82, w: 26, h: 14 },
];

export function renderMap(root, { onOpen }) {
  root.innerHTML = `
    <div class="island-map">
      <div class="island-map-board" id="island-map-board">
        ${sceneArt("island-map")}
        ${HOTS.map((p) => hotMarkup(p)).join("")}
      </div>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
  const map = root.querySelector(".island-map");
  layoutCoverBoard(map, ".island-map-board", 972, 1619);
  if (typeof onOpen === "function") {
    root.querySelectorAll("[data-go],[data-href]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const href = btn.getAttribute("data-href");
        if (href) {
          window.location.href = href;
          return;
        }
        onOpen(btn.getAttribute("data-go"));
      });
    });
  }
}

function hotMarkup(p) {
  const aria = p.label ? `${p.name}（${p.label}）` : p.name;
  const key = p.href
    ? `data-href="${p.href}"`
    : `data-go="${p.go}"`;
  const style = `left:${p.left}%;top:${p.top}%;width:${p.w}%;height:${p.h}%`;
  return `<button type="button" class="island-hot ${p.cls}" ${key} style="${style}" aria-label="${aria}"></button>`;
}

