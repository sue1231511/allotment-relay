import { layoutCoverBoard, sceneArt } from "../ui/art.js";

const PICKS = [
  { go: "writers", name: "点一下看编剧社" },
  { go: "atelier", name: "点一下看衣泊坊" },
  { go: "hall", name: "点一下看剧场" },
];

export function renderTheater(root, { onOpen } = {}) {
  root.innerHTML = `
    <div class="island-plaza island-theater">
      <div class="island-plaza-board island-theater-board">
        ${sceneArt("theater")}
        <div class="island-theater-picks">
          ${PICKS.map((p) => (
            `<button type="button" class="island-scene-tap" data-go="${p.go}">${p.name}</button>`
          )).join("")}
        </div>
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
