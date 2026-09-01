import { sceneArt } from "../ui/art.js?v=island-fastscenes1";
import { esc } from "../ui/modal.js?v=island-mapbgm1";
import { state } from "../store.js?v=island-mapbgm1";

export function renderLighthouse(root, { onAct, onMeet } = {}) {
  const shop = state.lighthouse || {};
  const peek = !state.lighthouseMeet;
  let wrap = root.querySelector(".island-lighthouse");
  if (!wrap) {
    root.innerHTML = `
      <div class="island-vn island-lighthouse">
        <div class="island-vn-board">
          ${sceneArt("lighthouse")}
          <div class="island-vn-stand">
            <img class="island-vn-sprite" src="/static/island/assets/sprites/buxing.png" alt="不醒" draggable="false">
          </div>
          <div class="island-vn-talk is-line">
            <button type="button" class="island-vn-box" id="island-vn-advance">
              <span class="island-vn-name"></span>
              <p class="island-vn-line"></p>
              <i class="island-vn-more" aria-hidden="true"></i>
            </button>
            <div class="island-vn-choices" id="island-lighthouse-choices"></div>
          </div>
          <button type="button" class="island-scene-tap">点一下见不醒</button>
        </div>
      </div>
    `;
    wrap = root.querySelector(".island-lighthouse");
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

function paintTalk(wrap, shop, onAct) {
  const talk = wrap.querySelector(".island-vn-talk");
  const name = wrap.querySelector(".island-vn-name");
  const line = wrap.querySelector(".island-vn-line");
  if (name) name.textContent = shop.speaker || "不醒";
  if (line) line.textContent = shop.line || "茶不要钱。坐。";
  showLine(talk);
  bindAdvance(wrap);
  const list = wrap.querySelector("#island-lighthouse-choices");
  if (!list) return;
  const rows = shop.choices || [];
  list.innerHTML = rows.map((row) => {
    const fee = row.price ? `<small>${esc(row.price)}</small>` : "";
    return `<button type="button" class="island-vn-choice ${row.can ? "" : "is-off"}" data-act="${esc(row.id)}">
      <b>${esc(row.label)}</b>
      ${fee}
    </button>`;
  }).join("");
  list.querySelectorAll("[data-act]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (onAct) onAct(btn.getAttribute("data-act"), "");
    });
  });
}
