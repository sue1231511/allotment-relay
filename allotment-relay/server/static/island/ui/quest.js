import { ripeYard, state, thirstyYard, yardPlots } from "../store.js?v=island-modulefix2";
import { esc } from "./modal.js?v=island-modulefix2";

export function renderQuest(sheet) {
  const me = state.me || {};
  const dues = me.dues || {};
  const idle = yardPlots("home").filter((p) => p.can_sow).length;
  const ripe = ripeYard("home").length + ripeYard("orchard").length + ripeYard("greenhouse").length;
  const thirsty = thirstyYard("home").length + thirstyYard("orchard").length + thirstyYard("greenhouse").length;
  const seeds = ((me.seeds) || []).filter((s) => !s.tree);
  const lines = [
    seeds.length && idle ? `手里还有种子，菜地有 ${idle} 块空地。` : "空地没有种就去广场杂货铺买，种植面板只出背包里有的种。",
    thirsty ? `有 ${thirsty} 块能浇水，份地底下可一键浇。` : "浇过的地这一茬不用再浇。",
    ripe ? `有 ${ripe} 块已经熟了，份地底下可一键收。` : "熟了才会出现收获。急不来。",
    String(me.duty || "").includes("逾期") ? "酒吧考勤逾期了，去地图点酒吧洗碗。" : "酒吧每 2 天上一次工。地图里有酒吧。",
    Number(dues.tax_arrears) > 0 && Number(dues.upkeep_arrears) > 0
      ? "岸税和岸维都欠着。岸税是口袋按周交的票，岸维是地和屋子每天的维修。去潮生会分栏交。"
      : Number(dues.tax_arrears) > 0
        ? "欠岸税。口袋里的票，按周交。去潮生会岸税栏。"
        : Number(dues.upkeep_arrears) > 0
          ? "欠岸维。地和屋子每天的维修。去潮生会岸维栏。"
          : "岸税岸维没欠就不用跑潮生会。",
    "饿了去小馆或打开行囊吃。困了回小屋睡。",
  ];
  sheet.hidden = false;
  sheet.innerHTML = `
    <h2>现在可以做的</h2>
    ${lines.map((t) => `<div class="island-item"><span>${esc(t)}</span></div>`).join("")}
  `;
}
