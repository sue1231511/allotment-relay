/** 面板三样：白菜(kale) / 胡萝卜(beet) / 番茄(fogpea)。按 appearance 换图。 */

const SPROUT = `<svg viewBox="0 0 80 80" aria-hidden="true"><path d="M40 62v-22" stroke="#6f8f6a" stroke-width="4" stroke-linecap="round"/><path d="M40 48c-10-8-16-6-18-2" stroke="#8fbf72" stroke-width="4" fill="none" stroke-linecap="round"/><path d="M40 46c10-8 16-6 18-2" stroke="#9bb88a" stroke-width="4" fill="none" stroke-linecap="round"/></svg>`;

const ART = {
  kale: {
    growing: `<svg viewBox="0 0 80 80" aria-hidden="true"><ellipse cx="40" cy="54" rx="20" ry="14" fill="#86a576"/><ellipse cx="28" cy="48" rx="12" ry="10" fill="#b7cda3"/><ellipse cx="52" cy="48" rx="12" ry="10" fill="#6f8f6a"/><ellipse cx="40" cy="44" rx="10" ry="8" fill="#cfe0be"/></svg>`,
    ripe: `<svg viewBox="0 0 80 80" aria-hidden="true"><ellipse cx="40" cy="50" rx="24" ry="18" fill="#7d9a6c"/><ellipse cx="26" cy="44" rx="14" ry="12" fill="#b7cda3"/><ellipse cx="54" cy="44" rx="14" ry="12" fill="#86a576"/><ellipse cx="40" cy="38" rx="13" ry="11" fill="#cfe0be"/><circle cx="40" cy="46" r="7" fill="#e8f0dc"/></svg>`,
  },
  beet: {
    growing: `<svg viewBox="0 0 80 80" aria-hidden="true"><path d="M40 22c2 12 7 18 7 18s-4 0-7 5c-3-5-7-5-7-5s5-6 7-18z" fill="#7d9a6c"/><path d="M40 42l-5 16h10z" fill="#d08a4a"/></svg>`,
    ripe: `<svg viewBox="0 0 80 80" aria-hidden="true"><path d="M34 16c2 12 4 16 4 16s-3 1-5 5c1-2-5-3-5-3s4-8 6-18z" fill="#6f8f6a"/><path d="M46 16c-1 11 3 16 3 16s-4 0-4 5c3-3 8-2 8-2s-4-9-7-19z" fill="#86a576"/><path d="M40 34c10 8 10 28 0 36-10-8-10-28 0-36z" fill="#e07a3a"/><path d="M40 42c3 4 4 12 1 18" stroke="#f0b27a" stroke-width="2" fill="none"/></svg>`,
  },
  fogpea: {
    growing: `<svg viewBox="0 0 80 80" aria-hidden="true"><path d="M40 62V34" stroke="#6f8f6a" stroke-width="4" stroke-linecap="round"/><circle cx="40" cy="36" r="10" fill="#c45b4a"/><path d="M40 24c6 4 10 8 10 8" stroke="#86a576" stroke-width="3" fill="none"/></svg>`,
    ripe: `<svg viewBox="0 0 80 80" aria-hidden="true"><path d="M40 64V30" stroke="#6f8f6a" stroke-width="4" stroke-linecap="round"/><circle cx="32" cy="40" r="11" fill="#c45b4a"/><circle cx="50" cy="38" r="10" fill="#b34a3c"/><circle cx="40" cy="28" r="9" fill="#d46b5a"/><ellipse cx="28" cy="36" rx="3" ry="2" fill="#e7a197"/><path d="M48 20c8 2 12 8 12 8" stroke="#86a576" stroke-width="3" fill="none"/><circle cx="60" cy="20" r="5" fill="#7d9a6c"/></svg>`,
  },
};

export function cropArt(key, stage = "ripe") {
  if (!key || stage === "empty") return "";
  if (stage === "seedling") return SPROUT;
  const pack = ART[key] || ART.kale;
  return pack[stage] || pack.ripe || SPROUT;
}

export function neighborCrop(crops, key, delta) {
  if (!crops.length) return "";
  const i = Math.max(0, crops.findIndex((c) => c.key === key));
  return crops[(i + delta + crops.length * 10) % crops.length].key;
}
