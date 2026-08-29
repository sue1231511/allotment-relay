export function renderMap(root, { onOpen }) {
  root.innerHTML = `
    <div class="island-map">
      <button type="button" class="island-map-hot is-garden" data-go="home" aria-label="菜园">
        <small>Garden</small><b>菜园</b>
      </button>
      <button type="button" class="island-pin is-shore" data-go="shore"><small>Tide</small><b>海边</b></button>
      <button type="button" class="island-pin is-plaza" data-go="plaza"><small>Plaza</small><b>岛心广场</b></button>
    </div>
  `;
  const bar = document.getElementById("island-actionbar");
  bar.innerHTML = `<p class="island-fine" style="grid-column:1/-1;margin:4px 2px 0">点左上角菜园进家园。点整片菜地就能种，不用选某一块。</p>`;
  root.querySelectorAll("[data-go]").forEach((btn) => {
    btn.addEventListener("click", () => onOpen(btn.getAttribute("data-go")));
  });
}
