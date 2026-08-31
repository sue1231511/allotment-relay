import { sceneArt } from "../ui/art.js";
import { esc } from "../ui/modal.js";
import { state } from "../store.js";

export function renderLighthouse(root, { onAct } = {}) {
  const shop = state.lighthouse || {};
  const existing = root.querySelector(".island-lighthouse");
  if (existing) {
    paintTalk(existing, shop, onAct);
    hideActionBar();
    return;
  }
  root.innerHTML = `
    <div class="island-vn island-lighthouse">
      <div class="island-vn-board">
        ${sceneArt("lighthouse")}
        <img class="island-vn-sprite" src="/static/island/assets/sprites/buxing.png" alt="不醒" draggable="false">
        <div class="island-vn-box">
          <span class="island-vn-name"></span>
          <p class="island-vn-line"></p>
          <div class="island-vn-choices" id="island-lighthouse-choices"></div>
        </div>
      </div>
    </div>
  `;
  hideActionBar();
  paintTalk(root.querySelector(".island-lighthouse"), shop, onAct);
}

function hideActionBar() {
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
}

function paintTalk(wrap, shop, onAct) {
  const name = wrap.querySelector(".island-vn-name");
  const line = wrap.querySelector(".island-vn-line");
  if (name) name.textContent = shop.speaker || "不醒";
  if (line) line.textContent = shop.line || "茶不要钱。坐。";
  const list = wrap.querySelector("#island-lighthouse-choices");
  if (!list) return;
  const rows = shop.choices || [];
  list.innerHTML = rows.map((row) => (
    `<button type="button" class="island-vn-choice ${row.can ? "" : "is-off"}" data-act="${esc(row.id)}">
      <b>${esc(row.label)}</b>
      <small>${esc(row.price || row.note || "")}</small>
    </button>`
  )).join("");
  list.querySelectorAll("[data-act]").forEach((btn) => {
    btn.addEventListener("click", () => {
      if (onAct) onAct(btn.getAttribute("data-act"), "");
    });
  });
}
