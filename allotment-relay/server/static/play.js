const state = {
  key: '',
  enrolled: false,
  dash: null,
  seeds: [],
  places: [],
  climate: null,
  placeId: '',
  eaterySnap: { shops: [] },
};

function $(id) {
  return document.getElementById(id);
}

function esc(s) {
  return siteKeyEsc(s);
}

function show(el, on) {
  if (!el) return;
  el.classList.toggle('hidden', !on);
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
  $('play-motto').textContent = d.motto || '人和管家公用这一个号。';
  const energy = (d.meters && d.meters.energy) || 0;
  const emax = (d.meters && d.meters.energy_max) || 100;
  $('play-energy').textContent = `精力 ${energy} / ${emax}`;
  $('play-tickets').textContent = `工分票 ${d.tickets}`;
  $('play-level').textContent = `等级 ${d.level || 1} · ${d.title || ''}`;
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
    acts.push(`<button type="button" class="btn" data-sow="${esc(token)}">播种</button>`);
  }
  if (p.state === 'growing' || p.state === 'tending') {
    if (!p.tended) acts.push(`<button type="button" class="btn" data-act='{"tool":"plot_ops","command":"tend"}'>打理</button>`);
    if (!p.watered) acts.push(`<button type="button" class="btn" data-act='{"tool":"plot_ops","command":"浇水 ${token}"}'>浇水</button>`);
    if (!p.fertilized) acts.push(`<button type="button" class="btn" data-act='{"tool":"plot_ops","command":"施肥 ${token}"}'>施肥</button>`);
  }
  if (p.state === 'ready') {
    acts.push(`<button type="button" class="btn" data-act='{"tool":"plot_ops","command":"gather ${token}"}'>收</button>`);
    if (p.shake) acts.push(`<button type="button" class="btn" data-act='{"tool":"plot_ops","command":"shake ${token}"}'>摇</button>`);
  }
  if (p.state === 'overripe') {
    acts.push(`<button type="button" class="btn" data-act='{"tool":"plot_ops","command":"compost ${token}"}'>堆肥</button>`);
    acts.push(`<button type="button" class="btn" data-act='{"tool":"plot_ops","command":"gather ${token}"}'>清果</button>`);
  }
  return acts.join('');
}

function renderPlots() {
  const parcels = (state.dash && state.dash.parcels) || [];
  const shown = parcels.slice(0, 6);
  $('play-plots').innerHTML = shown.map((p) => `
    <article class="card play-card ${p.state === 'ready' ? 'is-ready' : ''}">
      <span class="slot">${p.greenhouse ? '棚' : (p.orchard ? '园' : '份地')} ${esc(p.token || p.slot)}</span>
      <strong>${p.emoji || ''} ${esc(p.name)}</strong>
      <span class="detail">${esc(p.detail || '')}</span>
      <div class="acts">${plotButtons(p)}</div>
    </article>
  `).join('') || '<p class="muted">还没有地。</p>';
}

function renderPlaces() {
  const urgent = dutyUrgent(state.dash);
  $('play-places').innerHTML = (state.places || []).map((pl) => `
    <article class="card play-card ${pl.duty && urgent ? 'is-duty' : ''}">
      <span class="slot">${pl.week1 ? '常去' : '出门'}</span>
      <strong>${esc(pl.name)}</strong>
      <span class="detail">${esc(pl.blurb)}</span>
      <button type="button" class="btn primary play-go" data-place="${esc(pl.id)}">前往</button>
    </article>
  `).join('');
}

function renderTide() {
  const c = state.climate || {};
  const voyage = (state.dash && state.dash.voyage) || '';
  $('play-tide-box').innerHTML = `
    <div class="play-tide-line">${esc(c.tide || '—')} · ${esc(c.phase || '')}</div>
    <p class="muted">${esc(c.season || '')} · ${esc(c.weather || '')}</p>
    ${voyage ? `<p class="muted">${esc(voyage)}</p>` : ''}
  `;
}

function renderTote() {
  const stock = ((state.dash && state.dash.stock) || []).slice(0, 8);
  if (!stock.length) {
    $('play-tote').innerHTML = '<p class="muted">口袋空着。</p>';
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
    $('play-memory-row').innerHTML = '<p class="muted">还没走完的故事不会出现。</p>';
    return;
  }
  $('play-memory-row').innerHTML = mem.slice(0, 6).map((m) => `
    <article class="card play-memory">
      <small>${esc(m.kind === 'tale' ? '潮闻' : (m.kind === 'story' ? '故事' : '相遇'))}</small>
      <strong>${esc(m.title || m.key)}</strong>
      <p class="muted">${esc(m.blurb || '')}</p>
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

function hidePatron() {
  show($('play-patron'), false);
  ['play-patron-bar', 'play-patron-eatery', 'play-patron-star'].forEach((id) => show($(id), false));
}

function renderPlace(id) {
  const place = (state.places || []).find((p) => p.id === id);
  if (!place) return;
  state.placeId = id;
  show($('play-home'), false);
  show($('play-place'), true);
  $('play-place-title').textContent = place.name;
  $('play-place-blurb').textContent = place.blurb + (place.caution ? ' 新手别从这儿开局。' : '');
  const acts = (place.actions || []).concat(extraPlaceActions(place));
  $('play-place-actions').innerHTML = acts.map((a) => (
    `<button type="button" class="btn" data-act='${JSON.stringify({ tool: a.tool, command: a.command })}'>${esc(a.label)}</button>`
  )).join('');
  if (place.href) {
    $('play-place-actions').insertAdjacentHTML(
      'beforeend',
      `<a class="btn" href="${place.href}">打开网页</a>`
    );
  }
  hidePatron();
  if (id === 'bar' || id === 'eatery' || id === 'star') {
    show($('play-patron'), true);
    show($(`play-patron-${id}`), true);
    bindPatronPanels();
    if (id === 'bar') loadBarPatron();
    if (id === 'eatery') loadEateryPatron();
  }
}

function goHome() {
  state.placeId = '';
  show($('play-place'), false);
  show($('play-home'), true);
  hidePatron();
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
    `<button type="button" class="btn" data-act='{"tool":"plot_ops","command":"sow ${token} ${s.name}"}'>${s.emoji} ${s.name} ×${s.qty}</button> `
  )).join(''));
}

function itemSheet(name) {
  openSheet(name, `
    <button type="button" class="btn" data-act='{"tool":"kitchen_ops","command":"eat ${name}"}'>吃</button>
    <button type="button" class="btn" data-act='{"tool":"tote_ops","command":"vend ${name} 1"}'>卖 1</button>
  `);
}

async function act(tool, command) {
  try {
    document.querySelectorAll('.play-page button.btn, .play-go').forEach((b) => { b.disabled = true; });
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

function bindPatronPanels() {
  const name = (state.dash && state.dash.name) || '';
  const bound = name ? { name } : null;
  renderPatronBind($('play-bar-bind'), bound, '点单');
  renderPatronBind($('play-eatery-bind'), bound, '点餐');
  renderPatronBind($('play-star-bind'), bound, '打赏');
  const duoA = $('play-duo-bind');
  if (duoA) {
    if (name) {
      duoA.classList.remove('is-unbound');
      duoA.innerHTML = `<p class="patron-who">岸上人 A：本机管家「${esc(name)}」</p>`;
    } else {
      renderPatronBind(duoA, null, '立案');
    }
  }
}

async function postJson(url, body) {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '没做成');
  return data;
}

function showResult(id, html) {
  const box = $(id);
  box.classList.remove('hidden');
  box.innerHTML = html;
}

async function refreshAfterPatron() {
  const data = await api('', '');
  applySnap(data, '');
}

async function loadBarPatron() {
  const data = await fetch('/api/public/bar').then((r) => r.json());
  if (state.placeId !== 'bar') return;
  const serviceSel = $('play-bar-service');
  const prevService = serviceSel.value;
  serviceSel.innerHTML = (data.services || []).map((s) =>
    `<option value="${esc(s.key)}">${s.emoji} ${esc(s.name)} — ${s.cost} 票</option>`
  ).join('');
  if ([...serviceSel.options].some((o) => o.value === prevService)) serviceSel.value = prevService;

  const hostSel = $('play-bar-host');
  const prevHost = hostSel.value;
  hostSel.innerHTML = '<option value="">随机安排</option>' + (data.hosts || []).map((h) =>
    `<option value="${esc(h.name)}">${esc(h.name)} · ${esc(h.badge || '')}</option>`
  ).join('');
  if ([...hostSel.options].some((o) => o.value === prevHost)) hostSel.value = prevHost;

  const nudgeSel = $('play-duo-nudge');
  if (!nudgeSel.options.length && data.duo_nudges) {
    nudgeSel.innerHTML = data.duo_nudges.map((n) =>
      `<option value="${esc(n.key)}">${n.emoji} ${esc(n.name)} — ${esc(n.desc)}</option>`
    ).join('');
  }

  const status = $('play-duo-status');
  const form = $('play-duo-form');
  const submit = $('play-duo-submit');
  if (data.duo) {
    status.textContent = `今晚已立案 · ${data.duo.emoji} ${data.duo.name} · ${data.duo.patron_a} × ${data.duo.patron_b}`;
    form.classList.add('hidden');
    return;
  }
  if (!data.open) {
    status.textContent = '酒吧歇业（暮/夜开放）。双人吧台也只能在营业时立案。';
    form.classList.add('hidden');
    return;
  }
  status.textContent = `尚未立案。本机管家是岸上人 A，再填另一人的凭证，各扣 ${data.duo_cost_each || 6} 票。`;
  form.classList.remove('hidden');
  submit.textContent = `双人立案 · 各扣 ${data.duo_cost_each || 6} 票`;
}

function currentEateryShop() {
  const name = $('play-eatery-shop').value;
  return (state.eaterySnap.shops || []).find((s) => s.name === name) || state.eaterySnap.shops[0];
}

function fillEateryMenu(shop) {
  const itemSel = $('play-eatery-item');
  const prev = itemSel.value;
  if (!shop || !shop.menu.length) {
    itemSel.innerHTML = '<option value="">店内推荐</option>';
    return;
  }
  itemSel.innerHTML = '<option value="">店内推荐</option>' + shop.menu.map((m) =>
    `<option value="${esc(m.item)}">${esc(m.name)} — ${m.price} 票</option>`
  ).join('');
  if ([...itemSel.options].some((o) => o.value === prev)) itemSel.value = prev;
}

async function loadEateryPatron() {
  state.eaterySnap = await fetch('/api/public/eatery').then((r) => r.json());
  if (state.placeId !== 'eatery') return;
  const shopSel = $('play-eatery-shop');
  const prevShop = shopSel.value;
  shopSel.innerHTML = state.eaterySnap.shops.length
    ? state.eaterySnap.shops.map((s) =>
        `<option value="${esc(s.name)}">${esc(s.label)} · ${esc(s.name)}（${s.menu.length} 道）</option>`
      ).join('')
    : '<option value="">暂无开张小馆</option>';
  if ([...shopSel.options].some((o) => o.value === prevShop)) shopSel.value = prevShop;
  fillEateryMenu(currentEateryShop());
}

$('play-key-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const err = $('play-gate-err');
  err.classList.add('hidden');
  try {
    await bootWithKey($('play-key').value.trim());
  } catch (ex) {
    err.classList.remove('hidden');
    err.textContent = ex.message;
  }
});

$('play-enroll-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const name = $('play-enroll-name').value.trim();
  const err = $('play-gate-err');
  err.classList.add('hidden');
  try {
    const data = await api('steward_ops', `enroll ${name}`);
    applySnap(data, data.text || '');
  } catch (ex) {
    err.classList.remove('hidden');
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

$('play-place-back').addEventListener('click', goHome);
$('play-sheet-bg').addEventListener('click', closeSheet);
$('play-sheet-cancel').addEventListener('click', closeSheet);

$('play-eatery-shop').addEventListener('change', () => fillEateryMenu(currentEateryShop()));

$('play-bar-order').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const data = await postJson('/api/bar/order', {
      api_key: state.key,
      service: $('play-bar-service').value,
      host_name: $('play-bar-host').value || null,
    });
    showResult('play-bar-order-result', `
      <p><strong>下单成功</strong></p>
      <p>${esc(data.patron)} 点了 ${esc(data.service)}（-${data.cost} 票）· 值班 ${esc(data.host)}</p>
      <p>${esc(data.message)}</p>
      <p class="muted">剩余 ${data.tickets_left} 票</p>
    `);
    await refreshAfterPatron();
    await loadBarPatron();
  } catch (err) {
    showResult('play-bar-order-result', `<p class="error">${esc(err.message)}</p>`);
  }
});

$('play-duo-form').addEventListener('submit', async (e) => {
  e.preventDefault();
  const keyB = $('play-duo-key-b').value.trim();
  if (state.key === keyB) {
    showResult('play-duo-result', '<p class="error">必须是两名不同的岸上人，不能填同一个凭证</p>');
    return;
  }
  try {
    const data = await postJson('/api/bar/duo', {
      api_key_a: state.key,
      api_key_b: keyB,
      nudge: $('play-duo-nudge').value,
    });
    showResult('play-duo-result', `
      <p><strong>${esc(data.emoji)} ${esc(data.name)} · 立案成功</strong></p>
      <p>${esc(data.patron_a)} × ${esc(data.patron_b)}</p>
      <p>${esc(data.message)}</p>
    `);
    $('play-duo-key-b').value = '';
    await refreshAfterPatron();
    await loadBarPatron();
  } catch (err) {
    showResult('play-duo-result', `<p class="error">${esc(err.message)}</p>`);
  }
});

$('play-eatery-order').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const data = await postJson('/api/eatery/order', {
      api_key: state.key,
      shop: $('play-eatery-shop').value,
      item: $('play-eatery-item').value || null,
    });
    showResult('play-eatery-order-result', `
      <p><strong>吃完了</strong></p>
      <p>${esc(data.message || '').replaceAll('\n', '<br>')}</p>
      <p class="muted">剩余 ${data.tickets_left} 票</p>
    `);
    await refreshAfterPatron();
    await loadEateryPatron();
  } catch (err) {
    showResult('play-eatery-order-result', `<p class="error">${esc(err.message)}</p>`);
  }
});

$('play-star-tip').addEventListener('submit', async (e) => {
  e.preventDefault();
  try {
    const data = await postJson('/api/star/tip', {
      api_key: state.key,
      amount: parseInt($('play-star-amount').value, 10),
      note: $('play-star-note').value.trim(),
    });
    showResult('play-star-tip-result', `
      <p><strong>打赏送达</strong></p>
      <p>${esc(data.message)}</p>
      <p class="muted">剩余 ${data.tickets_left} 票</p>
    `);
    await refreshAfterPatron();
  } catch (err) {
    showResult('play-star-tip-result', `<p class="error">${esc(err.message)}</p>`);
  }
});

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
    err.classList.remove('hidden');
    err.textContent = ex.message;
  }
})();
