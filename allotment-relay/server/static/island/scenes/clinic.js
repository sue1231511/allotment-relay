import { sceneArt } from "../ui/art.js?v=island-mapbgm1";
import { esc } from "../ui/modal.js?v=island-mapbgm1";
import { state } from "../store.js?v=island-mapbgm1";

export function renderClinic(root, { onAct, onMeet } = {}) {
  const shop = state.clinic || {};
  const peek = !state.clinicMeet;
  let wrap = root.querySelector(".island-clinic");
  if (!wrap) {
    root.innerHTML = `
      <div class="island-vn island-clinic">
        <div class="island-vn-board">
          ${sceneArt("clinic")}
          <div class="island-vn-stand is-half">
            <img class="island-vn-sprite" src="/static/island/assets/sprites/qiaoqiao.png" alt="桥桥" draggable="false">
          </div>
          <div class="island-vn-talk is-line">
            <button type="button" class="island-vn-box" id="island-vn-advance">
              <span class="island-vn-name"></span>
              <p class="island-vn-line"></p>
              <i class="island-vn-more" aria-hidden="true"></i>
            </button>
            <div class="island-vn-choices" id="island-clinic-choices"></div>
          </div>
          <button type="button" class="island-scene-tap">点一下见桥桥</button>
        </div>
      </div>
    `;
    wrap = root.querySelector(".island-clinic");
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

function clinicChoices(shop) {
  const items = shop.items || {};
  const rows = [];
  for (const key of ["treat", "tonic", "shelf", "dove"]) {
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
  if (name) name.textContent = shop.speaker || "桥桥";
  if (line) line.textContent = shop.line || "地上的病来看病，没病可调理，药架能买，窗台能喂斑鸠。";
  showLine(talk);
  bindAdvance(wrap);
  const list = wrap.querySelector("#island-clinic-choices");
  if (!list) return;
  const rows = clinicChoices(shop);
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
