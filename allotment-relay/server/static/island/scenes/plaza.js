import { sceneArt } from "../ui/art.js";
import { esc } from "../ui/modal.js";

export function renderPlaza(root, { messages, notices, onSay, onBack }) {
  const board = (notices && notices[0]) || { title: "公告牌", body: "今天岛上还安静。" };
  const rows = (messages || []).slice(-16);
  root.innerHTML = `
    <div class="island-plaza">
      ${sceneArt("plaza")}
      <aside class="island-board">
        <small>潮汐广场</small>
        <b>${esc(board.title || "世界")}</b>
        <p>${esc(board.body || "")}</p>
      </aside>
      <div class="island-msgs">
        ${rows.map((m) => `
          <article class="island-msg">
            <b>${esc(m.who || "岛民")}</b>
            <p>${esc(m.text || m.body || "")}</p>
          </article>
        `).join("") || "<p class='island-fine' style='padding:8px'>大厅还没人说话。</p>"}
      </div>
      <form class="island-composer" id="plaza-say">
        <input name="text" maxlength="280" placeholder="对全服说一句" autocomplete="off">
        <button type="submit" class="island-btn primary">发言</button>
      </form>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  bar.innerHTML = `<button type="button" class="island-btn wide" data-act="back">回地图</button>`;
  bar.querySelector("[data-act=back]").addEventListener("click", onBack);
  root.querySelector("#plaza-say").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const input = ev.target.elements.text;
    const text = (input.value || "").trim();
    if (!text) return;
    onSay(text);
    input.value = "";
  });
}
