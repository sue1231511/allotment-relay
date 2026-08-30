import { state } from "../store.js";
import { esc } from "./modal.js";

export function renderBag(sheet, { onEat } = {}) {
  const stock = (state.me && state.me.stock) || [];
  sheet.hidden = false;
  sheet.innerHTML = `
    <h2>行囊</h2>
    <p class="island-fine">和 AI 看见的是同一口袋。点吃一口；卖货、送礼仍去上手页。</p>
    ${stock.map((it) => `
      <div class="island-item">
        <span>${esc(it.name || it.item)} ×${esc(it.qty)}</span>
        <button type="button" class="island-btn" data-eat="${esc(it.name || it.item)}">吃</button>
      </div>
    `).join("") || "<p>行囊空着。</p>"}
  `;
  sheet.querySelectorAll("[data-eat]").forEach((btn) => {
    btn.addEventListener("click", () => onEat && onEat(btn.getAttribute("data-eat")));
  });
}
