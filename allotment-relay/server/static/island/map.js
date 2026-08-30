import { sceneArt } from "./ui/art.js";

/** 热区按总览图 941×1672 的建筑位置。图上没有字，热区带小名签。 */
const HOTS = [
  { go: "hut", cls: "is-hut", name: "岸畔小屋", left: 30, top: 10, w: 26, h: 15 },
  { go: "home", cls: "is-home", name: "份地", label: "家园", left: 10, top: 22, w: 26, h: 13 },
  { go: "shore", cls: "is-shore", name: "海边", label: "港口", left: 62, top: 16, w: 30, h: 16 },
  { go: "bar", cls: "is-bar", name: "酒吧", left: 2, top: 38, w: 24, h: 13 },
  { go: "plaza", cls: "is-plaza", name: "广场", left: 36, top: 42, w: 28, h: 16 },
  { go: "eatery", cls: "is-eatery", name: "小馆", left: 16, top: 46, w: 20, h: 11 },
  { href: "/market", cls: "is-market", name: "集市", left: 66, top: 48, w: 26, h: 14 },
  { go: "theater", cls: "is-theater", name: "剧场", left: 6, top: 66, w: 30, h: 18 },
  { href: "/undertide", cls: "is-well", name: "井下入口", left: 56, top: 70, w: 26, h: 16 },
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
  layoutMapBoard(map);
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
  return `<button type="button" class="island-hot ${p.cls}" ${key} style="${style}" aria-label="${aria}"><span>${p.name}</span></button>`;
}

function layoutMapBoard(map) {
  if (!map) return;
  const board = map.querySelector(".island-map-board");
  const img = map.querySelector(".island-slot-pic");
  if (!board || !img) return;
  const apply = () => {
    const iw = img.naturalWidth || 941;
    const ih = img.naturalHeight || 1672;
    const cw = map.clientWidth;
    if (!cw) return;
    /* 和顶栏一样宽：按宽度缩放 941×1672，高度跟比例走，太高就在图上滚，不裁切。 */
    const s = cw / iw;
    board.style.width = `${cw}px`;
    board.style.height = `${Math.round(ih * s)}px`;
    board.style.left = "0px";
    board.style.top = "0px";
  };
  apply();
  requestAnimationFrame(apply);
  img.addEventListener("load", apply);
  if (!map._laid) {
    map._laid = true;
    window.addEventListener("resize", apply);
  }
}
