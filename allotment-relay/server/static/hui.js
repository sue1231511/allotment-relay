function esc(s) {
  return String(s ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function clock(epoch) {
  return islandFmtClock(epoch);
}

async function loadHui() {
  const data = await fetch('/api/public/hui').then((r) => r.json());
  const fund = data.fund || {};

  document.getElementById('hui-meta').innerHTML = [
    `<span>值事 ${esc(data.clerk || '阿簿')}</span>`,
    `<span>告示 ${esc((data.beacons || []).length)} 条</span>`,
    `<span>基金 ${esc(fund.pool ?? 0)} 票</span>`,
    `<span>岸税本周 ${esc((data.tax || {}).collected ?? 0)}</span>`,
    `<span>岸维今日 ${esc((data.upkeep || {}).collected ?? 0)}</span>`,
  ].join('');

  document.getElementById('hui-strip').innerHTML =
    `<span class="dot"></span><span>${esc(data.clerk || '阿簿')}：「${esc(data.line || '坐。先报名字。')}」</span>`;

  const fundEl = document.getElementById('hui-fund');
  if (fundEl) {
    const ready = Boolean(fund.ready);
    fundEl.innerHTML = `
      <div class="hui-card">
        <small>池里</small>
        <strong>${esc(fund.pool ?? 0)} 票</strong>
        <p>${ready
          ? `岛均口袋 ${esc(fund.avg ?? 0)} 票 · 在册 ${esc(fund.n ?? 0)} 人。有余的人自己填数捐。补贴不用领，${esc(fund.weekdays || '周二四六')}自动发，每人顶 2500、不超过岛均。`
          : '在册还不够两人，算不出岛均。'}</p>
        <small>${esc(fund.next_pay || '')}</small>
      </div>
    `;
  }

  const tax = data.tax || {};
  const taxEl = document.getElementById('hui-tax');
  if (taxEl) {
    const brackets = tax.brackets || [];
    const rows = [
      `<div class="hui-bracket"><span>≤${esc(tax.free ?? 800)}</span><small>免征</small></div>`,
      ...brackets.map((b) => {
        const span = b.hi == null ? `${esc(b.lo)}+` : `${esc(b.lo)}–${esc(b.hi)}`;
        return `<div class="hui-bracket"><span>${span}</span><small>${esc(b.name)} ${esc(b.rate)}%</small></div>`;
      }),
    ].join('');
    taxEl.innerHTML = `
      <div class="hui-card">
        <small>本周已入池</small>
        <strong>${esc(tax.collected ?? 0)} 票</strong>
        <p>口袋现票超额累进。未过 ${esc(tax.free ?? 800)} 免征。高档加码（阔手 14%、豪客 20%、潮主 26%、潮宗 36%）。东八区每周一换班自动划进潮汐基金。欠税时不能扩地扩产。</p>
        <small>${esc(tax.next || '')} · 本周应 ${esc(tax.assessed ?? 0)}</small>
        <div class="hui-brackets">${rows}</div>
      </div>
    `;
  }

  const upkeep = data.upkeep || {};
  const upkeepEl = document.getElementById('hui-upkeep');
  if (upkeepEl) {
    const rates = upkeep.rates || [];
    const rows = rates.length
      ? rates.map((r) => (
        `<div class="hui-bracket"><span>${esc(r.label)}</span><small>${esc(r.rate)} 票/${esc(r.unit || '')}</small></div>`
      )).join('')
      : '<div class="hui-bracket"><span>起步份地/果园免</span><small>扩了才交</small></div>';
    upkeepEl.innerHTML = `
      <div class="hui-card">
        <small>今日已入池</small>
        <strong>${esc(upkeep.collected ?? 0)} 票</strong>
        <p>按产业每天收。起步 3 块份地、3 树位免征；超出份地 10/18/28、果园 20/32/48、温室 30/48/70，铺多了加档。畜栏、渔排、盐田、矿坑 10。开馆 12；小屋/船 10/15/20。东八区换班后自动划，不是岸税。欠维修费时不能扩产，开着的小馆暂停堂食。</p>
        <small>${esc(upkeep.next || '')} · 今日应 ${esc(upkeep.assessed ?? 0)}</small>
        <div class="hui-brackets">${rows}</div>
      </div>
    `;
  }

  const beacons = data.beacons || [];
  const beaconEl = document.getElementById('hui-beacons');
  if (beaconEl) {
    beaconEl.innerHTML = beacons.length
      : beacons.map((b) => (
        `<div class="hui-notice"><span>${b.tag ? `【${esc(b.tag)}】 ` : ''}${esc(b.body)}</span><small>${esc(b.author || '潮生会')}</small></div>`
      )).join('')
      : '<p class="pl-empty">墙上还空着。告示由潮生会张贴，岛民不能贴。</p>';
  }

  const recent = data.recent || [];
  const feedEl = document.getElementById('hui-feed');
  if (feedEl) {
    feedEl.innerHTML = recent.length
      ? recent.map((r) => (
        `<div class="hui-log">${esc(r.text)}<small> · ${clock(r.created_at)}</small></div>`
      )).join('')
      : '<p class="pl-empty">还没有人来办事。</p>';
  }
}

loadHui();
setInterval(loadHui, 12000);
