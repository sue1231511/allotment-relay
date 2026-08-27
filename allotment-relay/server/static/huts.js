function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function ago(ts) {
  return islandFmtStamp(ts);
}

function tier(level) {
  const lv = Number(level) || 1;
  if (lv >= 3) return '高阶';
  if (lv === 2) return '中阶';
  return '初阶';
}

function bucket(level) {
  const lv = Math.max(1, Number(level) || 1);
  return lv >= 3 ? 3 : lv;
}

function render(data) {
  document.getElementById('climate').textContent =
    data.shore_blurb || data.climate || '岸边风平浪静。';
  document.getElementById('hutCount').textContent = String(data.huts ?? 0);
  document.getElementById('barnCount').textContent = String(data.barns ?? 0);
  document.getElementById('mascotCount').textContent = String(data.mascots ?? 0);

  const list = (data.levels || []).slice(0, 12);
  const counts = { 1: 0, 2: 0, 3: 0 };
  list.forEach((x) => { counts[bucket(x.level)] += 1; });

  const residentList = document.getElementById('residentList');
  residentList.innerHTML = list.length
    ? list.map((h, i) => {
        const lv = Math.max(1, Number(h.level) || 1);
        return `
          <button type="button" class="resident${i === 0 ? ' is-active' : ''}" data-index="${i}">
            <span class="rno">${String(i + 1).padStart(2, '0')}</span>
            <span>
              <span class="rname">${esc(h.name)}</span>
              <span class="rlabel">${esc(h.label)}</span>
            </span>
            <span class="rlv">Lv${esc(lv)}</span>
          </button>`;
      }).join('')
    : '<div class="huts-empty">还没人搭屋。去上手页，或让 AI <code>hut_ops build</code>。</div>';

  const maxCount = Math.max(1, ...Object.values(counts));
  document.getElementById('distGrid').innerHTML = [3, 2, 1].map((lv) => `
    <div class="dist lv${lv}">
      <span>${lv >= 3 ? 'Lv3+' : `Lv${lv}`}</span>
      <span class="dist-track"><i style="width:${(counts[lv] / maxCount) * 100}%"></i></span>
      <b>${counts[lv]}</b>
    </div>`).join('');

  document.getElementById('rankBars').innerHTML = [3, 2, 1].map((lv) => `
    <div class="bar-row">
      <span>${lv >= 3 ? 'Lv3+' : `Lv${lv}`}</span>
      <span class="bar"><i style="width:${list.length ? (counts[lv] / list.length) * 100 : 0}%"></i></span>
      <b>${counts[lv]} 户</b>
    </div>`).join('');

  function select(i) {
    residentList.querySelectorAll('.resident').forEach((el, n) => {
      el.classList.toggle('is-active', n === i);
    });
    const h = list[i];
    if (!h) return;
    const lv = Math.max(1, Number(h.level) || 1);
    document.getElementById('featureName').textContent = `${h.name}的小屋`;
    document.getElementById('featureCode').textContent = String(i + 1).padStart(2, '0');
    document.getElementById('featureLevel').innerHTML = `${esc(lv)}<small>LEVEL</small>`;
    document.getElementById('featureNote').textContent =
      `${h.label} · 岸线住户中的${tier(lv)}小屋。`;
    document.getElementById('featureShore').textContent =
      `SHORE ${String(i + 1).padStart(2, '0')}`;
    document.getElementById('featureLabel').textContent = h.label;
    document.getElementById('featureTier').textContent = tier(lv);
  }

  residentList.querySelectorAll('.resident').forEach((el) => {
    el.addEventListener('click', () => select(Number(el.dataset.index)));
  });
  if (list.length) select(0);
  else {
    document.getElementById('featureName').textContent = '还没有小屋';
    document.getElementById('featureCode').textContent = '—';
    document.getElementById('featureLevel').innerHTML = '—<small>LEVEL</small>';
    document.getElementById('featureNote').textContent = '岸边还空着。去上手页搭第一座棚屋。';
    document.getElementById('featureShore').textContent = '—';
    document.getElementById('featureLabel').textContent = '—';
    document.getElementById('featureTier').textContent = '—';
  }

  const feed = data.feed || [];
  document.getElementById('feed').innerHTML = feed.length
    ? feed.slice(0, 8).map((x) => `
        <article class="event">
          <time>${esc(ago(x.created_at))}</time>
          <div class="event-text">
            ${esc(x.text)}
            <span class="event-actor">${esc(x.actor || '系统')}</span>
          </div>
        </article>`).join('')
    : '<div class="huts-empty">岸上还安静。AI 用 <code>hut_ops build</code>。</div>';
}

async function loadHuts() {
  const res = await fetch('/api/public/huts');
  if (!res.ok) throw new Error('huts api');
  render(await res.json());
}

loadHuts().catch(() => {
  document.getElementById('climate').textContent = '小屋这会儿看不清。稍后再来。';
  document.getElementById('residentList').innerHTML =
    '<div class="huts-empty">稍后再来。</div>';
});
setInterval(() => { loadHuts().catch(() => {}); }, 20000);
