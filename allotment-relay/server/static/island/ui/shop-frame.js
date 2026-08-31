import { layoutCoverBoard, sceneArt } from "./art.js?v=island-ting2";

/** 店景只铺一次。点一下只叠出列表，不换裁切、不重载底图。 */
export function ensureShopFrame(root, {
  find,
  className,
  sceneId,
  tap,
  fold = "收起列表",
  listId,
  tabAria = "列表",
}) {
  let wrap = find(root);
  if (wrap && wrap.querySelector(".island-shop-board") && wrap.querySelector(".island-shop-shelf")) {
    return wrap;
  }
  root.innerHTML = `
    <div class="${className} is-peek">
      <div class="island-shop-board">
        ${sceneArt(sceneId)}
        <button type="button" class="island-scene-tap">${tap}</button>
      </div>
      <button type="button" class="island-scene-fold" aria-label="${fold}"></button>
      <div class="island-shop-shelf">
        <div class="island-shop-meta"><b></b><small></small></div>
        <div class="island-shop-tabs" role="tablist" aria-label="${tabAria}"></div>
        <div class="island-shop-list" id="${listId}"></div>
      </div>
    </div>
  `;
  wrap = find(root);
  layoutCoverBoard(wrap, ".island-shop-board", 941, 1672);
  return wrap;
}

export function bindShopFrame(wrap, { onOpenShelf, onCloseShelf } = {}) {
  const board = wrap.querySelector(".island-shop-board");
  if (board && !board._bound) {
    board._bound = true;
    board.addEventListener("click", () => {
      if (!wrap.classList.contains("is-peek")) return;
      if (onOpenShelf) onOpenShelf();
    });
  }
  const fold = wrap.querySelector(".island-scene-fold");
  if (fold && !fold._bound) {
    fold._bound = true;
    fold.addEventListener("click", (ev) => {
      ev.stopPropagation();
      if (onCloseShelf) onCloseShelf();
    });
  }
}

export function setShopPeek(wrap, peek) {
  if (wrap) wrap.classList.toggle("is-peek", peek);
}
