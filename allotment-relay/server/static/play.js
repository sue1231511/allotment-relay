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
  renderGifts();
  renderMemories();
  if (state.placeId) renderPlace(state.placeId);
  consumeGo();
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

function renderGifts() {
  const gifts = (state.dash && state.dash.gifts) || [];
  if (!gifts.length) {
    $('play-gifts').innerHTML = '<p class="muted">暂无收礼 / 打赏</p>';
    return;
  }
  $('play-gifts').innerHTML = gifts.slice(0, 6).map((g) => `
    <div class="item">
      <span class="muted">${esc(g.kind)}</span>
      <strong>${esc(g.who)}</strong>
      <p class="muted">${esc(g.text)}</p>
    </div>
  `).join('');
}

const MEMORY_KIND_LABELS = { tale: '潮闻', story: '故事', npc: '相遇' };
let memoryCatalog = [];
let memoryFilter = 'all';
let activeMemory = null;
let activeMemoryChapter = 0;
let continuousMemoryMode = false;

function fmtMemoryDate(epoch) {
  if (!epoch) return '已收录';
  return new Date(Number(epoch) * 1000).toLocaleDateString('zh-CN', {
    year: 'numeric', month: 'long', day: 'numeric',
  });
}

function multiline(value) {
  return esc(value).replace(/\n/g, '<br>');
}

function renderMemories() {
  memoryCatalog = (state.dash && state.dash.memories) || [];
  const root = $('memories');
  const visible = memoryFilter === 'all'
    ? memoryCatalog
    : memoryCatalog.filter((item) => item.kind === memoryFilter);
  if (!visible.length) {
    root.innerHTML = '<p class="muted">还没走完的故事不会出现。</p>';
    return;
  }
  root.innerHTML = visible.map((item) => {
    const index = memoryCatalog.indexOf(item);
    const variants = item.variants || [];
    const chooser = variants.length > 1 ? `
      <label class="memory-variant-label">
        <span>选择结局</span>
        <select data-memory-variant-select="${index}">
          ${variants.map((v, i) => `<option value="${i}">${esc(v.label)}</option>`).join('')}
        </select>
      </label>` : '';
    const count = Number(item.chapter_count) > 0 ? `${item.chapter_count} 幕` : '旧档案';
    return `
      <article class="memory-card kind-${esc(item.kind)}" data-memory-card="${index}">
        <div class="memory-card-top">
          <span class="memory-kind">${esc(MEMORY_KIND_LABELS[item.kind] || item.kind)}</span>
          <time>${esc(fmtMemoryDate(item.completed_at))}</time>
        </div>
        <h3>《${esc(item.title)}》</h3>
        <p class="memory-blurb">${esc(item.blurb)}</p>
        <div class="memory-card-meta">
          <span>${esc(count)}</span>
          ${item.ending ? `<span>${esc(item.ending)}</span>` : ''}
        </div>
        <div class="memory-card-action">
          ${chooser}
          <button type="button" class="btn primary memory-watch" data-memory-watch="${index}">再次观看</button>
        </div>
      </article>`;
  }).join('');
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
  if (window.playLounge) window.playLounge.stop();
  show($('play-lounge'), false);
  if (id === 'lounge') {
    show($('play-lounge'), true);
    if (window.playLounge) window.playLounge.start();
  }
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
  show($('play-lounge'), false);
  if (window.playLounge) window.playLounge.stop();
  window.scrollTo({ top: 0, behavior: 'smooth' });
}

let goApplied = false;
function consumeGo() {
  if (goApplied || !state.enrolled) return;
  const go = new URLSearchParams(location.search).get('go') || '';
  if (!go) return;
  goApplied = true;
  if (go === 'me') openMe();
  else renderPlace(go);
}

function openMe() {
  const d = state.dash;
  if (!d) return;
  const m = d.meters || {};
  const lines = d.meter_lines || {};
  $('play-me-body').innerHTML = `
    <p><strong>${esc(d.name)}</strong> · 等级 ${d.level || 1} · ${esc(d.title || '')}</p>
    ${d.motto ? `<p>「${esc(d.motto)}」</p>` : ''}
    <p>精力 ${m.energy || 0}/${m.energy_max || 100} · 工分票 ${d.tickets}</p>
    <p>饱食 ${m.satiety ?? '—'} · 雾智 ${m.mist_wit ?? '—'} · 档信 ${m.standing ?? '—'}</p>
    <p class="muted">${esc(lines.energy || '')}</p>
    <p class="muted">${esc(lines.bar_duty || '')}</p>
    ${d.voyage ? `<p class="muted">${esc(d.voyage)}</p>` : ''}
  `;
  show($('play-me'), true);
}

function closeMe() {
  show($('play-me'), false);
}

function memorySouvenirs(items) {
  if (!items || !items.length) return '';
  return `<section class="memory-reader-souvenirs">
    <h4>一同留下的纪念</h4>
    <div>${items.map((item) => `
      <span title="${esc(item.description || '')}">${esc(item.emoji || '◌')} ${esc(item.name)}</span>
    `).join('')}</div>
  </section>`;
}

function renderMemoryReader() {
  if (!activeMemory) return;
  const chapters = activeMemory.chapters || [];
  $('memory-reader-title').textContent = `《${activeMemory.title}》`;
  $('memory-reader-kicker').textContent = `${MEMORY_KIND_LABELS[activeMemory.kind] || '岛上'} · 回忆重映`;
  $('memory-reader-meta').textContent = [
    fmtMemoryDate(activeMemory.completed_at),
    activeMemory.ending ? `留下：${activeMemory.ending}` : '',
  ].filter(Boolean).join(' · ');
  $('memory-reader-notice').textContent = activeMemory.notice || '';
  $('memory-reader-toc').innerHTML = chapters.map((chapter, i) => `
    <button type="button" class="memory-toc-item${!continuousMemoryMode && i === activeMemoryChapter ? ' is-active' : ''}" data-memory-chapter="${i}">
      <span>${String(i + 1).padStart(2, '0')}</span>${esc(chapter.title)}
    </button>
  `).join('');
  const page = $('memory-reader-page');
  if (continuousMemoryMode) {
    page.innerHTML = chapters.map((chapter, i) => `
      <section class="memory-chapter" id="memory-chapter-${i}">
        <span class="memory-chapter-count">${i + 1} / ${chapters.length}</span>
        <h3>${esc(chapter.title)}</h3>
        <div class="memory-prose">${multiline(chapter.text)}</div>
      </section>
    `).join('') + memorySouvenirs(activeMemory.souvenirs);
  } else {
    const chapter = chapters[activeMemoryChapter] || { title: '回忆', text: '' };
    page.innerHTML = `
      <section class="memory-chapter">
        <span class="memory-chapter-count">${activeMemoryChapter + 1} / ${chapters.length}</span>
        <h3>${esc(chapter.title)}</h3>
        <div class="memory-prose">${multiline(chapter.text)}</div>
      </section>
      ${activeMemoryChapter === chapters.length - 1 ? memorySouvenirs(activeMemory.souvenirs) : ''}`;
  }
  $('memory-reader-progress').textContent = continuousMemoryMode
    ? `共 ${chapters.length} 幕`
    : `${activeMemoryChapter + 1} / ${chapters.length}`;
  $('memory-reader-prev').disabled = continuousMemoryMode || activeMemoryChapter <= 0;
  $('memory-reader-next').disabled = continuousMemoryMode || activeMemoryChapter >= chapters.length - 1;
  $('memory-reader-mode').textContent = continuousMemoryMode ? '按幕阅读' : '连续阅读';
}

async function openMemory(index, trigger) {
  const item = memoryCatalog[index];
  if (!item) return;
  const card = trigger.closest('[data-memory-card]');
  const select = card ? card.querySelector('[data-memory-variant-select]') : null;
  const variantIndex = select ? Number(select.value) : 0;
  const variant = (item.variants || [])[variantIndex];
  trigger.disabled = true;
  trigger.textContent = '取回中…';
  try {
    const data = await postJson('/api/steward/memory', {
      api_key: state.key,
      kind: item.kind,
      key: item.key,
      variant: variant ? String(variant.id) : '',
    });
    activeMemory = data;
    activeMemoryChapter = 0;
    continuousMemoryMode = false;
    renderMemoryReader();
    $('memory-modal').classList.remove('hidden');
    document.body.classList.add('memory-open');
  } catch (err) {
    setLog(err.message);
  } finally {
    trigger.disabled = false;
    trigger.textContent = '再次观看';
  }
}

function closeMemory() {
  $('memory-modal').classList.add('hidden');
  document.body.classList.remove('memory-open');
  activeMemory = null;
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
  if (!state.enrolled) {
    show($('play-main'), false);
    show($('play-gate'), true);
    return;
  }
  openMe();
});

$('play-me-close').addEventListener('click', closeMe);
$('play-me-bg').addEventListener('click', closeMe);
$('play-me-forget').addEventListener('click', () => {
  if (confirm('清除本机凭证？')) {
    clearSiteKey();
    state.key = '';
    location.href = '/play';
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

$('memory-filters').addEventListener('click', (e) => {
  const button = e.target.closest('[data-memory-filter]');
  if (!button) return;
  memoryFilter = button.dataset.memoryFilter;
  document.querySelectorAll('[data-memory-filter]').forEach((item) => {
    item.classList.toggle('is-active', item === button);
  });
  renderMemories();
});

$('memories').addEventListener('click', (e) => {
  const button = e.target.closest('[data-memory-watch]');
  if (!button) return;
  openMemory(Number(button.dataset.memoryWatch), button);
});

$('memory-reader-toc').addEventListener('click', (e) => {
  const item = e.target.closest('[data-memory-chapter]');
  if (!item || continuousMemoryMode) return;
  activeMemoryChapter = Number(item.dataset.memoryChapter);
  renderMemoryReader();
});

$('memory-reader-prev').addEventListener('click', () => {
  if (activeMemoryChapter > 0) {
    activeMemoryChapter -= 1;
    renderMemoryReader();
  }
});
$('memory-reader-next').addEventListener('click', () => {
  const chapters = (activeMemory && activeMemory.chapters) || [];
  if (activeMemoryChapter < chapters.length - 1) {
    activeMemoryChapter += 1;
    renderMemoryReader();
  }
});
$('memory-reader-mode').addEventListener('click', () => {
  continuousMemoryMode = !continuousMemoryMode;
  renderMemoryReader();
});
document.querySelectorAll('[data-memory-close]').forEach((btn) => {
  btn.addEventListener('click', closeMemory);
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
