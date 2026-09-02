const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const root = path.resolve(__dirname, "..");
const read = (file) => fs.readFileSync(path.join(root, file), "utf8");

function setup() {
  const state = { me: {
    shadow_rep: 12, satiety: 0, mist_wit: 23, standing: 34, health: 45,
    energy: 56, tickets: 789, level: 3, island_bond: 67,
  } };
  const panels = {};
  for (const [id, keys] of [
    ["island-stats", ["shadow", "satiety", "mist", "standing", "health", "energy"]],
    ["island-status", ["tickets", "level", "bond"]],
    ["island-back-chip", []],
  ]) {
    const slots = Object.fromEntries(keys.map((key) => [key, { textContent: "—" }]));
    panels[id] = {
      hidden: true, slots,
      removeAttribute(name) { if (name === "hidden") this.hidden = false; },
      querySelector(selector) {
        const match = selector.match(/^\[data-k="(.+)"\]$/);
        return match ? slots[match[1]] || null : null;
      },
    };
  }
  const context = vm.createContext({ state, document: { getElementById: (id) => panels[id] } });
  for (const file of ["stats.js", "back-map.js"]) {
    const code = read(`server/static/island/ui/${file}`)
      .replace(/^import .*;\r?\n/gm, "")
      .replace(/export function /g, "function ");
    vm.runInContext(code, context, { filename: file });
  }
  return { state, panels, context };
}

test("original six stats and new three stats render together and refresh", () => {
  const { state, panels, context } = setup();
  context.setStatsChip(true);
  assert.equal(panels["island-stats"].hidden, false);
  assert.equal(panels["island-status"].hidden, false);
  assert.deepEqual(Object.values(panels["island-stats"].slots).map((s) => s.textContent),
    ["12", "0", "23", "34", "45", "56"]);
  assert.deepEqual(Object.values(panels["island-status"].slots).map((s) => s.textContent),
    ["789", "3", "67"]);
  state.me.energy = 88;
  state.me.tickets = 1000;
  context.paintStats();
  assert.equal(panels["island-stats"].slots.energy.textContent, "88");
  assert.equal(panels["island-status"].slots.tickets.textContent, "1000");
});

test("map, yards and undertide hide both panels; other locations restore both", () => {
  const { panels, context } = setup();
  for (const showStats of [false, true, false, true]) {
    context.setBackChip(true, () => {}, { showStats });
    assert.equal(panels["island-stats"].hidden, !showStats);
    assert.equal(panels["island-status"].hidden, !showStats);
  }
  context.setBackChip(false);
  assert.equal(panels["island-stats"].hidden, true);
  assert.equal(panels["island-status"].hidden, true);
  const app = read("server/static/island/app.js");
  assert.match(app, /showStats: name !== "yards" && name !== "undertide"/);
});

test("missing data uses a dash and missing panels do not block the other panel", () => {
  const { state, panels, context } = setup();
  delete panels["island-stats"];
  state.me = { tickets: null, level: "", island_bond: "invalid" };
  context.setStatsChip(true);
  assert.equal(panels["island-status"].hidden, false);
  assert.deepEqual(Object.values(panels["island-status"].slots).map((s) => s.textContent),
    ["—", "—", "—"]);
});

test("left and right panel styles are independent and use the correct assets", () => {
  const css = read("server/static/island/island.css");
  const left = css.match(/\.island-float-chip\.is-stats \{([^}]+)\}/)[1];
  const right = css.match(/\.island-float-chip\.is-status \{([^}]+)\}/g).at(-1);
  assert.match(left, /left: 4px/);
  assert.match(left, /right: auto/);
  assert.match(left, /stats-frame\.png/);
  assert.match(right, /left: auto/);
  assert.match(right, /right: 4px/);
  assert.match(right, /status-frame\.webp/);
  const hud = read("server/static/island/hud.js");
  const back = read("server/static/island/ui/back-map.js");
  assert.match(hud, /stats\.js\?v=dual-panels1/);
  assert.match(back, /stats\.js\?v=dual-panels1/);
});
