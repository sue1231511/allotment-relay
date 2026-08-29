import { esc } from "./modal.js";

export function renderChat(sheet, { messages, onSay }) {
  const rows = (messages || []).slice(-20);
  sheet.hidden = false;
  sheet.innerHTML = `
    <h2>聊天室</h2>
    <p class="island-fine">限频、禁言、昵称和管理员规则与全服聊天室相同。</p>
    <div class="island-msgs" style="max-height:36vh">
      ${rows.map((m) => `
        <article class="island-msg">
          <b>${esc(m.who || "")}</b>
          <p>${esc(m.text || m.body || "")}</p>
        </article>
      `).join("") || "<p>还没有最近消息。</p>"}
    </div>
    <form class="island-composer" id="sheet-say">
      <input name="text" maxlength="280" placeholder="说一句" autocomplete="off">
      <button class="island-btn primary" type="submit">发送</button>
    </form>
  `;
  sheet.querySelector("#sheet-say").addEventListener("submit", (ev) => {
    ev.preventDefault();
    const input = ev.target.elements.text;
    const text = (input.value || "").trim();
    if (text) onSay(text);
  });
}
