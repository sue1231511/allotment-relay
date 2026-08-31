/** 插图位。文件放到 /static/island/assets/scenes/{id}.png 就会自动铺上。 */

export const SLOTS = {
  "island-map": { label: "岛屿总览", size: "972×1619", ext: "jpg" },
  home: { label: "家园院子", size: "1080×1920" },
  yards: { label: "份地", size: "941×1672" },
  shore: { label: "海边", size: "1080×1920" },
  port: { label: "港口", size: "1080×1920", file: "shore" },
  beach: { label: "海边", size: "1080×1920", file: "shore" },
  plaza: { label: "潮汐广场", size: "941×1672" },
  lili: { label: "栗栗流动摊", size: "1086×1448" },
  clinic: { label: "乔乔诊所", size: "941×1672" },
  hut: { label: "岸畔小屋", size: "1080×1920" },
  bar: { label: "潮汐酒吧", size: "1080×1920" },
  theater: { label: "潮汐剧场", size: "1080×1920" },
  writers: { label: "编剧社", size: "941×1672" },
  atelier: { label: "衣泊坊", size: "941×1672" },
  hall: { label: "剧场看台", size: "941×1672" },
  eatery: { label: "岸畔小馆", size: "941×1672" },
  hui: { label: "潮生会", size: "941×1672" },
  market: { label: "集市", size: "941×1672" },
  ting: { label: "听潮亭", size: "941×1672" },
  lianli: { label: "连理所", size: "941×1672" },
  workshop: { label: "岸工坊", size: "941×1672" },
  quarry: { label: "盐风崖", size: "941×1672" },
  shop: { label: "Tt酱杂货铺", size: "941×1672" },
  lighthouse: { label: "灯塔", size: "941×1672" },
  notice: { label: "潮汐公告", size: "1080×1920" },
};

export function scenePicUrl(id) {
  const meta = SLOTS[id] || {};
  const file = meta.file || id;
  const ext = meta.ext || "png";
  return `/static/island/assets/scenes/${file}.${ext}`;
}

export function sceneArt(id) {
  const meta = SLOTS[id] || { label: id, size: "1080×1920" };
  return `<div class="island-slot" data-slot="${id}">
    <img class="island-slot-pic" src="${scenePicUrl(id)}" alt="" decoding="async" onerror="this.closest('.island-slot').classList.add('is-empty')">
    <span class="island-slot-mark"><b>插图位</b><small>${meta.label} · ${meta.size}</small></span>
  </div>`;
}

/** 底图至少铺满滚动容器，底下不漏色；比一屏高才往下滚。 */
export function layoutCoverBoard(scroller, boardSel, fallbackW, fallbackH) {
  if (!scroller) return;
  const board = scroller.querySelector(boardSel);
  const img = scroller.querySelector(".island-slot-pic");
  if (!board || !img) return;
  const apply = () => {
    const iw = img.naturalWidth || fallbackW;
    const ih = img.naturalHeight || fallbackH;
    const cw = scroller.clientWidth;
    const ch = scroller.clientHeight;
    if (!cw) return;
    const sW = cw / iw;
    const sH = ch / ih;
    const s = Math.max(sW, sH || 0);
    const bw = Math.round(iw * s);
    const bh = Math.round(ih * s);
    board.style.width = `${bw}px`;
    board.style.height = `${bh}px`;
    board.style.left = `${Math.round((cw - bw) / 2)}px`;
    board.style.top = "0px";
  };
  apply();
  requestAnimationFrame(apply);
  img.addEventListener("load", apply);
  if (!scroller._laid) {
    scroller._laid = true;
    window.addEventListener("resize", apply);
  }
}
