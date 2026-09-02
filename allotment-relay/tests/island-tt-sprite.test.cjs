const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { test } = require("node:test");

const root = path.resolve(__dirname, "..");
const read = file => fs.readFileSync(path.join(root, file), "utf8");

test("Tt portrait moves down 24px without resizing or blocking shop controls", () => {
  const css = read("server/static/island/island.css");
  const stand = css.match(/\.island-tt-stand \{([^}]+)\}/)[1];
  assert.match(stand, /bottom: calc\(30% - 24px\)/);
  assert.match(stand, /height: 58%/);
  assert.match(stand, /left: 0/);
  assert.match(stand, /right: 0/);
  assert.match(stand, /z-index: 1/);
  assert.match(stand, /overflow: hidden/);
  assert.match(stand, /pointer-events: none/);
  const sprite = css.match(/\.island-tt-sprite \{([^}]+)\}/)[1];
  assert.match(sprite, /width: 100%/);
  assert.match(sprite, /height: auto/);
  const shelf = css.match(/\.island-shop-shelf \{([^}]+)\}/)[1];
  assert.match(shelf, /bottom: 10px/);
  assert.match(shelf, /z-index: 2/);
  assert.match(css, /\.island-shop\.is-peek \.island-tt-stand \{\s*display: none;/);
});

test("portrait uses the same asset and updated stylesheet cache key", () => {
  assert.match(read("server/static/island/scenes/shop.js"), /sprites\/tt.webp\?v=tt-sprite1/);
  assert.match(read("server/templates/island.html"), /island.css\?v=tt-lower1/);
  assert.match(read("server/static/island/assets/ART.md"), /整体比原位置下移24px/);
});
