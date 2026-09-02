import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=undertide-scenes1";
import { renderPlace } from "./place.js?v=undertide-scenes1";

/** 热区对齐井下总览原有的地点牌；底图本身不改动。 */
const HOTS = [
  { id: "undertide-backroom", title: "后室铺", left: 7, top: 16, w: 35, h: 22 },
  { id: "undertide-bounty", title: "恩怨墙", left: 40, top: 21, w: 23, h: 18 },
  { id: "undertide-bank", title: "恶猫钱庄", left: 65, top: 16, w: 31, h: 22, sprite: "cat-bank-president", name: "恶猫钱庄行长" },
  { id: "undertide-casino", title: "死人赌场", left: 65, top: 37, w: 31, h: 20, sprite: "silas", name: "Silas" },
  { id: "undertide-medic", title: "晏安医务间", left: 65, top: 58, w: 31, h: 18 },
];

/** 先展示完整总览，点已有地点牌才进入对应场景。 */
export function renderUndertide(root) {
  const showMap = () => {
    root.innerHTML = `
    <div class="island-map island-undertide-map">
      <div class="island-map-board island-undertide-board">
        ${sceneArt("undertide-map")}
        ${HOTS.map(hotMarkup).join("")}
      </div>
    </div>
  `;
    root.querySelectorAll("[data-undertide-place]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const id = btn.getAttribute("data-undertide-place");
        const spot = HOTS.find((item) => item.id === id);
        if (spot) showPlace(spot);
      });
    });
    layoutCoverBoard(root.querySelector(".island-undertide-map"), ".island-undertide-board", 941, 1672);
  };

  const showPlace = (spot) => {
    renderPlace(root, { id: spot.id, title: spot.title });
    if (spot.sprite) {
      root.querySelector(".island-place").insertAdjacentHTML("beforeend", `
        <div class="island-undertide-sprite">
          <img src="/static/island/assets/sprites/${spot.sprite}.png" alt="${spot.name}" draggable="false">
        </div>
      `);
    }
    const card = root.querySelector(".island-place-card");
    if (card) {
      const back = document.createElement("button");
      back.type = "button";
      back.className = "island-undertide-return";
      back.textContent = "返回井下地图";
      back.addEventListener("click", showMap);
      card.append(back);
    }
  };

  showMap();
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
}

function hotMarkup(spot) {
  const style = `left:${spot.left}%;top:${spot.top}%;width:${spot.w}%;height:${spot.h}%`;
  return `<button type="button" class="island-hot" data-undertide-place="${spot.id}" style="${style}" aria-label="${spot.title}"></button>`;
}
