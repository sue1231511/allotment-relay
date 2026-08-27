const state = {
  key: '',
  enrolled: false,
  dash: null,
  seeds: [],
  places: [],
  neighbors: { total: 0, listed: 0, online: 0, people: [] },
  climate: null,
  placeId: '',
  placeResult: '',
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

function duesOf(dash) {
  return (dash && dash.dues) || {};
}

function duesUrgent(dash) {
  const dues = duesOf(dash);
  return Number(dues.tax_arrears || 0) > 0 || Number(dues.upkeep_arrears || 0) > 0;
}

function duesLine(dash) {
  const dues = duesOf(dash);
  const bits = [];
  if (dues.tax_arrears) bits.push(`岸税欠 ${dues.tax_arrears}`);
  if (dues.upkeep_arrears) bits.push(`岸维欠 ${dues.upkeep_arrears}`);
  return bits.join(' · ');
}

async function api(tool, command) {
  const res = await fetch('/api/play', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      api_key: state.key,
      tool: tool || '',
      command: command || '',
      device_id: (typeof getOrCreateDeviceId === 'function' ? getOrCreateDeviceId() : ''),
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
  state.neighbors = data.neighbors || { total: 0, listed: 0, online: 0, people: [] };
  state.climate = data.climate || null;
  if (text) setLog(text);
  if (!state.enrolled) {
    document.body.classList.remove('play-bound');
    show($('play-main'), false);
    show($('play-gate'), true);
    show($('play-key-form'), false);
    show($('play-enroll-form'), true);
    $('play-who-name').textContent = '未登记';
    $('play-who-sub').textContent = '先起一个岛上的名字';
    $('play-avatar').textContent = '≈';
    return;
  }
  document.body.classList.add('play-bound');
  show($('play-gate'), false);
  show($('play-main'), true);
  renderAll();
}

function setLog(text) {
  const log = $('play-log');
  if (!text) {
    show(log, false);
    clearPlaceResult();
    return;
  }
  log.textContent = text;
  show(log, true);
  showPlaceResult(text);
}

function clearPlaceResult() {
  state.placeResult = '';
  const empty = $('play-place-empty');
  const result = $('play-place-result');
  if (empty) show(empty, true);
  if (result) {
    result.textContent = '';
    show(result, false);
  }
}

function showPlaceResult(text) {
  if (!state.placeId) return;
  state.placeResult = text || '';
  const empty = $('play-place-empty');
  const result = $('play-place-result');
  if (!text) {
    if (empty) show(empty, true);
    if (result) show(result, false);
    return;
  }
  if (empty) show(empty, false);
  if (result) {
    result.textContent = text;
    show(result, true);
  }
}

function stockPreview(limit = 3) {
  const stock = ((state.dash && state.dash.stock) || []).filter((it) => Number(it.qty) > 0);
  if (!stock.length) return '空';
  return stock.slice(0, limit).map((it) => `${it.name || it.label || it.item} ×${it.qty}`).join(' · ');
}

function placeContextRows(place) {
  const d = state.dash || {};
  const m = d.meters || {};
  const now = [];
  now.push(`<div class="place-context-row"><span>精力</span><b>${m.energy ?? '—'} / ${m.energy_max || 100}</b></div>`);
  now.push(`<div class="place-context-row"><span>工分票</span><b>${d.tickets ?? '—'}</b></div>`);
  now.push(`<div class="place-context-row"><span>行囊</span><b>${esc(stockPreview())}</b></div>`);

  const memo = [];
  if (place.id === 'quarry' && d.quarry && d.quarry.line) {
    memo.push(`<div class="place-context-row"><span>崖况</span><b>${esc(d.quarry.line)}</b></div>`);
  } else if (place.id === 'craft' && d.craft && d.craft.line) {
    memo.push(`<div class="place-context-row"><span>砧况</span><b>${esc(d.craft.line)}</b></div>`);
  } else if (place.id === 'atelier' && d.cloth && d.cloth.line) {
    memo.push(`<div class="place-context-row"><span>坊况</span><b>${esc(d.cloth.line)}</b></div>`);
    if (d.cloth.worn) memo.push(`<div class="place-context-row"><span>衣着</span><b>${esc(d.cloth.worn)} · ${esc(d.cloth.season || '')}</b></div>`);
  } else if (place.id === 'tide' && d.voyage) {
    memo.push(`<div class="place-context-row"><span>航程</span><b>${esc(d.voyage)}</b></div>`);
  } else if (d.meter_lines && d.meter_lines.bar_duty) {
    memo.push(`<div class="place-context-row"><span>考勤</span><b>${esc(d.meter_lines.bar_duty)}</b></div>`);
  }
  const c = state.climate || {};
  if (c.tide || c.weather) {
    memo.push(`<div class="place-context-row"><span>海况</span><b>${esc([c.tide, c.weather, c.phase].filter(Boolean).join(' · '))}</b></div>`);
  }
  if (place.id === 'hui') {
    const dues = d.dues || {};
    const bits = [];
    if (dues.tax_arrears) bits.push(`岸税欠 ${dues.tax_arrears}`);
    if (dues.upkeep_arrears) bits.push(`岸维欠 ${dues.upkeep_arrears}`);
    const dueLine = bits.length ? bits.join(' · ') : '无欠项 · 税看口袋，维看产业';
    memo.push(`<div class="place-context-row"><span>岛务</span><b>${esc(dueLine)}。捐票自填。补贴周二四六自动发。不能入会。</b></div>`);
  }
  if (place.id === 'clinic' && d.meter_lines && d.meter_lines.health) {
    memo.push(`<div class="place-context-row"><span>身子</span><b>${esc(d.meter_lines.health)}</b></div>`);
  }
  if (place.id === 'undertide' && (d.island_bond != null || (d.meters && d.meters.island_bond != null))) {
    const bond = d.island_bond ?? d.meters.island_bond;
    memo.push(`<div class="place-context-row"><span>岛缘</span><b>${esc(String(bond))} · 下去会蚀</b></div>`);
  }
  if (!memo.length) {
    memo.push(`<div class="place-context-row"><span>备忘</span><b>${esc(place.blurb || '先选一个动作')}</b></div>`);
  }
  return { now: now.join(''), memo: memo.join('') };
}

function selectPlaceTool(btn) {
  if (!btn) return;
  document.querySelectorAll('#play-place-actions .place-tool').forEach((el) => el.classList.remove('is-active'));
  btn.classList.add('is-active');
  const label = btn.getAttribute('data-label') || '动作';
  const note = btn.getAttribute('data-note') || '操作结果会留在这里。';
  if ($('play-work-title')) $('play-work-title').textContent = label;
  if ($('play-work-sub')) $('play-work-sub').textContent = note;
}

function renderPlace(id) {
  const place = (state.places || []).find((p) => p.id === id);
  if (!place) return;
  const switching = state.placeId !== id;
  state.placeId = id;
  show($('play-home'), false);
  show($('play-place'), true);
  $('play-place').classList.toggle('is-lounge', id === 'lounge');
  $('play-place-title').textContent = place.name;
  $('play-place-blurb').textContent = place.blurb + (place.caution ? ' 新手别从这儿开局。' : '');
  if ($('play-place-rail-title')) {
    $('play-place-rail-title').textContent = place.rail || `今天在${place.name}做什么`;
  }

  const c = state.climate || {};
  const m = (state.dash && state.dash.meters) || {};
  const chips = [
    c.tide,
    c.weather,
    c.phase,
    (m.energy != null) ? `精力 ${m.energy} / ${m.energy_max || 100}` : '',
  ].filter(Boolean);
  $('play-place-meta').innerHTML = chips.map((x) => `<span>${esc(x)}</span>`).join('');

  const live = $('play-place-live');
  if (place.href) {
    live.href = place.href;
    live.textContent = place.live || `打开${place.name}现场 →`;
    show(live, true);
  } else {
    show(live, false);
  }

  const acts = extraPlaceActions(place).concat(place.actions || []);
  $('play-place-actions').innerHTML = acts.map((a, i) => {
    const idx = String(i + 1).padStart(2, '0');
    const note = a.note || a.command || '';
    const primary = i === acts.length - 1 ? ' is-primary' : '';
    return `<button type="button" class="place-tool${primary}" data-label="${esc(a.label)}" data-note="${esc(note)}" data-act='${JSON.stringify({ tool: a.tool, command: a.command })}'>
      <span class="place-tool-index">${idx}</span>
      <span><strong>${esc(a.label)}</strong><small>${esc(note)}</small></span>
      <span class="arrow">→</span>
    </button>`;
  }).join('');

  const ctx = placeContextRows(place);
  if ($('play-place-now')) $('play-place-now').innerHTML = ctx.now;
  if ($('play-place-memo')) $('play-place-memo').innerHTML = ctx.memo;

  if (switching) {
    if ($('play-work-title')) $('play-work-title').textContent = '选一个动作';
    if ($('play-work-sub')) $('play-work-sub').textContent = '操作结果会直接留在这里。';
    setWorkStatus('可操作');
    clearPlaceResult();
  } else if (state.placeResult) {
    showPlaceResult(state.placeResult);
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
  show($('play-hui-donate'), id === 'hui');
  show($('play-cloth-sew'), id === 'atelier');
}

function plotStateLabel(stateName) {
  return ({
    ready: '可收',
    growing: '生长中',
    tending: '生长中',
    fallow: '休耕',
    overripe: '过熟',
    clearing: '开垦中',
  })[stateName] || stateName || '';
}

function todayBlurb(d, c) {
  const parcels = (d && d.parcels) || [];
  const ready = parcels.filter((p) => p.state === 'ready').length;
  const bits = [];
  if (c.tide || c.weather) bits.push(`${c.tide || ''}${c.weather ? ' · ' + c.weather : ''}`.replace(/^ · /, ''));
  if (ready) bits.push(`有 ${ready} 块已经成熟`);
  const duty = (d && d.meter_lines && d.meter_lines.bar_duty) || '';
  if (dutyUrgent(d)) bits.push('酒吧值班快到期了');
  else if (duty && duty.includes('内须')) bits.push(duty.replace(/^⚠\s*/, ''));
  const health = d && d.meter_lines && d.meter_lines.health;
  if (health && health.includes('（')) bits.push(health.replace(/^⚠\s*/, ''));
  const dues = duesLine(d);
  if (dues) bits.push(dues);
  if (d && d.voyage) bits.push(d.voyage);
  if (bits.length) return bits.join('。') + '。';
  return d && d.motto ? d.motto : '先看份地，或去岛上晃一圈。';
}

function renderAll() {
  const d = state.dash;
  const c = state.climate || {};
  const name = (d && d.name) || '已绑定';
  const level = (d && d.level) || 1;
  const title = (d && d.title) || '';
  $('play-climate-mini').textContent = [c.season, c.phase].filter(Boolean).join(' · ') || '潮汐岛';
  $('play-who-name').textContent = name;
  $('play-who-sub').textContent = `管理员 · ${title || ('LV ' + level)}`;
  $('play-avatar').textContent = String(name).slice(0, 1) || '≈';
  $('play-today-title').textContent = (d && d.climate) || c.line || `${c.tide || '潮汐'} · ${c.phase || ''}`.trim();
  $('play-motto').textContent = todayBlurb(d, c);
  const energy = (d.meters && d.meters.energy) || 0;
  const emax = (d.meters && d.meters.energy_max) || 100;
  $('play-meter-climate').textContent = [c.tide, c.weather].filter(Boolean).join(' · ') || '—';
  $('play-energy').textContent = `${energy} / ${emax}`;
  $('play-tickets').textContent = String(d.tickets ?? '—');
  $('play-level').textContent = `LV ${level}${title ? ' · ' + title : ''}`;
  const bondEl = $('play-bond');
  if (bondEl) {
    const bond = d.island_bond ?? (d.meters && d.meters.island_bond);
    const flavor = d.bond_flavor || '';
    bondEl.textContent = bond == null ? '—' : `${bond}${flavor ? ' · ' + flavor : ''}`;
  }
  const duty = (d.meter_lines && d.meter_lines.bar_duty) || '';
  const dutyEl = $('play-duty');
  const dutyBits = [];
  if (duty && (dutyUrgent(d) || duty.includes('内须'))) dutyBits.push(duty.replace(/^⚠\s*/, ''));
  const dues = duesLine(d);
  if (dues) dutyBits.push(`${dues}。去潮生会交。`);
  dutyEl.textContent = dutyBits.join(' · ');
  show(dutyEl, dutyBits.length > 0);
  renderPlots();
  renderPlaces();
  renderNeighbors();
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
    acts.push(`<button type="button" class="play-mini-btn" data-sow="${esc(token)}">播种</button>`);
  }
  if (p.state === 'growing' || p.state === 'tending') {
    if (!p.tended) acts.push(`<button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"tend"}'>打理</button>`);
    if (!p.watered) acts.push(`<button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"浇水 ${token}"}'>浇水</button>`);
    if (!p.fertilized) acts.push(`<button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"施肥 ${token}"}'>施肥</button>`);
  }
  if (p.state === 'ready') {
    const harvest = (p.orchard || p.shake) ? '收果' : '收菜';
    acts.push(`<button type="button" class="play-mini-btn primary" data-act='{"tool":"plot_ops","command":"gather ${token}"}'>${harvest}</button>`);
    if (p.shake) acts.push(`<button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"shake ${token}"}'>摇一摇</button>`);
  }
  if (p.state === 'overripe') {
    acts.push(`<button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"compost ${token}"}'>堆肥</button>`);
    acts.push(`<button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"gather ${token}"}'>清果</button>`);
  }
  return acts.join('');
}

function plotCardHtml(p) {
  const token = p.token || String(p.slot);
  const slotLabel = p.greenhouse || p.orchard ? token : `份地 ${token}`;
  return `
    <article class="play-plot ${p.state === 'ready' ? 'is-ready' : ''} ${p.orchard ? 'is-orchard' : ''} ${p.greenhouse ? 'is-shed' : ''}">
      <div class="play-plot-top">
        <span class="play-plot-slot">${esc(slotLabel)}</span>
        <span class="play-state">${esc(plotStateLabel(p.state))}</span>
      </div>
      <div class="play-crop">${p.emoji ? esc(p.emoji) + ' ' : ''}${esc(p.name)}</div>
      <div class="play-detail">${esc(p.detail || '')}</div>
      <div class="acts">${plotButtons(p)}</div>
    </article>`;
}

function landExpandHtml(snap) {
  if (!snap) return '';
  if (snap.clearing) {
    return `<div class="play-land-expand is-busy">
      <span>${esc(snap.clearing_label || '')} 开垦中 · ${esc(snap.clearing_eta || '')}</span>
    </div>`;
  }
  const offer = snap.offer;
  if (!offer) return '';
  const confirm = JSON.stringify({ tool: 'plot_ops', command: snap.confirm_cmd });
  const quote = JSON.stringify({ tool: 'plot_ops', command: snap.quote_cmd });
  if (duesUrgent(state.dash)) {
    return `<div class="play-land-expand is-busy">
      <span>欠岸税或岸维，交清才能开垦</span>
      <button type="button" class="play-mini-btn" data-act='${quote}'>看价</button>
      <button type="button" class="play-mini-btn primary" data-place="hui">去潮生会</button>
    </div>`;
  }
  return `<div class="play-land-expand">
    <span>${esc(snap.next_word || '下一块')} ${esc(offer.token)} · ${offer.cost} 票 · 开垦 ${esc(offer.clear_eta)}</span>
    <button type="button" class="play-mini-btn" data-act='${quote}'>看价</button>
    <button type="button" class="play-mini-btn primary" data-act='${confirm}'>确认开垦</button>
  </div>`;
}

function plotGroupHtml(title, blurb, list, expandSnap, emptyText) {
  const cards = list.length
    ? `<div class="play-plots">${list.map(plotCardHtml).join('')}</div>`
    : `<p class="muted play-plot-empty">${esc(emptyText || '还没有地。')}</p>`;
  return `<div class="play-plot-group">
    <div class="play-plot-group-head">
      <strong>${esc(title)}</strong>
      <span>${esc(blurb)}</span>
    </div>
    ${cards}
    ${landExpandHtml(expandSnap)}
  </div>`;
}

function renderPlots() {
  const parcels = (state.dash && state.dash.parcels) || [];
  const land = (state.dash && state.dash.land) || {};
  const plots = parcels.filter((p) => !p.orchard && !p.greenhouse);
  const trees = parcels.filter((p) => p.orchard && !p.greenhouse);
  const sheds = parcels.filter((p) => p.greenhouse);
  const plotCount = (land.plots && land.plots.count) || plots.length;
  const treeCount = (land.orchard && land.orchard.count) || trees.length;
  const shedCount = (land.greenhouse && land.greenhouse.count) || sheds.length;
  const parts = [
    plotGroupHtml(`菜地 ${plotCount}`, '露天种菜', plots, land.plots),
    plotGroupHtml(`果园 ${treeCount}`, '只种果树', trees, land.orchard),
    plotGroupHtml(
      shedCount ? `温室 ${shedCount}` : '温室',
      shedCount ? '种菜种树都不受季节' : '买棚后四季可种',
      sheds,
      land.greenhouse,
      '还没有温室。',
    ),
  ];
  $('play-plots').innerHTML = parts.join('') || '<p class="muted">还没有地。</p>';
  const sub = $('play-plots-sub');
  if (sub) {
    sub.textContent = `菜地 ${plotCount} · 果园 ${treeCount}${shedCount ? ` · 温室 ${shedCount}` : ''} · 全部展示`;
  }
}

function placeCardHtml(pl, urgent) {
  const huiUrgent = pl.id === 'hui' && duesUrgent(state.dash);
  const hot = (pl.duty && urgent) || huiUrgent;
  return `
    <article class="play-place-card ${hot ? 'is-duty' : ''}">
      <small>${esc(pl.kicker || (pl.week1 ? 'Often' : 'Later'))}</small>
      <strong>${esc(pl.name)}</strong>
      <p>${esc(pl.blurb)}</p>
      <button type="button" class="play-mini-btn ${hot ? 'primary' : ''} go" data-place="${esc(pl.id)}">前往</button>
    </article>`;
}

function orderedPlaces(places) {
  return (places || []).slice().sort((a, b) => Number(Boolean(b.week1)) - Number(Boolean(a.week1)));
}

function renderPlaces() {
  const urgent = dutyUrgent(state.dash);
  const home = (state.places || []).filter((pl) => pl.week1);
  $('play-places').innerHTML = home.map((pl) => placeCardHtml(pl, urgent)).join('');
}

function openAllPlaces() {
  const urgent = dutyUrgent(state.dash);
  openSheet('岛上全部地点', `<div class="play-places">${orderedPlaces(state.places).map((pl) => placeCardHtml(pl, urgent)).join('')}</div>`);
}

function renderNeighbors() {
  const n = state.neighbors || {};
  const people = n.people || [];
  const total = n.total || 0;
  const online = n.online || 0;
  $('play-neighbors-count').textContent = online
    ? `${total} · 档口 ${online}`
    : `${total}`;
  if (!people.length) {
    $('play-neighbors-list').innerHTML = total <= 1
      ? '<p class="muted">岛上暂时就你一位。</p>'
      : '<p class="muted">名册是空的。</p>';
    return;
  }
  $('play-neighbors-list').innerHTML = people.map((p) => {
    const ripe = p.ripe ? `熟地 ${p.ripe}` : '暂无熟地';
    const where = p.home ? '在档口' : (p.ago || '');
    return `<button type="button" class="play-neighbor" data-neighbor="${esc(p.name)}">
      <span class="play-neighbor-dot ${p.home ? '' : 'is-away'}" aria-hidden="true"></span>
      <span><strong>${esc(p.name)}</strong><small>${esc(where)} · ${esc(ripe)}</small></span>
    </button>`;
  }).join('');
}

function neighborSheet(person) {
  const name = person.name;
  const stock = ((state.dash && state.dash.stock) || [])
    .filter((it) => Number(it.qty) > 0)
    .slice(0, 8);
  const giftBtns = stock.map((it) => {
    const cmd = JSON.stringify({ tool: 'tote_ops', command: `gift ${name} ${it.name} 1` });
    return `<button type="button" class="play-mini-btn" data-act='${cmd}'>送 ${esc(it.name)}</button>`;
  }).join('');
  const ticketBtn = `<button type="button" class="play-mini-btn" data-act='${JSON.stringify({ tool: 'tote_ops', command: `gift ${name} 票 5` })}'>送 5 票</button>`;
  const ripe = person.ripe ? `熟地 ${person.ripe}` : '暂无熟地';
  const where = person.home ? '在档口' : (person.ago || '不在');
  openSheet(name, `
    <p class="muted">${esc(where)} · ${esc(ripe)}</p>
    <div class="play-mini-actions" style="margin-top:10px;flex-wrap:wrap">
      <button type="button" class="play-mini-btn" data-act='${JSON.stringify({ tool: 'steward_ops', command: `peer ${name}` })}'>看档</button>
      <button type="button" class="play-mini-btn" data-act='${JSON.stringify({ tool: 'alliance_ops', command: `assist ${name}` })}'>帮忙打理</button>
      <button type="button" class="play-mini-btn" data-act='${JSON.stringify({ tool: 'plot_ops', command: `偷菜 ${name}` })}'>偷菜</button>
      <button type="button" class="play-mini-btn" data-act='${JSON.stringify({ tool: 'plot_ops', command: `amends ${name}` })}'>致歉</button>
    </div>
    ${giftBtns
      ? `<div style="margin-top:12px"><p class="muted">送礼即时到账，对方在右侧「收礼 / 打赏」可见。</p>
         <div class="play-mini-actions" style="margin-top:8px;flex-wrap:wrap">${giftBtns}${ticketBtn}</div></div>`
      : `<p class="muted" style="margin-top:12px">口袋空了，没法送礼。送票仍可点：${ticketBtn}</p>`}
  `);
}

function renderTide() {
  const c = state.climate || {};
  const voyage = (state.dash && state.dash.voyage) || '';
  $('play-tide-box').innerHTML = `
    <div class="play-tide-line">${esc(c.tide || '—')} · ${esc(c.phase || '')}</div>
    <p>${esc(c.season || '')} · ${esc(c.weather || '')}</p>
    ${voyage ? `<p style="margin-top:7px">${esc(voyage)}</p>` : ''}
  `;
}

function renderTote() {
  const stock = ((state.dash && state.dash.stock) || []).filter((it) => Number(it.qty) > 0);
  const countEl = $('play-tote-count');
  if (countEl) countEl.textContent = stock.length ? `${stock.length} 种` : '—';
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
  const head = `<div style="margin-bottom:8px"><button type="button" class="play-text-btn" data-act='{"tool":"tote_ops","command":"gifts"}'>刷新收礼记录</button></div>`;
  if (!gifts.length) {
    $('play-gifts').innerHTML = `${head}<p>暂无收礼 / 打赏</p><p class="muted">别人送你礼或酒吧打赏会列在这里；也可 tote_ops gifts 或 steward_ops 收礼。</p>`;
    return;
  }
  $('play-gifts').innerHTML = head + gifts.slice(0, 6).map((g) => `
    <div class="item">
      <strong>${esc(g.who)}</strong><span class="muted"> · ${esc(g.kind)}</span>
      <p style="margin-top:4px">${esc(g.text)}</p>
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
  return islandFmtDate(epoch);
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
  if (place.id === 'hui') {
    const dues = duesOf(state.dash);
    if (Number(dues.tax_arrears || 0) > 0) {
      extra.push({ label: '交岸税', note: `欠 ${dues.tax_arrears}`, tool: 'visit_ops', command: '潮生会 税 交' });
    }
    if (Number(dues.upkeep_arrears || 0) > 0) {
      extra.push({ label: '交岸维', note: `欠 ${dues.upkeep_arrears}`, tool: 'visit_ops', command: '潮生会 维 交' });
    }
  }
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

function goHome() {
  state.placeId = '';
  state.placeResult = '';
  show($('play-place'), false);
  $('play-place').classList.remove('is-lounge');
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
  if (go === 'me') openStewardPage();
  else if (go === 'neighbors') {
    const el = $('play-neighbors');
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }
  else renderPlace(go);
}

async function openStewardPage() {
  if (!state.enrolled || !state.key) {
    show($('play-gate'), true);
    return;
  }
  state.placeId = '';
  show($('play-place'), false);
  show($('play-home'), false);
  show($('play-steward-page'), true);
  document.querySelectorAll('.play-dock button').forEach((b) => b.classList.remove('is-active'));
  $('play-dock-steward')?.classList.add('is-active');
  if (window.playLounge) window.playLounge.stop();
  const err = $('play-steward-error');
  if (err) show(err, false);
  try {
    const res = await fetch('/api/steward/dashboard', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: state.key }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || '管家档案暂时打不开');
    renderStewardPage(data);
  } catch (ex) {
    if (err) {
      err.textContent = ex.message || String(ex);
      show(err, true);
    }
  }
  $('play-steward-page')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function stewardMeter(label, value, max = 100, tone = 'sea') {
  const v = Math.max(0, Math.min(Number(max) || 100, Number(value) || 0));
  const pct = Math.round((v / (Number(max) || 100)) * 100);
  return `<div class="play-steward-meter"><div><span>${esc(label)}</span><strong>${v}</strong></div><i><b class="tone-${tone}" style="width:${pct}%"></b></i></div>`;
}

function renderStewardPage(data) {
  const st = data.status || {};
  const shadow = data.shadow || {};
  const flags = [];
  if (data.flags?.greenhouse) flags.push('温室');
  if (data.flags?.hut_built) flags.push('小屋');
  if (data.flags?.barn_built) flags.push('畜栏');
  if (data.flags?.eatery_open) flags.push('小馆');
  if (data.flags?.boat) flags.push('有船');
  const pulse = data.pulse ? `脉冲 · ${data.pulse.label}${data.pulse.remaining ? ` · ${Math.floor(data.pulse.remaining / 60)}分` : ''}` : '';
  const badges = [
    `影信 · ${shadow.rep ?? '—'}`,
    pulse,
    data.climate || '',
    ...flags,
    ...(st.flags || []),
  ].filter(Boolean);
  const badgeLabelMap = { naturalist: '博物家', mariner: '航海家', cook: '厨子', host: '掌柜', scout: '斥候', poet: '诗人' };
  $('play-steward-hero').innerHTML = `
    <div class="play-steward-id">
      <span class="play-steward-avatar">${esc(String(data.name || '≈').slice(0, 1))}</span>
      <span><strong>${esc(data.name || '未命名')}</strong><small>Lv ${data.level || 1} · ${esc(data.title || '')}${data.badge ? ` · ${esc(badgeLabelMap[data.badge] || data.badge)}` : ''}</small></span>
      <em>${esc(st.label || (st.online ? '在线' : '离线'))}</em>
    </div>
    ${data.motto ? `<p class="play-steward-motto">「${esc(data.motto)}」</p>` : ''}
    <div class="play-steward-chips">${badges.map((x) => `<span>${esc(x)}</span>`).join('')}</div>`;

  $('play-steward-stat-band').innerHTML = `
    <div class="play-steward-stat major"><small>工分票</small><strong>${data.tickets ?? '—'}</strong></div>
    <div class="play-steward-stat"><small>行囊</small><strong>${data.stock_count ?? (data.stock || []).length} 种</strong></div>
    <div class="play-steward-stat"><small>集市</small><strong>${data.market?.used ?? 0} / ${data.market?.cap ?? 0}</strong></div>`;

  const m = data.meters || {};
  $('play-steward-meters').innerHTML = [
    stewardMeter('影信', m.shadow_rep ?? shadow.rep, 100, 'ink'),
    stewardMeter('饱食', m.satiety, 100, 'sand'),
    stewardMeter('雾智', m.mist_wit, 100, 'sea'),
    stewardMeter('档信', m.standing, 100, 'green'),
    stewardMeter('健康', m.health, 100, 'rose'),
    stewardMeter('精力', m.energy, m.energy_max || 100, 'ink'),
  ].join('');
  $('play-steward-note').textContent = [
    data.meter_lines?.energy,
    data.meter_lines?.bar_duty,
    data.voyage ? `⛵ ${data.voyage}` : '',
    data.quarry?.line ? `⚒️ ${data.quarry.line}` : '',
    data.craft?.line ? `🔨 ${data.craft.line}` : '',
  ].filter(Boolean).join(' · ');

  const incidents = data.incidents || [];
  $('play-steward-ops').innerHTML = `
    <section class="play-steward-ops-card market"><small>OPS · 集市</small><strong>${data.market?.used ?? 0} / ${data.market?.cap ?? 0} 摊格</strong><p>当前摊格使用情况。</p></section>
    <section class="play-steward-ops-card incidents"><small>OPS · 意外</small><strong>${incidents.length} 件待处理</strong><div>${incidents.length ? incidents.map((i) => `<span>#${i.id} ${esc(i.label)} <b>${i.repair_tickets}票</b></span>`).join('') : '<p>无未处理意外</p>'}</div></section>`;

  const parcels = data.parcels || [];
  $('play-steward-plots').innerHTML = parcels.length ? parcels.map((p) => `<article><small>${p.greenhouse ? '棚' : (p.orchard ? '园' : '#')}${p.slot} · ${esc(p.state || '')}</small><strong>${esc(p.emoji || '🌱')} ${esc(p.name || p.label || '')}</strong><p>${esc(p.detail || '')}</p></article>`).join('') : '<p class="muted">暂无份地</p>';

  const stock = data.stock || [];
  $('play-steward-stock-count').textContent = `TOTE · ${data.stock_count ?? stock.length} 种`;
  $('play-steward-stock').innerHTML = stock.length ? stock.map((it) => `<span><b>${esc(it.name || it.item || '')}</b><em>×${it.qty}</em></span>`).join('') : '<p class="muted">行囊空</p>';

  const gifts = data.gifts || [];
  $('play-steward-gifts').innerHTML = gifts.length ? gifts.slice(0, 6).map((g) => `<article><time>${esc(islandFmtStamp(g.created_at))}</time><div><strong>${esc(g.who || '')} · ${esc(g.kind || '')}</strong><p>${esc(g.text || '')}</p></div></article>`).join('') : '<p class="muted">暂无收礼 / 打赏</p>';

  const memories = data.memories || [];
  const latest = memories[0];
  $('play-steward-memory').innerHTML = latest ? `<small>MEMORIES · 最近完成</small><h3>${esc(latest.title || '')}</h3><p>${esc([MEMORY_KIND_LABELS[latest.kind] || latest.kind, latest.chapter_count ? `${latest.chapter_count} 幕` : '', latest.ending || ''].filter(Boolean).join(' · '))}</p><button type="button" class="play-steward-memory-go">去回忆页查看</button>` : '<small>MEMORIES</small><h3>还没有岛上回忆</h3>';
  $('.play-steward-memory-go')?.addEventListener?.('click', () => {});
  const goMemory = document.querySelector('.play-steward-memory-go');
  if (goMemory) goMemory.addEventListener('click', () => {
    show($('play-steward-page'), false);
    show($('play-home'), true);
    document.querySelectorAll('.play-dock button').forEach((b) => b.classList.remove('is-active'));
    document.querySelector('[data-scroll="memoriesSection"]')?.classList.add('is-active');
    $('memoriesSection')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
}

function openMe() {
  const d = state.dash;
  if (!d) return;
  const m = d.meters || {};
  const lines = d.meter_lines || {};
  const name = d.name || '';
  const inv = d.invite || {};
  const guests = (inv.invited || []).slice(0, 8).map((g) =>
    `<li>${esc(g.name)} · ${esc(g.status)}</li>`
  ).join('');
  const keeps = (inv.keepsakes || []).map((k) =>
    `${esc(k.emoji || '')}${esc(k.name)}`
  ).join(' · ');
  $('play-me-body').innerHTML = `
    <div class="play-identity" style="margin-bottom:14px;width:100%;cursor:default">
      <span class="play-avatar">${esc(String(name).slice(0, 1) || '≈')}</span>
      <span><strong>${esc(name)}</strong><small>管理员 · ${esc(d.title || ('LV ' + (d.level || 1)))}</small></span>
    </div>
    <p>精力 ${m.energy || 0}/${m.energy_max || 100} · 工分票 ${d.tickets}</p>
    <p style="margin-top:6px">岛缘 ${d.island_bond ?? m.island_bond ?? 0} ∞${d.bond_flavor ? ' · ' + esc(d.bond_flavor) : ''}</p>
    <p style="margin-top:6px">饱食 ${m.satiety ?? '—'} · 雾智 ${m.mist_wit ?? '—'} · 档信 ${m.standing ?? '—'}</p>
    ${d.motto ? `<p style="margin-top:8px">「${esc(d.motto)}」</p>` : ''}
    ${lines.health && lines.health.includes('（') ? `<p class="muted" style="margin-top:8px">${esc(lines.health)}</p>` : ''}
    <div class="play-rule">${esc(lines.bar_duty || '每 2 天须去酒吧上工。')}</div>
    ${duesLine(d) ? `<div class="play-rule">${esc(duesLine(d))}。去潮生会交。</div>` : ''}
    ${d.voyage ? `<p class="muted" style="margin-top:8px">${esc(d.voyage)}</p>` : ''}
    <section class="play-invite">
      <div class="play-kicker">Pilot</div>
      <h3>引航</h3>
      <p>邀请码 <strong id="play-invite-code">${esc(inv.code || '—')}</strong>
        <button type="button" class="btn secret-copy" id="play-invite-copy">复制链接</button>
      </p>
      ${inv.inviter ? `<p class="muted">由「${esc(inv.inviter.name)}」引来 · ${esc(inv.my_status || '')}</p>` : ''}
      ${inv.can_bind ? `
        <form id="play-invite-bind">
          <label>绑定邀请码（只能一次）
            <input id="play-invite-bind-code" type="text" maxlength="16" placeholder="邀请码" autocomplete="off">
          </label>
          <button type="submit" class="btn">绑定</button>
        </form>
        <p class="error hidden" id="play-invite-bind-err"></p>
      ` : ''}
      <p class="muted">已引来 ${Number(inv.invited && inv.invited.length) || 0} 人，计入有效 ${Number(inv.valid_count) || 0} 人。</p>
      <p class="muted">对方成为有效岛民后，你会收到 ${Number(inv.official_reward_tickets) || 100} 工分票和 ${Number(inv.official_reward_bond) || 20} 岛缘。</p>
      ${guests ? `<ul class="play-invite-list">${guests}</ul>` : ''}
      ${keeps ? `<p class="muted">收藏 ${keeps}</p>` : ''}
      ${inv.lantern ? `<p class="muted">岸灯已在小屋亮着。</p>` : ''}
    </section>
  `;
  const copyBtn = $('play-invite-copy');
  if (copyBtn) {
    copyBtn.addEventListener('click', () => {
      const url = inv.link && inv.link.startsWith('http')
        ? inv.link
        : `${location.origin}${inv.link || '/register'}`;
      if (typeof copyText === 'function') copyText(url, copyBtn);
      else navigator.clipboard.writeText(url);
    });
  }
  const bindForm = $('play-invite-bind');
  if (bindForm) {
    bindForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      const err = $('play-invite-bind-err');
      err.classList.add('hidden');
      try {
        const res = await fetch('/api/invite/bind', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            api_key: state.key,
            code: $('play-invite-bind-code').value.trim(),
            device_id: typeof getOrCreateDeviceId === 'function' ? getOrCreateDeviceId() : '',
          }),
        });
        const data = await res.json();
        if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : '绑不上');
        if (data.invite) state.dash = { ...state.dash, invite: data.invite };
        openMe();
        setLog(data.text || '引航关系已结。');
      } catch (ex) {
        err.classList.remove('hidden');
        err.textContent = ex.message;
      }
    });
  }
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
  const sowBtns = seeds.map((s) => (
    `<button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"sow ${token} ${s.name}"}'>${s.emoji || ''} ${s.name} ×${s.qty}</button>`
  )).join('');
  if (!seeds.length) {
    openSheet(`种到 ${token}`, `<p class="muted">口袋里没有能种在这儿的种。买当季或全年的，过季会拒。</p>${seedBuyHtml()}`);
    return;
  }
  openSheet(`种到 ${token}`, `${sowBtns}<p class="muted" style="margin-top:10px">没有想要的就买一份。</p>${seedBuyHtml()}`);
}

function seedBuyHtml() {
  return `
    <button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"catalog"}'>看当季</button>
    <button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"buy 1 甘蓝"}'>买甘蓝种</button>
    <button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"buy 1 甜菜"}'>买甜菜种</button>
    <button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"buy 1 雾豌豆"}'>买雾豆种</button>
    <button type="button" class="play-mini-btn" data-act='{"tool":"plot_ops","command":"buy 1 浅海藻"}'>买浅海藻种</button>
  `;
}

function buySeedSheet() {
  openSheet('买种', `<p class="muted">买当季或全年种。甘蓝 / 甜菜 / 雾豆 / 浅海藻全年可种。过季会拒。</p>${seedBuyHtml()}`);
}

function itemSheet(name) {
  openSheet(name, `
    <button type="button" class="play-mini-btn primary" data-act='{"tool":"kitchen_ops","command":"eat ${name}"}'>吃</button>
    <button type="button" class="play-mini-btn" data-act='{"tool":"tote_ops","command":"vend ${name} 1"}'>卖 1</button>
  `);
}

function setWorkStatus(text) {
  const pill = $('play-work-status');
  if (!pill) return;
  pill.textContent = text || '可操作';
}

function parseActPayload(raw) {
  if (!raw) return null;
  try {
    const payload = JSON.parse(raw);
    if (!payload || typeof payload.tool !== 'string' || typeof payload.command !== 'string') {
      return null;
    }
    return payload;
  } catch {
    return null;
  }
}

async function act(tool, command) {
  try {
    setWorkStatus('处理中…');
    document.querySelectorAll('.play-page button.btn, .play-page .play-mini-btn, .play-page .place-tool, .play-go').forEach((b) => { b.disabled = true; });
    const data = await api(tool, command);
    applySnap(data, data.text || '');
    setWorkStatus('完成');
    closeSheet();
    const workarea = $('play-place-workspace');
    if (workarea && state.placeId) {
      workarea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
  } catch (err) {
    const msg = err.message || String(err);
    setLog(msg);
    setWorkStatus('未做成');
    const workarea = $('play-place-workspace');
    if (workarea && state.placeId) {
      workarea.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    }
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
  const invite = ($('play-enroll-invite') && $('play-enroll-invite').value.trim())
    || (typeof peekInviteCode === 'function' ? peekInviteCode() : '');
  const err = $('play-gate-err');
  err.classList.add('hidden');
  try {
    const data = await api('steward_ops', `enroll ${name}`);
    applySnap(data, data.text || '');
    if (invite && data.enrolled && data.dashboard && data.dashboard.invite && data.dashboard.invite.can_bind) {
      const res = await fetch('/api/invite/bind', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          api_key: state.key,
          code: invite,
          device_id: typeof getOrCreateDeviceId === 'function' ? getOrCreateDeviceId() : '',
        }),
      });
      const bound = await res.json();
      if (res.ok && bound.invite) {
        state.dash = { ...state.dash, invite: bound.invite };
        setLog(`${data.text || ''}\n${bound.text || ''}`.trim());
        if (typeof clearStoredInvite === 'function') clearStoredInvite();
      }
    }
  } catch (ex) {
    err.classList.remove('hidden');
    err.textContent = ex.message;
  }
});

$('play-who-btn').addEventListener('click', () => {
  if (!state.enrolled) {
    document.body.classList.remove('play-bound');
    show($('play-main'), false);
    show($('play-gate'), true);
    return;
  }
  openMe();
});

$('play-dock-steward')?.addEventListener('click', () => {
  openStewardPage();
});

$('play-steward-refresh')?.addEventListener('click', () => {
  openStewardPage();
});

$('play-all-places')?.addEventListener('click', openAllPlaces);

document.querySelectorAll('[data-scroll]').forEach((btn) => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.play-dock button').forEach((b) => b.classList.remove('is-active'));
    btn.classList.add('is-active');
    show($('play-steward-page'), false);
    show($('play-home'), true);
    if (state.placeId) goHome();
    const el = $(btn.dataset.scroll);
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
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

$('play-star-script')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const pitch = $('play-star-script-pitch').value.trim();
  const title = $('play-star-script-title').value.trim().replaceAll('|', '·');
  const body = $('play-star-script-body').value.trim();
  if (!title || !body) {
    showResult('play-star-script-result', '<p class="error">标题和正文都要写。</p>');
    return;
  }
  const head = pitch ? `投稿 ${pitch} ${title}` : `投稿 ${title}`;
  try {
    const data = await api('theater_ops', `${head} | ${body}`);
    applySnap(data, data.text || '');
    showResult('play-star-script-result', `<p>${esc(data.text || '').replaceAll('\n', '<br>')}</p>`);
    $('play-star-script-title').value = '';
    $('play-star-script-body').value = '';
  } catch (err) {
    showResult('play-star-script-result', `<p class="error">${esc(err.message)}</p>`);
  }
});

$('play-hui-donate')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const amount = parseInt($('play-hui-donate-amount').value, 10);
  if (!Number.isFinite(amount) || amount < 1) {
    setLog('票数自己填，至少 1。');
    return;
  }
  await act('visit_ops', `潮生会 基金 捐 ${amount}`);
});

$('play-cloth-sew')?.addEventListener('submit', async (e) => {
  e.preventDefault();
  const cut = $('play-cloth-cut')?.value || '短褂';
  const color = $('play-cloth-color')?.value || '海色';
  const motif = $('play-cloth-motif')?.value || '素';
  await act('cloth_ops', `委托 ${cut} ${color} ${motif}`);
});

$('play-cloth-wear-btn')?.addEventListener('click', async () => {
  const gid = parseInt($('play-cloth-wear')?.value, 10);
  if (!Number.isFinite(gid) || gid < 1) {
    setLog('先看衣橱编号，再填要穿的那件。');
    return;
  }
  await act('cloth_ops', `穿 ${gid}`);
});

$('play-cloth-off-btn')?.addEventListener('click', async () => {
  await act('cloth_ops', '脱');
});

document.body.addEventListener('click', (e) => {
  const sow = e.target.closest('[data-sow]');
  if (sow) {
    sowSheet(sow.getAttribute('data-sow'));
    return;
  }
  if (e.target.closest('[data-buy-seed]')) {
    buySeedSheet();
    return;
  }
  const place = e.target.closest('[data-place]');
  if (place) {
    closeSheet();
    renderPlace(place.getAttribute('data-place'));
    return;
  }
  const item = e.target.closest('#play-tote [data-item]');
  if (item) {
    itemSheet(item.getAttribute('data-item'));
    return;
  }
  const neighborBtn = e.target.closest('[data-neighbor]');
  if (neighborBtn) {
    const name = neighborBtn.getAttribute('data-neighbor');
    const people = (state.neighbors && state.neighbors.people) || [];
    const person = people.find((p) => p.name === name);
    if (person) neighborSheet(person);
    return;
  }
  const btn = e.target.closest('[data-act]');
  if (!btn) return;
  const payload = parseActPayload(btn.getAttribute('data-act'));
  if (!payload) {
    setLog('动作按钮坏了，刷新页面再试。');
    setWorkStatus('未做成');
    return;
  }
  if (btn.classList.contains('place-tool')) selectPlaceTool(btn);
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
  const enrollInvite = $('play-enroll-invite');
  if (enrollInvite && typeof peekInviteCode === 'function') {
    enrollInvite.value = peekInviteCode();
  }
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
