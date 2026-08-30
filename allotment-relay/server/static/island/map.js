import { sceneArt } from "./ui/art.js";

const PINS = [
  { go: "home", cls: "is-home", kicker: "Home", name: "家园" },
  { go: "shore", cls: "is-shore", kicker: "Tide", name: "港口" },
  { go: "hut", cls: "is-hut", kicker: "Hut", name: "小屋" },
  { go: "bar", cls: "is-bar", kicker: "Bar", name: "酒吧" },
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
  bar.innerHTML = `<p class="island-fine" style="grid-column:1/-1;margin:4px 2px 0">点家园进院子，再点土地才看菜地、果园、温室。插图后补，地点已经能进。</p>`;
  root.querySelectorAll("[data-go]").forEach((btn) => {
    btn.addEventListener("click", () => onOpen(btn.getAttribute("data-go")));
  });
}
