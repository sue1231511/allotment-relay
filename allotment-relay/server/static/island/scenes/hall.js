import { sceneArt } from "../ui/art.js?v=island-modulefix2";
import { esc } from "../ui/modal.js?v=island-modulefix2";
import { state } from "../store.js?v=island-modulefix2";

export function renderHall(root, { onAct, onMeet } = {}) {
  const shop = state.hall || {};
  const peek = !state.hallMeet;
  let wrap = root.querySelector(".island-hall");
  if (!wrap) {
    root.innerHTML = `
      <div class="island-vn island-hall">
        <div class="island-vn-board">
          ${sceneArt("hall")}
          <div class="island-vn-stand is-half">
            <img class="island-vn-sprite" src="/static/island/assets/sprites/xiaoju.png" alt="小橘" draggable="false">
          </div>
          <div class="island-vn-talk is-line">
            <button type="button" class="island-vn-box" id="island-vn-advance">
              <span class="island-vn-name"></span>
              <p class="island-vn-line"></p>
              <i class="island-vn-more" aria-hidden="true"></i>
            </button>
            <div class="island-vn-choices" id="island-hall-choices"></div>
          </div>
          <button type="button" class="island-scene-tap">点一下见小橘</button>
        </div>
      </div>
    `;
    wrap = root.querySelector(".island-hall");
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

function hallChoices(shop) {
  const board = shop.board || {};
  const jobs = shop.jobs || [];
  const stars = shop.stars || [];
  return [
    {
      id: "look",
      target: "board",
      label: board.title || "今晚看板",
      price: "看",
      look: true,
    },
    {
      id: "look",
      target: "affinity",
      label: "舞台好感",
      price: `${board.affinity ?? 0}/100`,
      look: true,
    },
    ...stars.map((row) => ({
      id: row.id,
      target: row.cmd,
      label: row.name,
      price: row.price || (row.can_act ? "上" : "看"),
      can: Boolean(row.can_act),
    })),
    ...jobs.map((row) => ({
      id: row.id,
      target: row.cmd,
      label: row.name,
      price: row.can_act ? "上" : "看",
      can: Boolean(row.can_act),
    })),
  ];
}

function paintTalk(wrap, shop, onAct) {
  const talk = wrap.querySelector(".island-vn-talk");
  const name = wrap.querySelector(".island-vn-name");
  const line = wrap.querySelector(".island-vn-line");
  if (name) name.textContent = shop.speaker || "小橘";
  if (line) line.textContent = shop.line || "今晚没专场。侧厅编剧社还开着。";
  showLine(talk);
  bindAdvance(wrap);
  const list = wrap.querySelector("#island-hall-choices");
  if (!list) return;
  const rows = hallChoices(shop);
  list.innerHTML = rows.map((row) => {
    const fee = row.price ? `<small>${esc(row.price)}</small>` : "";
    const off = row.look || row.can ? "" : "is-off";
    return `<button type="button" class="island-vn-choice ${off}" data-act="${esc(row.id)}" data-target="${esc(row.target || "")}">
      <b>${esc(row.label)}</b>
      ${fee}
    </button>`;
  }).join("");
  list.querySelectorAll("[data-act]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (onAct) onAct(btn.getAttribute("data-act"), btn.getAttribute("data-target") || "");
    });
  });
}
