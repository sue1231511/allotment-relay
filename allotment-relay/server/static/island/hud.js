import { state } from "./store.js";

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
}
