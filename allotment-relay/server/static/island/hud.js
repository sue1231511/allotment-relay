import { state } from "./store.js?v=island-hutscene1";

export function renderHud() {
  const me = state.me || {};
  const name = document.getElementById("hud-name");
  const lv = document.getElementById("hud-lv");
  const energy = document.getElementById("hud-energy");
  const tickets = document.getElementById("hud-tickets");
  if (name) name.textContent = me.name || (state.enrolled ? "岛民" : "未绑定");
  if (lv) lv.textContent = me.level ? `Lv ${me.level}` : "Lv —";
  if (energy) energy.textContent = me.energy == null ? "—" : `${me.energy}/${me.energy_max || 100}`;
  if (tickets) tickets.textContent = me.tickets == null ? "—" : String(me.tickets);
  const ribbon = document.getElementById("island-ribbon");
  if (!ribbon) return;
  const notes = [];
  const dues = me.dues || {};
  if (String(me.duty || "").includes("逾期")) notes.push({ go: "bar", text: "酒吧考勤逾期，去洗碗。" });
  if (Number(dues.tax_arrears) > 0) notes.push({ go: "hui", text: `欠岸税 ${dues.tax_arrears}。` });
  if (Number(dues.upkeep_arrears) > 0) notes.push({ go: "hui", text: `欠岸维 ${dues.upkeep_arrears}。` });
  if (me.satiety != null && Number(me.satiety) <= 20) notes.push({ go: "eatery", text: "饿了，去小馆或打开行囊吃一口。" });
  ribbon.hidden = notes.length === 0;
  ribbon.innerHTML = notes.map((n) => `<button type="button" data-go="${n.go}">${n.text}</button>`).join("");
}
