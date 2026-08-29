export function renderMap(root, { onOpen }) {
  root.innerHTML = `
    <div class="island-map">
      <div class="island-map-sea" aria-hidden="true"></div>
      <div class="island-land" aria-hidden="true"></div>
      <button type="button" class="island-pin is-home" data-go="home"><small>Home</small><b>家园</b></button>
      <button type="button" class="island-pin is-shore" data-go="shore"><small>Tide</small><b>海边</b></button>
      <button type="button" class="island-pin is-plaza" data-go="plaza"><small>Plaza</small><b>岛心广场</b></button>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  bar.innerHTML = `<p class="island-fine" style="grid-column:1/-1;margin:4px 2px 0">点地点进去。种地、撒网、说话都是这个号。</p>`;
  root.querySelectorAll("[data-go]").forEach((btn) => {
    btn.addEventListener("click", () => onOpen(btn.getAttribute("data-go")));
  });
}
