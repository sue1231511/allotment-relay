const state = {
  key: '',
  enrolled: false,
  dash: null,
  seeds: [],
  places: [],
  climate: null,
  placeId: '',
};

function $(id) {
  return document.getElementById(id);
}

function esc(s) {
  return siteKeyEsc(s);
}

function show(el, on) {
  el.classList.toggle('hidden', !on);
}

function setNav(which) {
  document.querySelectorAll('.play-top-nav button').forEach((btn) => {
    btn.classList.toggle('is-on', btn.getAttribute('data-go') === which);
  });
}

function dutyUrgent(dash) {
  const line = (dash && dash.meter_lines && dash.meter_lines.bar_duty) || '';
  return line.startsWith('⚠');
}

async function api(tool, command) {
  const res = await fetch('/api/play', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key: state.key,
      tool: tool || '',
      command: command || '',
    }),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '做不成');
  return data;
}

function applySnap(data, text) {
  state.enrolled = Boolean(data.enrolled);
  state.dash = data.dashboard || null;
  state.seeds = data.seeds || [];
  state.places = data.places || [];
  state.climate = data.climate || null;
  if (text) setLog(text);
  if (!state.enrolled) {
    show($('play-main'), false);
    show($('play-gate'), true);
    show($('play-key-form'), false);
    show($('play-enroll-form'), true);
    $('play-who-btn').textContent = '未登记';
    return;
  }
  show($('play-gate'), false);
  show($('play-main'), true);
  renderAll();
}

function setLog(text) {
  const log = $('play-log');
  if (!text) {
    show(log, false);
    return;
  }
  log.textContent = text;
  show(log, true);
  const placeResult = $('play-place-result');
  if (state.placeId) placeResult.textContent = text;
}

function renderAll() {
  const d = state.dash;
  const c = state.climate || {};
  $('play-climate-mini').textContent = `${c.season || ''} · ${c.tide || ''} · ${c.weather || ''}`;
  $('play-who-btn').textContent = d.name || '已绑定';
  $('play-hello').textContent = `${d.name}，今天也在岛上`;
  $('play-motto').textContent = d.motto || '人和管家公用这一个号。';
  const energy = (d.meters && d.meters.energy) || 0;
  const emax = (d.meters && d.meters.energy_max) || 100;
  $('play-stats').innerHTML = `
    <div>精力 <b>${energy}</b> / ${emax}
      <div class="play-bar"><i style="width:${Math.max(4, Math.min(100, energy))}%"></i></div>
    </div>
    <div>工分票 <b>${d.tickets}</b></div>
    <div>等级 ${d.level || 1} · ${esc(d.title || '')}</div>
  `;
  const duty = (d.meter_lines && d.meter_lines.bar_duty) || '';
  const dutyEl = $('play-duty');
  dutyEl.textContent = duty;
  show(dutyEl, Boolean(duty && (dutyUrgent(d) || duty.includes('内须'))));
  renderPlots();
  renderPlaces();
  renderTide();
  renderTote();
  renderMemories();
  if (state.placeId) renderPlace(state.placeId);
}

function plotButtons(p) {
  const token = p.token || String(p.slot);
  const acts = [];
  if (p.state === 'fallow') {
    acts.push(`<button type="button" data-sow="${esc(token)}">播种</button>`);
  }
  if (p.state === 'growing' || p.state === 'tending') {
    if (!p.tended) acts.push(`<button type="button" data-act='{"tool":"plot_ops","command":"tend"}'>打理</button>`);
    if (!p.watered) acts.push(`<button type="button" data-act='{"tool":"plot_ops","command":"浇水 ${token}"}'>浇水</button>`);
    if (!p.fertilized) acts.push(`<button type="button" data-act='{"tool":"plot_ops","command":"施肥 ${token}"}'>施肥</button>`);
  }
  if (p.state === 'ready') {
    acts.push(`<button type="button" data-act='{"tool":"plot_ops","command":"gather ${token}"}'>收</button>`);
    if (p.shake) acts.push(`<button type="button" data-act='{"tool":"plot_ops","command":"shake ${token}"}'>摇</button>`);
  }
  if (p.state === 'overripe') {
    acts.push(`<button type="button" data-act='{"tool":"plot_ops","command":"compost ${token}"}'>堆肥</button>`);
    acts.push(`<button type="button" data-act='{"tool":"plot_ops","command":"gather ${token}"}'>清果</button>`);
  }
  return acts.join('');
}

function renderPlots() {
  const parcels = (state.dash && state.dash.parcels) || [];
  const shown = parcels.slice(0, 6);
  $('play-plots').innerHTML = shown.map((p) => `
    <article class="play-card ${p.state === 'ready' ? 'is-ready' : ''}">
      <span class="slot">${p.greenhouse ? '棚' : (p.orchard ? '园' : '份地')} ${esc(p.token || p.slot)}</span>
      <strong>${p.emoji || ''} ${esc(p.name)}</strong>
      <span class="detail">${esc(p.detail || '')}</span>
      <div class="acts">${plotButtons(p)}</div>
    </article>
  `).join('') || '<p class="play-empty">还没有地。</p>';
}

function renderPlaces() {
  const urgent = dutyUrgent(state.dash);
  $('play-places').innerHTML = (state.places || []).map((pl) => `
    <article class="play-card ${pl.duty && urgent ? 'is-duty' : ''}">
      <span class="slot">${pl.week1 ? '常去' : '出门'}</span>
      <strong>${esc(pl.name)}</strong>
      <span class="detail">${esc(pl.blurb)}</span>
      <button type="button" class="play-go" data-place="${esc(pl.id)}">前往</button>
    </article>
  `).join('');
}

function renderTide() {
  const c = state.climate || {};
  const voyage = (state.dash && state.dash.voyage) || '';
  $('play-tide-box').innerHTML = `
    <div class="play-tide-line">${esc(c.tide || '—')} · ${esc(c.phase || '')}</div>
    <p class="play-rule">${esc(c.season || '')} · ${esc(c.weather || '')}</p>
    ${voyage ? `<p class="play-rule">${esc(voyage)}</p>` : ''}
  `;
}

function renderTote() {
  const stock = ((state.dash && state.dash.stock) || []).slice(0, 8);
  if (!stock.length) {
    $('play-tote').innerHTML = '<p class="play-empty">口袋空着。</p>';
    return;
  }
  $('play-tote').innerHTML = stock.map((it) => `
    <button type="button" data-item="${esc(it.name)}" data-qty="${it.qty}">
      ${esc(it.name)} ×${it.qty}
    </button>
  `).join('');
}

function renderMemories() {
  const mem = (state.dash && state.dash.memories) || [];
  if (!mem.length) {
    $('play-memory-row').innerHTML = '<p class="play-empty">还没走完的故事不会出现。</p>';
    return;
  }
  $('play-memory-row').innerHTML = mem.slice(0, 6).map((m) => `
    <article class="play-memory">
      <small>${esc(m.kind === 'tale' ? '潮闻' : (m.kind === 'story' ? '故事' : '相遇'))}</small>
      <strong>${esc(m.title || m.key)}</strong>
      <p>${esc(m.blurb || '')}</p>
    </article>
  `).join('');
}

function extraPlaceActions(place) {
  const extra = [];
  const voyage = (state.dash && state.dash.voyage) || '';
  if (place.id === 'tide' && voyage.includes('黑旗')) {
    extra.push({ label: '打', tool: 'tide_ops', command: 'fight' });
    extra.push({ label: '逃', tool: 'tide_ops', command: 'flee' });
    extra.push({ label: '谈', tool: 'tide_ops', command: 'parley' });
  }
  if (place.id === 'tide' && voyage.includes('未命名')) {
    extra.push({ label: '礼遇', tool: 'tide_ops', command: 'compliment' });
    extra.push({ label: '动手', tool: 'tide_ops', command: 'catch' });
  }
  return extra;
}

function renderPlace(id) {
  const place = (state.places || []).find((p) => p.id === id);
  if (!place) return;
  state.placeId = id;
  show($('play-home'), false);
  show($('play-place'), true);
  setNav('places');
  $('play-place-title').textContent = place.name;
  $('play-place-blurb').textContent = place.blurb + (place.caution ? ' 新手别从这儿开局。' : '');
  const acts = (place.actions || []).concat(extraPlaceActions(place));
  $('play-place-actions').innerHTML = acts.map((a) => (
    `<button type="button" class="play-btn" data-act='${JSON.stringify({ tool: a.tool, command: a.command })}'>${esc(a.label)}</button>`
  )).join('');
  if (place.href) {
    $('play-place-actions').insertAdjacentHTML(
      'beforeend',
      `<a class="play-btn" href="${place.href}">打开网页</a>`
    );
  }
}

function goHome() {
  state.placeId = '';
  show($('play-place'), false);
  show($('play-home'), true);
  setNav('home');
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

function openSheet(title, html) {
  $('play-sheet-title').textContent = title;
  $('play-sheet-body').innerHTML = html;
  show($('play-sheet'), true);
}

function closeSheet() {
  show($('play-sheet'), false);
}

function sowSheet(token) {
  const seeds = (state.seeds || []).filter((s) => {
    const orchard = String(token).startsWith('园');
    const shed = String(token).startsWith('棚');
    if (orchard) return s.tree;
    if (shed) return true;
    return !s.tree;
  });
  if (!seeds.length) {
    setLog('口袋里没有能种在这儿的种。去份地边上的采集，或以后去杂货买。');
    return;
  }
  openSheet(`种到 ${token}`, seeds.map((s) => (
    `<button type="button" class="play-btn" data-act='{"tool":"plot_ops","command":"sow ${token} ${s.name}"}'>${s.emoji} ${s.name} ×${s.qty}</button> `
  )).join(''));
}

function itemSheet(name) {
  openSheet(name, `
    <button type="button" class="play-btn" data-act='{"tool":"kitchen_ops","command":"eat ${name}"}'>吃</button>
    <button type="button" class="play-btn" data-act='{"tool":"tote_ops","command":"vend ${name} 1"}'>卖 1</button>
  `);
}

async function act(tool, command) {
  try {
    document.querySelectorAll('.play-btn, .play-card .acts button, .play-go').forEach((b) => { b.disabled = true; });
    const data = await api(tool, command);
    applySnap(data, data.text || '');
    closeSheet();
  } catch (err) {
    setLog(err.message || String(err));
  } finally {
    document.querySelectorAll('button[disabled]').forEach((b) => { b.disabled = false; });
  }
}

async function bootWithKey(key) {
  state.key = key;
  saveSiteKey(key);
  const data = await api('', '');
  applySnap(data, '');
}

$('play-key-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const err = $('play-gate-err');
  err.hidden = true;
  try {
    await bootWithKey($('play-key').value.trim());
  } catch (ex) {
    err.hidden = false;
    err.textContent = ex.message;
  }
});

$('play-enroll-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = $('play-enroll-name').value.trim();
  const err = $('play-gate-err');
  err.hidden = true;
  try {
    const data = await api('steward_ops', `enroll ${name}`);
    applySnap(data, data.text || '');
  } catch (ex) {
    err.hidden = false;
    err.textContent = ex.message;
  }
});

$('play-who-btn').addEventListener('click', () => {
  if (!state.key) {
    show($('play-main'), false);
    show($('play-gate'), true);
    return;
  }
  if (confirm('清除本机凭证？管家页和上手页是同一份。')) {
    clearSiteKey();
    state.key = '';
    location.reload();
  }
});

document.querySelectorAll('.play-top-nav button').forEach((btn) => {
  btn.addEventListener('click', () => {
    const go = btn.getAttribute('data-go');
    if (go === 'home') {
      goHome();
      return;
    }
    if (go === 'places') {
      goHome();
      setNav('places');
      $('play-places').scrollIntoView({ behavior: 'smooth', block: 'start' });
      return;
    }
    if (go === 'memories') {
      goHome();
      setNav('memories');
      $('play-memories').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  });
});

$('play-place-back').addEventListener('click', goHome);
$('play-sheet-bg').addEventListener('click', closeSheet);
$('play-sheet-cancel').addEventListener('click', closeSheet);

document.body.addEventListener('click', (e) => {
  const sow = e.target.closest('[data-sow]');
  if (sow) {
    sowSheet(sow.getAttribute('data-sow'));
    return;
  }
  const place = e.target.closest('[data-place]');
  if (place) {
    renderPlace(place.getAttribute('data-place'));
    return;
  }
  const item = e.target.closest('#play-tote [data-item]');
  if (item) {
    itemSheet(item.getAttribute('data-item'));
    return;
  }
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  let payload;
  try {
    payload = JSON.parse(btn.getAttribute('data-act'));
  } catch {
    return;
  }
  act(payload.tool, payload.command);
});

(async function boot() {
  const saved = loadSavedKey();
  if (!saved) return;
  $('play-key').value = saved;
  try {
    await bootWithKey(saved);
  } catch (ex) {
    const err = $('play-gate-err');
    err.hidden = false;
    err.textContent = ex.message;
  }
})();
