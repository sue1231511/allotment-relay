export function showEvent(event) {
  if (!event) return;
  const root = document.getElementById("island-modal");
  if (!root) return;
  root.hidden = false;
  root.innerHTML = `
    <article class="island-card">
      <h3>${esc(event.title || "岛上")}</h3>
      <p>${esc(event.narrative || "")}</p>
      <button type="button" class="island-btn primary wide" data-close-modal>收下</button>
    </article>
  `;
  root.querySelector("[data-close-modal]").addEventListener("click", hideModal);
  root.addEventListener("click", (ev) => {
    if (ev.target === root) hideModal();
  }, { once: true });
}

export function hideModal() {
  const root = document.getElementById("island-modal");
  if (!root) return;
  root.hidden = true;
  root.innerHTML = "";
}

export function toast(text) {
  const el = document.getElementById("island-toast");
  if (!el) return;
  el.hidden = false;
  el.textContent = text;
  clearTimeout(el._t);
  el._t = setTimeout(() => { el.hidden = true; }, 2800);
}

export function esc(s) {
  return String(s == null ? "" : s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}
