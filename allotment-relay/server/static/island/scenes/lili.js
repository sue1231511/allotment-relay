import { sceneArt } from "../ui/art.js?v=island-mapbgm1";
import { esc } from "../ui/modal.js?v=island-mapbgm1";
import { state } from "../store.js?v=island-mapbgm1";

export function renderLili(root, { onAct, onMeet } = {}) {
  const shop = state.lili || {};
  const peek = !state.liliMeet;
  let wrap = root.querySelector(".island-lili");
  if (!wrap) {
    root.innerHTML = `
      <div class="island-vn island-lili">
        <div class="island-vn-board">
          ${sceneArt("lili")}
          <div class="island-vn-stand is-half">
            <img class="island-vn-sprite" src="/static/island/assets/sprites/lili.png" alt="栗栗" draggable="false">
          </div>
          <div class="island-vn-talk is-line">
            <button type="button" class="island-vn-box" id="island-vn-advance">
              <span class="island-vn-name"></span>
              <p class="island-vn-line"></p>
              <i class="island-vn-more" aria-hidden="true"></i>
            </button>
            <div class="island-vn-choices" id="island-lili-choices"></div>
          </div>
          <button type="button" class="island-scene-tap">点一下见栗栗</button>
        </div>
      </div>
    `;
    wrap = root.querySelector(".island-lili");
  }
  wrap.classList.toggle("is-peek", peek);
  hideActionBar();
  bindMeet(wrap, onMeet);
  if (peek) return;
  paintTalk(wrap, shop, onAct);
}

function bindMeet(wrap, onMeet) {
  const board = wrap.querySelector(".island-vn-board");
  if (!board || board._meetBound) return;
  board._meetBound = true;
  board.addEventListener("click", () => {
    if (!wrap.classList.contains("is-peek")) return;
    if (onMeet) onMeet();
  });
}

function hideActionBar() {
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
}

function showLine(talk) {
  if (!talk) return;
  talk.classList.add("is-line");
  talk.classList.remove("is-picks");
}

function showPicks(talk) {
  if (!talk) return;
  talk.classList.remove("is-line");
  talk.classList.add("is-picks");
}

function bindAdvance(wrap) {
  const talk = wrap.querySelector(".island-vn-talk");
  const box = wrap.querySelector("#island-vn-advance");
  if (!talk || !box || box._vnBound) return;
  box._vnBound = true;
  box.addEventListener("click", () => {
    if (talk.classList.contains("is-picks")) return;
    showPicks(talk);
  });
}

function liliChoices(shop) {
  const items = shop.items || {};
  const rows = [];
  for (const key of ["shelf", "summon", "side"]) {
    for (const row of items[key] || []) {
      rows.push({
        id: row.id,
        kind: row.kind,
        target: row.target || "",
        label: row.name,
        price: row.price || "",
        look: row.kind === "look",
        can: Boolean(row.can),
      });
    }
  }
  return rows;
}

function paintTalk(wrap, shop, onAct) {
  const talk = wrap.querySelector(".island-vn-talk");
  const name = wrap.querySelector(".island-vn-name");
  const line = wrap.querySelector(".island-vn-line");
  if (name) name.textContent = shop.speaker || "栗栗";
  if (line) line.textContent = shop.line || "贝壳换货。不在就献壳唤摊，夜栖在摊边。";
  showLine(talk);
  bindAdvance(wrap);
  const list = wrap.querySelector("#island-lili-choices");
  if (!list) return;
  const rows = liliChoices(shop);
  list.innerHTML = rows.map((row) => {
    const fee = row.price ? `<small>${esc(row.price)}</small>` : "";
    const off = row.look || row.can ? "" : "is-off";
    return `<button type="button" class="island-vn-choice ${off}" data-act="${esc(row.kind)}" data-target="${esc(row.target || "")}" data-id="${esc(row.id || "")}">
      <b>${esc(row.label)}</b>
      ${fee}
    </button>`;
  }).join("");
  list.querySelectorAll("[data-act]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (onAct) onAct(btn.getAttribute("data-act"), btn.getAttribute("data-target") || "", btn.getAttribute("data-id") || "");
    });
  });
}
