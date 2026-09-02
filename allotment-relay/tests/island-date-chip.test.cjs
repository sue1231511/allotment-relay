const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const root = path.resolve(__dirname, "..");
const read = file => fs.readFileSync(path.join(root, file), "utf8");
const tick = () => new Promise(resolve => setImmediate(resolve));

function setup() {
  function node() {
    return {
      hidden: true, disabled: false, attrs: {}, handlers: {}, innerHTML: "", focused: false,
      setAttribute(k, v) { this.attrs[k] = v; },
      addEventListener(k, fn) { this.handlers[k] = fn; },
      focus() { this.focused = true; },
    };
  }
  const chip = node(), badge = node(), close = node(), panel = node();
  chip.innerHTML = '<img src="chip-date.png"><span class="island-date-badge"></span>';
  chip.querySelector = sel => sel === ".island-date-badge" ? badge : null;
  panel.querySelector = sel => sel === "[data-date-close]" ? close : null;
  panel.querySelectorAll = () => [close];
  const classes = new Set(["is-playing"]);
  const calls = { reads: 0, responses: [], scenes: [], toasts: [], delay: 0 };
  let rows = [], error = null;
  const api = {
    async dates() { calls.reads++; if (error) throw error; return { dates: rows }; },
    async dateRespond(id, scene, accept) {
      calls.responses.push({ id, scene, accept });
      rows = rows.map(row => ({ ...row, status: "active", status_label: "同行中" }));
      return { dates: rows };
    },
  };
  const document = {
    hidden: false,
    getElementById: id => id === "island-date-chip" ? chip : null,
    createElement: tag => { assert.equal(tag, "section"); return panel; },
    body: { append(el) { assert.equal(el, panel); }, classList: {
      contains: key => classes.has(key), add: key => classes.add(key), remove: key => classes.delete(key),
    } },
  };
  const context = vm.createContext({ document, api, esc: s => String(s).replaceAll("<", "&lt;"),
    toast: s => calls.toasts.push(s), clearTimeout() {}, setTimeout(fn, delay) { calls.delay = delay; return 1; } });
  vm.runInContext(read("server/static/island/ui/companion-date.js")
    .replace(/^import .*;\r?\n/gm, "").replace(/export function /g, "function "), context);
  context.mountDates(async scene => { calls.scenes.push(scene); context.dateSceneChanged(scene); });
  return { chip, panel, badge, close, classes, calls, context,
    rows(value) { rows = value; }, error(value) { error = value; },
    clickControl(selector, dataset = {}) {
      return panel.handlers.click({ target: { closest: sel => sel === selector ? { dataset } : null } });
    },
  };
}

function invitation(extra = {}) {
  return { id: 1, scene: "eatery", place: "小馆", status: "pending", status_label: "待应邀", kind_label: "约会",
    title: "一起听雨", seq: 0, total_spent: 188, history: [], current: null, note: "一起听雨", ...extra };
}

test("icon is a root sibling before bag; shares top and height with bag", () => {
  const html = read("server/templates/island.html");
  assert.equal((html.match(/id="island-date-chip"/g) || []).length, 1);
  assert.ok(html.indexOf('id="island-date-chip"') < html.indexOf('id="island-bag-chip"'));
  assert.match(html, /class="island-float-chip is-date"/);
  assert.match(html, /aria-controls="island-date-panel"/);
  assert.match(html, /src="\/static\/island\/assets\/chip-date.png"/);
  const css = read("server/static/island/island.css");
  const shared = css.match(/\.island-float-chip\.is-bag,\s*\.island-float-chip\.is-date,[^{]+\{([^}]+)\}/)[1];
  assert.match(shared, /top: env\(safe-area-inset-top, 0px\)/);
  assert.match(shared, /height: 66px/);
  assert.match(shared, /align-items: center/);
  const dateCss = read("server/static/island/companion-date.css");
  assert.match(dateCss, /right:calc\(min\(58px, 16%\) \+ min\(88px, 24%\) \+ 8px\)/);
  assert.match(dateCss, /width:44px/);
  assert.match(dateCss, /z-index:10/); // above transparent edges of back-map artwork at narrow widths
  assert.doesNotMatch(dateCss, /bottom:calc\(20px|left:50%|translateX\(-50%\)/);
  for (const width of [280, 320, 375, 414, 768, 1200]) {
    const bagRight = Math.min(58, width * .16), bagWidth = Math.min(88, width * .24);
    const bagLeft = width - bagRight - bagWidth, dateRight = bagLeft - 8, dateLeft = dateRight - 44;
    assert.ok(dateLeft >= 0);
    assert.equal(bagLeft - dateRight, 8);
    assert.ok(dateRight < bagLeft);
  }
  const asset = fs.readFileSync(path.join(root, "server/static/island/assets/chip-date.png"));
  assert.equal(asset.toString("hex", 0, 8), "89504e470d0a1a0a");
  assert.equal(asset[25], 6); // RGBA PNG; preserve original transparency.
  assert.match(html, /companion-date.css\?v=date-chip1/);
  assert.match(html, /app.js\?v=date-chip1/);
  assert.match(read("server/static/island/app.js"), /companion-date.js\?v=date-chip1/);
});

test("empty account opens a useful panel on map and click/refresh never accepts or spends", async () => {
  const ui = setup();
  ui.context.dateSceneChanged("map");
  await tick();
  assert.equal(ui.chip.hidden, false);
  assert.equal(ui.badge.hidden, true);
  await ui.chip.handlers.click();
  await tick();
  assert.equal(ui.panel.hidden, false);
  assert.match(ui.panel.innerHTML, /还没有约会邀请/);
  assert.match(ui.panel.innerHTML, /不会发起约会、生成剧情或扣票/);
  assert.equal(ui.chip.attrs["aria-expanded"], "true");
  assert.equal(ui.close.focused, true);
  await ui.clickControl("[data-date-refresh]");
  await tick();
  assert.ok(ui.calls.reads >= 3);
  assert.deepEqual(ui.calls.responses, []);
  assert.deepEqual(ui.calls.scenes, []);
  assert.equal(ui.calls.delay, 2500);
  await ui.clickControl("[data-date-close]");
  assert.equal(ui.panel.hidden, true);
  assert.equal(ui.chip.attrs["aria-expanded"], "false");
  assert.equal(ui.chip.focused, true);
});

test("pending invitation navigates before explicit acceptance; badge and icon survive refresh", async () => {
  const ui = setup();
  const iconMarkup = ui.chip.innerHTML;
  ui.rows([invitation()]);
  ui.context.dateSceneChanged("plaza");
  await tick();
  assert.equal(ui.badge.hidden, false);
  assert.match(ui.chip.attrs["aria-label"], /小馆待应邀/);
  await ui.chip.handlers.click();
  await tick();
  assert.deepEqual(ui.calls.scenes, ["eatery"]);
  assert.match(ui.panel.innerHTML, /应邀，一起走/);
  assert.deepEqual(ui.calls.responses, []);
  await ui.clickControl("[data-date-respond]", { dateRespond: "yes" });
  assert.deepEqual(ui.calls.responses, [{ id: 1, scene: "eatery", accept: true }]);
  assert.match(ui.panel.innerHTML, /还没有第一幕旁白/);
  assert.equal(ui.chip.innerHTML, iconMarkup);
  assert.doesNotMatch(ui.panel.innerHTML, /<input|<textarea|data-date-choose/);
});

test("active date shows narration; completed date opens memories without navigation", async () => {
  for (const status of ["active", "completed"]) {
    const ui = setup();
    ui.rows([invitation({ status, seq: 2, current: { kind: "event", title: "听雨", narrative: "两人坐在窗边。", options: [] } })]);
    ui.context.dateSceneChanged("eatery");
    await tick();
    await ui.chip.handlers.click();
    await tick();
    assert.match(ui.panel.innerHTML, /两人坐在窗边/);
    assert.equal(ui.badge.hidden, status === "completed");
    assert.deepEqual(ui.calls.scenes, []);
    assert.deepEqual(ui.calls.responses, []);
    ui.panel.handlers.keydown({ key: "Escape" });
    assert.equal(ui.panel.hidden, true);
  }
});

test("network failure has a retry hint; scene changes and logout close the panel", async () => {
  const ui = setup();
  ui.error(new Error("offline"));
  ui.context.dateSceneChanged("plaza");
  await tick();
  await ui.chip.handlers.click();
  await tick();
  assert.match(ui.panel.innerHTML, /暂时没能读取约会/);
  ui.error(null);
  await ui.clickControl("[data-date-refresh]");
  await tick();
  assert.match(ui.panel.innerHTML, /还没有约会邀请/);
  ui.context.dateSceneChanged("hut");
  assert.equal(ui.panel.hidden, true);
  await tick();
  await ui.chip.handlers.click();
  ui.classes.delete("is-playing");
  ui.context.resetDates();
  assert.equal(ui.panel.hidden, true);
  assert.equal(ui.chip.hidden, true);
  assert.equal(ui.chip.attrs["aria-expanded"], "false");
});

test("tutorials point at the same date icon and preserve AI-led gameplay", () => {
  for (const file of ["README.md", "../README.md", "server/game.py", "server/marriage.py", "server/templates/partials/island-manual-content.html"]) {
    assert.match(read(file), /背包左边/);
    assert.match(read(file), /同一水平/);
  }
  assert.match(read("server/mcp_app.py"), /背包左侧图标应邀/);
  assert.match(read("server/static/island/assets/ART.md"), /chip-date.png/);
});
