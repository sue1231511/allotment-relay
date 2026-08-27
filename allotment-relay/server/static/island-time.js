/** 全站时间展示统一东八区（Asia/Shanghai）。 */
const ISLAND_TZ = 'Asia/Shanghai';

function islandFmtClock(epoch) {
  if (!epoch) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: ISLAND_TZ,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(Number(epoch) * 1000));
}

function islandFmtStamp(epoch) {
  if (!epoch) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: ISLAND_TZ,
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(new Date(Number(epoch) * 1000)).replace(/\//g, '-');
}

function islandFmtDate(epoch) {
  if (!epoch) return '—';
  return new Intl.DateTimeFormat('zh-CN', {
    timeZone: ISLAND_TZ,
    year: 'numeric',
    month: 'long',
    day: 'numeric',
  }).format(new Date(Number(epoch) * 1000));
}

function islandAgo(epoch) {
  if (!epoch) return '—';
  const sec = Math.max(0, Math.floor(Date.now() / 1000) - Number(epoch));
  if (sec < 60) return '刚刚';
  if (sec < 3600) return `${Math.floor(sec / 60)} 分钟前`;
  if (sec < 86400) return `${Math.floor(sec / 3600)} 小时前`;
  return `${Math.floor(sec / 86400)} 天前`;
}

function islandClockNow() {
  return islandFmtClock(Math.floor(Date.now() / 1000));
}
