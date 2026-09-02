const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");
const { test } = require("node:test");
const read = file => fs.readFileSync(path.resolve(__dirname, "..", file), "utf8");
const tick = () => new Promise(resolve => setImmediate(resolve));
function node() {
  return { hidden: false, disabled: false, attrs: {}, handlers: {}, dataset: {}, scrollTop: 0,
    setAttribute(k, v) { this.attrs[k] = v; }, addEventListener(k, fn) { this.handlers[k] = fn; },
    click() { return (this.onclick || this.handlers.click)?.({ stopPropagation() {} }); },
  };
}

test("the existing look-at-land entry opens exactly two choices and retains farming", () => {
  const tap = node(), choices = node(), plots = node(), events = node(), board = node();
  choices.hidden = true;
  const classes = new Set(["is-peek"]);
  const wrap = { querySelector: sel => ({ ".island-scene-tap": tap, ".island-yard-choices": choices, ".island-yards-board": board })[sel],
    classList: { contains: c => classes.has(c), remove: c => classes.delete(c) } };
  choices.querySelector = sel => sel.includes('"plots"') ? plots : events;
  let opened = 0;
  const context = vm.createContext({ state: { yardsShelf: false }, wrap, onEvents: w => { assert.equal(w, wrap); opened++; } });
  const source = read("server/static/island/scenes/home.js");
  vm.runInContext(source.replace(/^import[\s\S]*?;\r?\n/gm, "").replace(/export function /g, "function "), context);
  vm.runInContext("bindYardsPeek(wrap, onEvents)", context);
  tap.click();
  assert.equal(choices.hidden, false);
  assert.equal(context.state.yardsShelf, false);
  events.click();
  assert.equal(opened, 1);
  assert.equal(context.state.yardsShelf, false);
  plots.click();
  assert.equal(context.state.yardsShelf, true);
  assert.equal(classes.has("is-peek"), false);
  assert.equal((source.match(/data-yard-choice=/g) || []).length, 4); // two markup + two bindings
  assert.match(source, />看地<\/button>/);
  assert.match(source, />田间事件<\/button>/);
  const css = read("server/static/island/island.css");
  assert.match(css, /\.island-yards \.island-yard-choices\s*\{[^}]*bottom: 10px;/);
});

function setup() {
  let savedKey = "same-owner";
  let rows = [{ id: 1, label: "篱边意外", detail: "<script>bad</script>", repair_tickets: 30, can_pay_tickets: true, repair_item: "compost", repair_item_label: "堆肥", repair_qty: 2, can_pay_item: true }];
  let readWait = null, repairWait = null, error = null;
  const calls = { reads: 0, repairs: [], snapshots: 0, timers: [] };
  const host = node();
  host.isConnected = true;
  host.remove = () => { host.isConnected = false; };
  Object.defineProperty(host, "innerHTML", {
    get() { return this.html || ""; },
    set(s) {
      this.html = s;
      this.nodes = {};
      for(const sel of ["[data-close-events]", "[data-refresh-events]", ".island-farm-event-list"]) this.nodes[sel] = node();
      for(const attr of ["data-confirm-repair", "data-cancel-repair"]) if(s.includes(attr)) this.nodes[`[${attr}]`] = node();
      this.repairs = [...s.matchAll(/data-repair="(\d+)" data-payment="(\w+)"/g)].map(m => ({ ...node(), dataset: { repair: m[1], payment: m[2] } }));
    },
  });
  host.querySelector = sel => host.nodes?.[sel] || null;
  host.querySelectorAll = () => host.repairs;
  const wrap = { append() { host.isConnected = true; } };
  const api = {
    async farmEvents() { calls.reads++; const result = { tickets: 120, incidents: rows, history: [] }; if(readWait) await readWait; if(error) throw error; return result; },
    async repairFarmEvent(id, payment) { calls.repairs.push({ id, payment }); if(repairWait) await repairWait; rows = []; return { tickets: 90, incidents: [], history: [], event: { narrative: "已处理" } }; },
  };
  const context = vm.createContext({ api, loadKey: () => savedKey, esc: s => String(s).replaceAll("<", "&lt;"),
    document: { createElement: () => host },
    setTimeout(fn, delay) { const t = { fn, delay }; calls.timers.push(t); return t; }, clearTimeout(t) { if(t) t.cancelled = true; },
  });
  vm.runInContext(read("server/static/island/ui/farm-events.js").replace(/^import .*;\r?\n/gm, "").replace(/export function /g, "function "), context);
  return { host, calls, context, open() { context.openFarmEvents(wrap, () => calls.snapshots++); },
    waitRead(p) { readWait = p; }, waitRepair(p) { repairWait = p; }, fail(e) { error = e; }, changeKey() { savedKey = "other-owner"; } };
}

test("reading renders escaped incidents without a write; repair requires confirmation", async () => {
  const s = setup(); s.open(); await tick();
  assert.equal(s.calls.reads, 1);
  assert.equal(s.calls.repairs.length, 0);
  assert.match(s.host.innerHTML, /&lt;script>/);
  assert.match(s.host.innerHTML, /花 30 票处理/);
  assert.equal(s.calls.timers.at(-1).delay, 10000);
  s.host.repairs[0].click();
  assert.match(s.host.innerHTML, /确认处理/);
  assert.equal(s.calls.repairs.length, 0);
  await s.host.querySelector("[data-confirm-repair]").click();
  assert.deepEqual(s.calls.repairs, [{ id: 1, payment: "tickets" }]);
  assert.match(s.host.innerHTML, /目前没有待处理意外/);
  assert.equal(s.calls.snapshots, 1);
});

test("material choice sends item once even when confirmation is double tapped", async () => {
  const s = setup(); s.open(); await tick();
  let resolve; s.waitRepair(new Promise(r => resolve = r));
  s.host.repairs[1].click();
  const click = s.host.querySelector("[data-confirm-repair]").onclick;
  click(); click();
  assert.deepEqual(s.calls.repairs, [{ id: 1, payment: "item" }]);
  resolve(); await tick();
  assert.equal(s.calls.snapshots, 1);
});

test("cancel costs nothing; read failures offer a retry", async () => {
  const s = setup(); s.open(); await tick();
  s.host.repairs[0].click();
  s.host.querySelector("[data-cancel-repair]").click(); await tick();
  assert.equal(s.calls.repairs.length, 0);
  s.fail(new Error("网络暂断"));
  s.host.querySelector("[data-refresh-events]").click(); await tick();
  assert.match(s.host.innerHTML, /网络暂断/);
  assert.ok(s.host.querySelector("[data-refresh-events]"));
});

test("closing or switching credentials discards late reads and does not re-open", async () => {
  for(const action of ["close", "key"]) {
    const s = setup(); let resolve;
    s.waitRead(new Promise(r => resolve = r)); s.open();
    const old = s.host.innerHTML;
    if(action === "close") s.context.closeFarmEvents(); else s.changeKey();
    resolve(); await tick();
    assert.equal(s.host.innerHTML, old);
    assert.equal(s.calls.timers.length, 0);
    assert.equal(s.calls.repairs.length, 0);
  }
});

test("a late pre-repair refresh cannot restore an already resolved incident", async () => {
  const s = setup(); s.open(); await tick();
  let resolve; s.waitRead(new Promise(r => resolve = r));
  s.host.querySelector("[data-refresh-events]").click();
  s.host.repairs[0].click();
  await s.host.querySelector("[data-confirm-repair]").click();
  resolve(); await tick();
  assert.match(s.host.innerHTML, /目前没有待处理意外/);
  assert.match(s.host.innerHTML, /口袋 90 票/);
});
