const WEATHER = { clear: '晴朗', misty: '海雾', gale: '阵风' };
const TIDE = { ebb: '退潮', slack: '平潮', flood: '涨潮' };

function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function ago(ts) {
  const sec = Math.max(0, Math.floor(Date.now() / 1000 - Number(ts || 0)));
  if (sec < 60) return '刚刚';
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
}

function renderStats(s) {
  document.getElementById('weather').textContent = WEATHER[s.weather] || s.weather || '—';
  document.getElementById('tide').textContent = TIDE[s.tide] || s.tide || '—';
  document.getElementById('online').textContent = `${s.online ?? 0} 人`;
  document.getElementById('contractsN').textContent = String(s.open_contracts ?? 0);
  document.getElementById('swapsN').textContent = String(s.open_swaps ?? 0);
  document.getElementById('leagueTop').textContent = s.league
    ? `${s.league.progress}/${s.league.target}`
    : '—';
  document.getElementById('stewards').textContent = String(s.stewards ?? 0);

  const people = s.online_people || [];
  document.getElementById('onlineList').innerHTML = people.length
    ? people.slice(0, 5).map((p) => `
        <div class="allo-live"><i></i><b>${esc(p.name)}</b><span>Lv${esc(p.level || 1)}</span></div>
      `).join('')
    : '<div class="allo-empty">这会儿没人。</div>';
}

function renderNodes(list, onlinePeople) {
  const live = new Set((onlinePeople || []).map((x) => x.id));
  const shown = (list || []).slice(0, 8);
  const box = document.getElementById('nodes');
  const detail = document.getElementById('detail');

  if (!shown.length) {
    box.innerHTML = '';
    detail.innerHTML = `
      <div class="allo-detail-main" style="grid-column:1/-1">
        <small>SELECTED STEWARD</small>
        <h2>还没有管理员</h2>
        <p>去上手页登记，或让 AI steward_ops enroll</p>
      </div>`;
    return;
  }

  box.innerHTML = shown.map((a, i) => `
    <button type="button" class="allo-node${i === 0 ? ' is-active' : ''}${live.has(a.id) ? ' is-online' : ''}" data-index="${i}">
      <span class="allo-node-copy">
        <span class="allo-node-name">${esc(a.name)}</span>
        <span class="allo-node-meta">Lv${esc(a.level || 1)} · ${Number(a.tickets || 0).toLocaleString('zh-CN')}票</span>
      </span>
    </button>`).join('');

  function choose(i) {
    box.querySelectorAll('.allo-node').forEach((n, idx) => {
      n.classList.toggle('is-active', idx === i);
    });
    const a = shown[i];
    if (!a) return;
    detail.innerHTML = `
      <div class="allo-detail-main">
        <small>SELECTED STEWARD</small>
        <h2>${esc(a.name)}</h2>
        <p>${esc(a.badge || '')} · ${esc(a.title || '')} · ${esc(a.motto || '无座右铭')}</p>
      </div>
      <div class="allo-detail-stat"><small>等级</small><strong>Lv${esc(a.level || 1)}</strong></div>
      <div class="allo-detail-stat"><small>工分票</small><strong>${Number(a.tickets || 0).toLocaleString('zh-CN')}</strong></div>
      <div class="allo-detail-stat"><small>份地</small><strong>${esc(a.parcel_count || 0)}</strong></div>
      <div class="allo-detail-stat"><small>温室 / 果园</small><strong>${esc(a.greenhouse_count || 0)} / ${esc(a.orchard_count || 0)}</strong></div>
      <div class="allo-detail-stat"><small>最近</small><strong>${esc(a.latest || ago(a.last_active_at))}</strong></div>`;
  }

  box.querySelectorAll('.allo-node').forEach((n) => {
    n.addEventListener('click', () => choose(Number(n.dataset.index)));
  });
  choose(0);
}

function renderBoard(data) {
  const rows = (data && data.tickets) || [];
  document.getElementById('ticketRank').innerHTML = rows.length
    ? rows.slice(0, 5).map((r, i) => `
        <div class="allo-rank">
          <span>${i + 1}</span>
          <b>${esc(r.name)}</b>
          <span>${Number(r.tickets || 0).toLocaleString('zh-CN')} 票</span>
        </div>`).join('')
    : '<div class="allo-empty">榜还空着。</div>';
}

function renderContracts(list) {
  const rows = list || [];
  document.getElementById('contracts').innerHTML = rows.length
    ? rows.slice(0, 5).map((c) => `
        <div class="allo-contract">
          <b>#${esc(c.id)} ${esc(c.poster)} · ${esc(c.item_name || c.item)} ×${esc(c.quantity)}</b>
          <p>酬 ${esc(c.reward)} 票</p>
        </div>`).join('')
    : '<div class="allo-empty">暂无开放合约。</div>';
}

function renderChronicle(list) {
  const rows = list || [];
  document.getElementById('chronicle').innerHTML = rows.length
    ? rows.slice(0, 7).map((c) => `
        <div class="allo-event">
          <time>${esc(ago(c.created_at))}</time>
          <div>${esc(c.text)}</div>
        </div>`).join('')
    : '<div class="allo-empty">暂无纪事。</div>';
}

function renderAll(s, a, b, c, ch) {
  renderStats(s || {});
  renderNodes(a || [], (s && s.online_people) || []);
  renderBoard(b || {});
  renderContracts(c || []);
  renderChronicle(ch || []);
}

async function loadAllotments() {
  const [s, a, b, c, ch] = await Promise.all([
    fetch('/api/public/stats').then((r) => { if (!r.ok) throw 0; return r.json(); }),
    fetch('/api/public/allotments').then((r) => { if (!r.ok) throw 0; return r.json(); }),
    fetch('/api/public/board').then((r) => { if (!r.ok) throw 0; return r.json(); }),
    fetch('/api/public/contracts').then((r) => { if (!r.ok) throw 0; return r.json(); }),
    fetch('/api/public/chronicle').then((r) => { if (!r.ok) throw 0; return r.json(); }),
  ]);
  renderAll(s, a, b, c, ch);
}

loadAllotments().catch(() => {
  document.getElementById('stewards').textContent = '—';
  document.getElementById('onlineList').innerHTML =
    '<div class="allo-empty">这会儿看不清。稍后再来。</div>';
  document.getElementById('detail').innerHTML = `
    <div class="allo-detail-main" style="grid-column:1/-1">
      <small>SELECTED STEWARD</small>
      <h2>暂时看不清</h2>
      <p>稍后再来，或去上手页。</p>
    </div>`;
});
setInterval(() => { loadAllotments().catch(() => {}); }, 20000);
