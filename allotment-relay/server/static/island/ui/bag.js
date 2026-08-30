import { state } from "../store.js";
import { esc } from "./modal.js";

export function renderBag(sheet, { onEat, onVend } = {}) {
  const stock = (state.me && state.me.stock) || [];
  sheet.hidden = false;
  sheet.innerHTML = `
    <h2>行囊</h2>
    <p class="island-fine">和 AI 看见的是同一口袋。左边吃，右边卖。</p>
    ${stock.map((it) => itemMarkup(it)).join("") || "<p>行囊空着。</p>"}
  `;
  sheet.querySelectorAll("[data-eat]").forEach((btn) => {
    btn.addEventListener("click", () => onEat && onEat(btn.getAttribute("data-eat")));
  });
  sheet.querySelectorAll("[data-vend]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const name = btn.getAttribute("data-vend");
      const row = stock.find((it) => (it.name || it.item) === name);
      if (onVend) onVend(row || { name, item: name });
    });
  });
}

function itemMarkup(it) {
  const name = it.name || it.item;
  const acts = [];
  if (it.can_eat) {
    acts.push(`<button type="button" class="island-btn" data-eat="${esc(name)}">吃</button>`);
  }
  if (it.can_vend !== false) {
    const price = it.vend_price ? `${it.vend_price}票` : "";
    acts.push(`<button type="button" class="island-btn primary" data-vend="${esc(name)}">卖${price ? ` ${esc(price)}` : ""}</button>`);
  }
  return `
    <div class="island-item">
      <span>${esc(name)} ×${esc(it.qty)}</span>
      <span class="island-item-acts">${acts.join("") || ""}</span>
    </div>
  `;
}
