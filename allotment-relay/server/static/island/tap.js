/** 橙光那种点按：落点闪星，能点的还会瘪一下。门页和地图共用。 */
(function () {
  if (window.__islandTapBound) return;
  window.__islandTapBound = true;

  var PRESS =
    "button, a.island-btn, .island-hot, .island-float-chip, .island-bag-slot:not(.is-empty), " +
    ".island-slot, .island-plot-tile, .island-plant-arrow, .island-plant-x, .island-plant-go, " +
    ".island-plant-buy, [data-go], [data-act], [data-tab], [data-eat], [data-vend], [data-page], " +
    "[data-close], [data-care], [data-yard], [data-href], [data-close-modal]";

  function burst(x, y) {
    var el = document.createElement("span");
    el.className = "island-spark";
    el.style.left = x + "px";
    el.style.top = y + "px";
    el.setAttribute("aria-hidden", "true");
    var bits = "<em></em>";
    var i;
    for (i = 0; i < 6; i++) {
      bits += '<i style="--a:' + (i * 60) + '"></i>';
    }
    el.innerHTML = bits;
    document.body.appendChild(el);
    window.setTimeout(function () {
      if (el.parentNode) el.parentNode.removeChild(el);
    }, 480);
  }

  function press(el) {
    if (!el || el.disabled || el.getAttribute("aria-hidden") === "true") return;
    if (el.classList.contains("is-empty")) return;
    el.classList.add("is-tap");
    var clear = function () {
      el.classList.remove("is-tap");
    };
    el.addEventListener("pointerup", clear, { once: true });
    el.addEventListener("pointercancel", clear, { once: true });
    el.addEventListener("pointerleave", clear, { once: true });
    window.setTimeout(clear, 260);
  }

  function onDown(ev) {
    if (ev.pointerType === "mouse" && ev.button !== 0) return;
    if (!document.body || !document.body.classList.contains("island-app")) return;
    var tag = ev.target && ev.target.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
    burst(ev.clientX, ev.clientY);
    var hit = ev.target && ev.target.closest ? ev.target.closest(PRESS) : null;
    if (hit) press(hit);
  }

  document.addEventListener("pointerdown", onDown, { passive: true });
})();
