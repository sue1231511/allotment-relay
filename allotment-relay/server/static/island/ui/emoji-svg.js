import { iconSvg } from "./icons.js?v=icons1";
import { EMOJI_ICON, TEXT_SYMBOLS } from "./emoji-map.js?v=icons1";

/**
 * 界面里不用 emoji：服务端文案、数据名字里带的 emoji，在落进页面的时候换成手绘 SVG 图标。
 * 对照表由 scripts/gen_emoji_icons.py 生成。聊天室消息和表情包是玩家写的内容，原样保留。
 */
const KEEP = new Set(TEXT_SYMBOLS);
const PICTO = /\p{Extended_Pictographic}(?:️|⃣|[\u{1F3FB}-\u{1F3FF}]|‍\p{Extended_Pictographic})*/gu;
const SKIP = "script,style,textarea,input,svg,[data-keep-emoji],#lounge-feed,#lounge-sticker-sheet,.lounge-sticker-grid";

function iconFor(seq) {
  const base = Array.from(seq)[0];
  return EMOJI_ICON[base] || "dot";
}

function makeIcon(seq) {
  const el = document.createElement("i");
  el.className = "island-ico";
  el.setAttribute("role", "img");
  el.setAttribute("aria-hidden", "true");
  el.innerHTML = iconSvg(iconFor(seq));
  return el;
}

function convertText(node) {
  const text = node.nodeValue;
  if (!text || !PICTO.test(text)) {
    PICTO.lastIndex = 0;
    return;
  }
  PICTO.lastIndex = 0;
  const parent = node.parentElement;
  if (!parent || parent.closest(SKIP)) return;
  const frag = document.createDocumentFragment();
  let last = 0;
  for (const m of text.matchAll(PICTO)) {
    if (KEEP.has(m[0])) continue;
    if (m.index > last) frag.append(text.slice(last, m.index));
    frag.append(makeIcon(m[0]));
    last = m.index + m[0].length;
  }
  if (last === 0) return;
  if (last < text.length) frag.append(text.slice(last));
  node.replaceWith(frag);
}

function walk(root) {
  if (root.nodeType === Node.TEXT_NODE) {
    convertText(root);
    return;
  }
  if (root.nodeType !== Node.ELEMENT_NODE || root.matches?.(SKIP)) return;
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  nodes.forEach(convertText);
}

/** 把一段文字里的 emoji 换成图标标记（给要拼 HTML 字符串的地方用；文字要先 esc）。 */
export function withIcons(escapedHtml) {
  return String(escapedHtml ?? "").replace(PICTO, (seq) => (KEEP.has(seq) ? seq : `<i class="island-ico" aria-hidden="true">${iconSvg(iconFor(seq))}</i>`));
}

let started = false;
export function startEmojiSvg() {
  if (started || typeof document === "undefined") return;
  started = true;
  try {
    walk(document.body);
    const observer = new MutationObserver((records) => {
      for (const rec of records) {
        if (rec.type === "characterData") convertText(rec.target);
        rec.addedNodes.forEach((n) => walk(n));
      }
    });
    observer.observe(document.body, { childList: true, subtree: true, characterData: true });
  } catch (err) {
    console.error("[emoji-svg] 启动失败", err);
  }
}
