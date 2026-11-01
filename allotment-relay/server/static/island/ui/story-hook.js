import { BOOK_SVG, PLACE_NAME, PLACE_SCENES, loadStories, onStoryChange, openPlaceStory } from "./stories.js?v=story1";
import { esc } from "./modal.js?v=mod-unify1";

/**
 * 走到对应地点，顶上冒一枚「故事 · 去海边看看」小牌。
 * 只在当前一步真对得上这个地点时出现；没有进行中的故事，或这一步在别处，就不出现。
 */
let current = "";
let seq = 0;

function hookEl() {
  return document.getElementById("island-story-hook");
}

function placeOf(scene) {
  return Object.keys(PLACE_SCENES).find((p) => PLACE_SCENES[p].includes(scene)) || "";
}

function paint(data, place) {
  const el = hookEl();
  if (!el) return;
  const steps = [];
  (data?.active || []).forEach((row) => (row.actions || []).forEach((s) => {
    if (s.place === place) steps.push({ title: row.title, label: s.label });
  }));
  if (!place || !steps.length) {
    el.hidden = true;
    return;
  }
  el.innerHTML = `${BOOK_SVG}<span>故事 · ${esc(steps[0].label)}${steps.length > 1 ? ` 等 ${steps.length} 步` : ""}</span>`;
  el.setAttribute("aria-label", `${PLACE_NAME[place] || "这里"}的故事：${steps[0].label}`);
  el.hidden = false;
  el.removeAttribute("hidden");
  el.onclick = () => openPlaceStory(place);
}

export async function mountStoryHook(scene, { enrolled = true } = {}) {
  const el = hookEl();
  if (!el) return;
  const place = enrolled ? placeOf(scene) : "";
  current = place;
  const mine = ++seq;
  if (!place) {
    el.hidden = true;
    return;
  }
  try {
    const data = await loadStories();
    if (mine === seq) paint(data, place);
  } catch (err) {
    console.error("[story-hook] 读取故事失败", scene, err);
    if (mine === seq) el.hidden = true;
  }
}

onStoryChange((data) => paint(data, current));
