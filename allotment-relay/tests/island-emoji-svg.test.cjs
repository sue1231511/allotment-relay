const assert = require("node:assert/strict");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const { test } = require("node:test");

const mod = () => import(pathToFileURL(path.resolve(__dirname, "../server/static/island/ui/emoji-svg.js")).href);

test("emoji 换成手绘 SVG，文字和星级保留", async () => {
  const { withIcons } = await mod();
  const html = withIcons("鲭鱼 \u{1F41F} 3★ 剪刀✂️");
  assert.equal((html.match(/island-ico/g) || []).length, 2);
  assert.match(html, /<svg viewBox="0 0 24 24"/);
  assert.match(html, /3★/);
  assert.doesNotMatch(html, /[\u{1F300}-\u{1FAFF}✂]/u);
  assert.equal(withIcons("没有图标"), "没有图标");
});

test("不认识的 emoji 落到通用小圆点，不留 emoji", async () => {
  const { withIcons } = await mod();
  const html = withIcons("\u{1F9EC}");
  assert.match(html, /island-ico/);
  assert.doesNotMatch(html, /\u{1F9EC}/u);
});
