/** 插图位。文件放到 /static/island/assets/scenes/{id}.png 就会自动铺上。 */

export const SLOTS = {
  "island-map": { label: "岛屿总览", size: "972×1619" },
  home: { label: "家园院子", size: "1080×1920" },
  yards: { label: "份地", size: "941×1672" },
  shore: { label: "港口", size: "1080×1920" },
  plaza: { label: "潮汐广场", size: "1080×1920" },
  hut: { label: "岸畔小屋", size: "1080×1920" },
  bar: { label: "潮汐酒吧", size: "1080×1920" },
  theater: { label: "潮汐剧场", size: "1080×1920" },
  eatery: { label: "岸畔小馆", size: "1080×1920" },
  hui: { label: "潮生会", size: "1080×1920" },
};

export function sceneArt(id) {
  const meta = SLOTS[id] || { label: id, size: "1080×1920" };
  return `<div class="island-slot" data-slot="${id}">
    <img class="island-slot-pic" src="/static/island/assets/scenes/${id}.png" alt="" onerror="this.closest('.island-slot').classList.add('is-empty')">
    <span class="island-slot-mark"><b>插图位</b><small>${meta.label} · ${meta.size}</small></span>
  </div>`;
}
