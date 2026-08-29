import { state } from "../store.js";
import { esc } from "./modal.js";

export function renderBag(sheet) {
  const stock = (state.me && state.me.stock) || [];
  sheet.hidden = false;
  sheet.innerHTML = `
    <h2>行囊</h2>
    <p class="island-fine">和 AI 看见的是同一口袋。卖货、送礼仍去上手页。</p>
    ${stock.map((it) => `
      <div class="island-item"><span>${esc(it.name || it.item)}</span><b>×${esc(it.qty)}</b></div>
    `).join("") || "<p>行囊空着。</p>"}
  `;
}
