function esc(s) {
  return String(s ?? '').replace(/[&<>"']/g, (c) => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[c]));
}

function ago(epoch) {
  return islandFmtStamp(epoch);
}

function medal(i) {
  return { 1: '①', 2: '②', 3: '③' }[i] || String(i);
}

function boardRowHtml(r, i, kind, { clickable = true } = {}) {
  const top = i <= 3 ? ' is-top' : '';
  const score = kind === 'tickets'
    ? `<strong>${esc(r.tickets)}</strong> 票`
    : `<strong>Lv${esc(r.level)}</strong> ${esc(r.title || '')}`;
  const sub = kind === 'tickets'
    ? `Lv${esc(r.level)} · ${esc(r.title || '')}`
    : `${esc(r.xp)} 入账 · ${esc(r.tickets)} 票`;
  const tag = clickable ? 'button' : 'div';
  const extra = clickable
    ? ` type="button" data-steward="${esc(r.id)}" data-name="${esc(r.name)}"`
    : '';
  return `
    <li>
      <${tag} class="board-row${top}${clickable ? ' is-hit' : ''}"${extra}>
        <span class="board-rank">${medal(i)}</span>
        <span class="board-who">
          <b>${esc(r.name)}</b>
          <small>${esc(r.badge || '')}</small>
        </span>
        <span class="board-score">${score}</span>
        <span class="board-sub">${sub}</span>
      </${tag}>
    </li>
  `;
}

function fillBoard(el, rows, kind, opts) {
  if (!el) return;
  if (!rows || !rows.length) {
    el.innerHTML = '<li class="muted">尚无登记管理员</li>';
    return;
  }
  el.innerHTML = rows.map((r, i) => boardRowHtml(r, i + 1, kind, opts)).join('');
}

function chip(panel, label, extraClass = '') {
  return `<button type="button" class="stat-chip${extraClass ? ' ' + extraClass : ''}" data-panel="${esc(panel)}" aria-expanded="false">${label}</button>`;
}

function scrollToSteward(id) {
  const el = document.getElementById(`steward-${id}`);
  if (!el) {
    if (!location.pathname.startsWith('/play')) {
      location.href = `/play?go=me`;
    }
    return false;
  }
  el.classList.add('is-focus');
  el.scrollIntoView({ behavior: 'smooth', block: 'center' });
  setTimeout(() => el.classList.remove('is-focus'), 2200);
  return true;
}

function bindStewardHits(root) {
  (root || document).addEventListener('click', (e) => {
    const hit = e.target.closest('[data-steward]');
    if (!hit) return;
    const id = hit.getAttribute('data-steward');
    if (!id) return;
    e.preventDefault();
    scrollToSteward(id);
  });
}
