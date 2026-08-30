import { sceneArt } from "./ui/art.js";

const PINS = [
  { go: "home", cls: "is-home", kicker: "Home", name: "家园" },
  { go: "shore", cls: "is-shore", kicker: "Tide", name: "港口" },
  { go: "hut", cls: "is-hut", kicker: "Hut", name: "小屋" },
  { go: "bar", cls: "is-bar", kicker: "Bar", name: "酒吧" },
  { go: "theater", cls: "is-theater", kicker: "Stage", name: "剧场" },
  { go: "eatery", cls: "is-eatery", kicker: "Eat", name: "小馆" },
  { go: "hui", cls: "is-hui", kicker: "Hui", name: "潮生会" },
  { go: "plaza", cls: "is-plaza", kicker: "Plaza", name: "广场" },
];

export function renderMap(root, { onOpen }) {
  root.innerHTML = `
    <div class="island-map">
      ${sceneArt("island-map")}
      ${PINS.map((p) => (
        `<button type="button" class="island-pin ${p.cls}" data-go="${p.go}"><small>${p.kicker}</small><b>${p.name}</b></button>`
      )).join("")}
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = `<p class="island-fine" style="grid-column:1/-1;margin:4px 2px 0">点家园、港口、小屋这些钉子就能进。插图后补。</p>`;
  }
  if (typeof onOpen === "function") {
    root.querySelectorAll("[data-go]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        onOpen(btn.getAttribute("data-go"));
      });
    });
  }
}
