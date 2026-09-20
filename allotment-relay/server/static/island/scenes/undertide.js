import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=undertide-desks1";
import { api } from "../api.js?v=undertide-desks1";
import { esc, showFormSheet, toast } from "../ui/modal.js?v=undertide-desks1";

/** 热区对齐井下总览原有的地点牌；底图本身不改动。 */
const HOTS = [
  { id: "undertide-backroom", title: "后室铺", desk: "market", speaker: "后室铺", peek: "看货架", left: 7, top: 16, w: 35, h: 22 },
  { id: "undertide-bounty", title: "恩怨墙", desk: "bounty", speaker: "恩怨墙", peek: "看墙", left: 40, top: 21, w: 23, h: 18 },
  { id: "undertide-bank", title: "恶猫钱庄", desk: "bank", speaker: "恶猫钱庄行长", peek: "见行长", sprite: "cat-bank-president", name: "恶猫钱庄行长", left: 65, top: 16, w: 31, h: 22 },
  { id: "undertide-casino", title: "死人赌场", desk: "casino", speaker: "Silas", peek: "见 Silas", sprite: "silas", name: "Silas", left: 65, top: 37, w: 31, h: 20 },
  { id: "undertide-medic", title: "晏安医务间", desk: "medic", speaker: "晏安", peek: "见晏安", left: 65, top: 58, w: 31, h: 18 },
];

/** 先展示完整总览，点已有地点牌才进入对应场景。 */
export function renderUndertide(root, { onDetailChange } = {}) {
  const showMap = () => {
    if (typeof onDetailChange === "function") onDetailChange(false);
    root.innerHTML = `
    <div class="island-map island-undertide-map">
      <div class="island-map-board island-undertide-board">
        ${sceneArt("undertide-map")}
        ${HOTS.map(hotMarkup).join("")}
      </div>
    </div>
  `;
    root.querySelectorAll("[data-undertide-place]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const id = btn.getAttribute("data-undertide-place");
        const spot = HOTS.find((item) => item.id === id);
        if (spot) showPlace(spot);
      });
    });
    layoutCoverBoard(root.querySelector(".island-undertide-map"), ".island-undertide-board", 941, 1672);
  };

  const showPlace = (spot) => {
    renderUndertideNpc(root, spot);
    if (typeof onDetailChange === "function") onDetailChange(true, showMap);
  };

  showMap();
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
}

function renderUndertideNpc(root, spot) {
  const stand = spot.sprite
    ? `<div class="island-vn-stand is-half"><img class="island-vn-sprite" src="/static/island/assets/sprites/${spot.sprite}.png" alt="${esc(spot.name || spot.speaker)}" draggable="false"></div>`
    : "";
  root.innerHTML = `
    <div class="island-vn island-undertide-vn is-peek" data-ut-desk="${esc(spot.desk)}">
      <div class="island-vn-board">
        ${sceneArt(spot.id)}
        ${stand}
        <div class="island-vn-talk is-line">
          <button type="button" class="island-vn-box" data-ut-advance><span class="island-vn-name"></span><p class="island-vn-line"></p><i class="island-vn-more" aria-hidden="true"></i></button>
          <div class="island-vn-choices"></div>
        </div>
        <button type="button" class="island-scene-tap">点一下${spot.peek}</button>
      </div>
    </div>
  `;
  const wrap = root.querySelector(".island-undertide-vn");
  const board = wrap.querySelector(".island-vn-board");
  board.addEventListener("click", () => {
    if (wrap.classList.contains("is-peek")) openUndertideNpc(wrap, spot);
  });
}

async function openUndertideNpc(wrap, spot) {
  wrap.classList.remove("is-peek");
  try {
    const snap = await api.undertide();
    paintUndertideTalk(wrap, spot, snap.undertide || {});
  } catch (err) {
    paintUndertideTalk(wrap, spot, {}, err.message || "这会儿不见客。");
  }
}

function deskLine(spot, under) {
  if (spot.desk === "bank") return under.bank;
  if (spot.desk === "casino") return under.casino;
  if (spot.desk === "market") return under.market;
  if (spot.desk === "bounty") return under.bounty;
  if (spot.desk === "medic") return under.medic;
  return "";
}

function paintUndertideTalk(wrap, spot, under, override = "") {
  const talk = wrap.querySelector(".island-vn-talk");
  const name = wrap.querySelector(".island-vn-name");
  const line = wrap.querySelector(".island-vn-line");
  const box = wrap.querySelector("[data-ut-advance]");
  if (!talk || !name || !line || !box) return;
  name.textContent = spot.speaker;
  line.textContent = override || deskLine(spot, under) || "这会儿没有可看的。";
  talk.classList.add("is-line");
  talk.classList.remove("is-picks");
  box.onclick = () => paintUndertideChoices(wrap, spot, under);
}

function paintUndertideChoices(wrap, spot, under, mode = "main") {
  const talk = wrap.querySelector(".island-vn-talk");
  const list = wrap.querySelector(".island-vn-choices");
  if (!talk || !list) return;
  talk.classList.remove("is-line");
  talk.classList.add("is-picks");
  const rows = deskChoices(spot, under, mode);
  list.innerHTML = rows.map((row) => `<button type="button" class="island-vn-choice" data-ut-kind="${esc(row.kind)}" data-ut-target="${esc(row.target || "")}"><b>${esc(row.label)}</b>${row.note ? `<small>${esc(row.note)}</small>` : ""}</button>`).join("");
  list.querySelectorAll("[data-ut-kind]").forEach((btn) => btn.addEventListener("click", () => chooseDeskAction(
    btn.getAttribute("data-ut-kind"), btn.getAttribute("data-ut-target") || "", spot, wrap, under,
  )));
}

function deskChoices(spot, under, mode) {
  if (spot.desk === "bank") {
    const rows = [];
    const well = under.well || {};
    if (well.hazard === "crack" && (well.crack_actions || []).length) {
      for (const act of well.crack_actions) {
        rows.push({
          kind: "well_crack",
          target: act.action,
          label: `井裂·${act.label}`,
          note: act.can ? (act.hint || "") : (act.disabled_reason || ""),
        });
      }
    }
    rows.push(
      { kind: "bank_debt", label: "查账" }, { kind: "bank_borrow", label: "借票" }, { kind: "bank_repay", target: "ask", label: "还款" },
      { kind: "bank_save", label: "存钱" }, { kind: "bank_take", target: "ask", label: "取钱" },
    );
    return rows;
  }
  if (spot.desk === "casino") {
    if (mode === "dice") return [
      { kind: "casino_dice", target: "small", label: "押小", note: "×2" }, { kind: "casino_dice", target: "big", label: "押大", note: "×2" }, { kind: "casino_dice", target: "black", label: "押黑潮", note: "对子 ×5" },
    ];
    if (mode === "lantern") return [
      { kind: "casino_lantern", target: "start", label: "开一局" }, { kind: "casino_lantern", target: "continue", label: "继续" }, { kind: "casino_lantern", target: "cash", label: "收手" },
    ];
    if (!under.casino_open) return [{ kind: "casino_desk", label: "看门牌" }];
    return [
      { kind: "casino_desk", label: "看赌桌" }, { kind: "menu", target: "dice", label: "黑潮骰" }, { kind: "menu", target: "lantern", label: "最后一盏灯" }, { kind: "casino_draw", label: "死人抽牌" },
    ];
  }
  if (spot.desk === "market") return [
    { kind: "market_desk", label: "看货架" },
    { kind: "racket_accept", label: "认栽成交", note: "阿标那一笔认了" },
    { kind: "racket_refuse", label: "硬扛", note: "战力判定" },
    { kind: "market_buy", label: "按编号买" },
    { kind: "market_repair", label: "找掌柜修" },
  ];
  if (spot.desk === "bounty") return [
    { kind: "bounty_desk", label: "看墙" },
    { kind: "bounty_take", label: "接单" },
    { kind: "bounty_post", label: "挂单" },
  ];
  return [
    { kind: "medic", target: "ring_shock", label: "治斗场震伤" },
    { kind: "medic", target: "pit_trauma", label: "治深坑重创" },
    { kind: "medic", target: "sprain", label: "治扭伤" },
    { kind: "medic", target: "backache", label: "治腰肌劳损" },
    { kind: "pit_drug", target: "list", label: "看体质药" },
  ];
}

function chooseDeskAction(kind, target, spot, wrap, under) {
  if (kind === "menu") return paintUndertideChoices(wrap, spot, under, target);
  if (kind === "well_crack") return runDeskAction(kind, target, spot, wrap);
  if (kind === "bank_debt" || kind === "casino_desk" || kind === "market_desk" || kind === "bounty_desk" || kind === "market_repair" || kind === "racket_accept" || kind === "racket_refuse" || kind === "medic" || kind === "pit_drug") {
    return runDeskAction(kind, target, spot, wrap);
  }
  if (kind === "bank_save" || kind === "bank_borrow") return askAmount(kind, "票数", spot, wrap);
  if (kind === "bank_take" || kind === "bank_repay") {
    if (target === "ask") return askAmount(kind, "票数（填 all 可全部）", spot, wrap, "", true);
  }
  if (kind === "casino_dice") return askAmount(kind, "下注票数", spot, wrap, target);
  if (kind === "casino_lantern") return target === "start" ? askAmount(kind, "下注票数", spot, wrap) : runDeskAction(kind, target, spot, wrap);
  if (kind === "casino_draw") {
    return showFormSheet({ title: "死人抽牌", body: "填下注和停牌点（12 到 20），这一把一次结算。", fields: [{ id: "bet", label: "下注票数", placeholder: "10" }, { id: "stand", label: "停牌点", placeholder: "17" }], confirm: "发牌", onConfirm: (values) => runDeskAction(kind, `${values.bet} ${values.stand}`, spot, wrap) });
  }
  if (kind === "market_buy") {
    return showFormSheet({ title: "按编号买", body: "写下货架编号。离柜概不认账。", fields: [{ id: "slot", label: "编号", placeholder: "1" }], confirm: "买", onConfirm: (values) => runDeskAction(kind, values.slot, spot, wrap) });
  }
  if (kind === "bounty_take") {
    return showFormSheet({ title: "接单", body: "写下墙上的悬赏编号。", fields: [{ id: "id", label: "编号", placeholder: "1" }], confirm: "接", onConfirm: (values) => runDeskAction(kind, values.id, spot, wrap) });
  }
  if (kind === "bounty_post") {
    return showFormSheet({
      title: "挂单",
      body: "steal 毁地，beat 打人。赏金另加手续费。",
      fields: [
        { id: "tier", label: "steal 或 beat", placeholder: "beat" },
        { id: "name", label: "名字", placeholder: "对方管家名" },
        { id: "bounty", label: "赏金", placeholder: "40" },
      ],
      confirm: "挂",
      onConfirm: (values) => runDeskAction(kind, `${values.tier} ${values.name} ${values.bounty}`, spot, wrap),
    });
  }
}

function askAmount(kind, label, spot, wrap, prefix = "", allowAll = false) {
  showFormSheet({
    title: label,
    body: allowAll ? "填正整数，或填 all 一次结清。实际限额和余额由柜台当场核。" : "只收正整数；实际限额和余额由柜台当场核。",
    fields: [{ id: "amount", label, placeholder: "10" }],
    confirm: "交给柜台",
    onConfirm: (values) => runDeskAction(kind, prefix ? `${prefix} ${values.amount}` : values.amount, spot, wrap),
  });
}

async function runDeskAction(kind, target, spot, wrap) {
  try {
    const snap = await api.undertideAct(kind, target);
    const event = snap.event || {};
    if (!wrap || !wrap.isConnected) return;
    paintUndertideTalk(wrap, spot, snap.undertide || {}, event.narrative || "这一下结清了。");
  } catch (err) {
    toast(err.message || "这一下没做成。");
  }
}

function hotMarkup(spot) {
  const style = `left:${spot.left}%;top:${spot.top}%;width:${spot.w}%;height:${spot.h}%`;
  return `<button type="button" class="island-hot" data-undertide-place="${spot.id}" style="${style}" aria-label="${spot.title}"></button>`;
}
