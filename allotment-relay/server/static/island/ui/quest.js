import { homePlots, state } from "../store.js";
import { esc } from "./modal.js";

export function renderQuest(sheet) {
  const plots = homePlots();
  const fallow = plots.filter((p) => p.can_sow).length;
  const ripe = plots.filter((p) => p.can_harvest).length;
  const seeds = ((state.me && state.me.seeds) || []).filter((s) => !s.tree);
  const lines = [
    seeds.length && fallow
      ? `手里还有种子，家园有 ${fallow} 块空地，先种下去。`
      : "空地先等种子，或去上手页买种。",
    ripe ? `有 ${ripe} 块已经熟了，点进去收。` : "熟了才会出现收获。急不来。",
    "酒吧每 2 天上一次工。逾期会锁份地和出海。去上手页点洗碗。",
    "潮闻和人物故事的下一步还在上手页。这里先把地种活。",
  ];
  sheet.hidden = false;
  sheet.innerHTML = `
    <h2>现在可以做的</h2>
    ${lines.map((t) => `<div class="island-item"><span>${esc(t)}</span></div>`).join("")}
  `;
}
