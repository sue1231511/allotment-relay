import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=mod-unify1";
import { api } from "../api.js?v=mod-unify1";
import { esc, showFormSheet, toast } from "../ui/modal.js?v=mod-unify1";

/**
 * 热区对齐井下总览原有的地点牌；底图本身不改动。
 * fetch：进这一处时 GET /undertide?desk=… 多取的柜台（柜台每看一次都会掷井下随机事件，不一股脑全取）。
 * gated：没下过井（access）就用不了的柜台，对话里给「去井口」。
 */
const HOTS = [
  { id: "undertide-well", title: "井下入口", desk: "well", speaker: "井口", peek: "看井", fetch: "well", left: 38, top: 6, w: 28, h: 16 },
  { id: "undertide-backroom", title: "后室铺", desk: "market", speaker: "后室铺", peek: "看货架", left: 7, top: 16, w: 35, h: 22 },
  { id: "undertide-bounty", title: "恩怨墙", desk: "bounty", speaker: "恩怨墙", peek: "看墙", left: 40, top: 21, w: 23, h: 18 },
  { id: "undertide-bank", title: "恶猫钱庄", desk: "bank", speaker: "恶猫钱庄行长", peek: "见行长", sprite: "cat-bank-president", name: "恶猫钱庄行长", left: 65, top: 16, w: 31, h: 22 },
  { id: "undertide-casino", title: "死人赌场", desk: "casino", speaker: "Silas", peek: "见 Silas", sprite: "silas", name: "Silas", left: 65, top: 37, w: 31, h: 20 },
  { id: "undertide-pit", title: "深坑", desk: "pit", speaker: "深坑看门人", peek: "看深坑", fetch: "pit", gated: true, left: 0, top: 39, w: 45, h: 16 },
  { id: "undertide-tavern", title: "凯斯酒馆", desk: "tavern", speaker: "凯斯酒馆", peek: "进酒馆", fetch: "tavern", gated: true, left: 26, top: 55, w: 36, h: 14 },
  { id: "undertide-medic", title: "晏安医务间", desk: "medic", speaker: "晏安", peek: "见晏安", left: 65, top: 58, w: 31, h: 18 },
  { id: "undertide-jail", title: "地下监牢", desk: "jail", speaker: "狱卒", peek: "看监牢", fetch: "jail", left: 3, top: 69, w: 34, h: 9 },
  { id: "undertide-kroom", title: "K 室", desk: "kroom", speaker: "K 室", peek: "敲门", fetch: "kroom", left: 27, top: 78, w: 38, h: 22 },
];

/** 一点就办的动作：不用再填东西。 */
const RUN_NOW = new Set([
  "well_look", "well_descend", "well_enter", "well_guide", "well_clean", "well_status", "well_crack",
  "pit_list", "pit_board", "tavern_visit", "tavern_chat", "tavern_whisper", "tavern_spy", "tavern_ai", "tavern_ruby", "tavern_bleed",
  "jail_status", "jail_ransom", "jail_serve", "jail_work", "kroom_status", "kroom_settle", "kroom_vr",
  "street", "lottery", "refine_list", "pit_fight", "grudge", "casino_lantern",
  "bank_debt", "casino_desk", "market_desk", "bounty_desk", "market_repair", "racket_accept", "racket_refuse", "medic", "pit_drug",
]);

/** 要填东西的动作。 */
const FORMS = {
  bank_save: () => amountForm("bank_save", "存钱", "票数"),
  bank_borrow: () => amountForm("bank_borrow", "借票", "票数"),
  bank_take: () => amountForm("bank_take", "取钱", "票数（填 all 可全部）", "", true),
  bank_repay: () => amountForm("bank_repay", "还款", "票数（填 all 可全部）", "", true),
  casino_dice: (target) => amountForm("casino_dice", "黑潮骰", "下注票数", target),
  casino_lantern: () => amountForm("casino_lantern", "最后一盏灯", "下注票数"),
  casino_draw: () => ({
    title: "死人抽牌", body: "填下注和停牌点（12 到 20），这一把一次结算。",
    fields: [{ id: "bet", label: "下注票数", placeholder: "10" }, { id: "stand", label: "停牌点", placeholder: "17" }],
    confirm: "发牌", target: (v) => `${v.bet} ${v.stand}`,
  }),
  market_buy: () => ({
    title: "按编号买", body: "写下货架编号。离柜概不认账。",
    fields: [{ id: "slot", label: "编号", placeholder: "1" }], confirm: "买", target: (v) => v.slot,
  }),
  bounty_take: () => ({
    title: "接单", body: "写下墙上的悬赏编号。",
    fields: [{ id: "id", label: "编号", placeholder: "1" }], confirm: "接", target: (v) => v.id,
  }),
  bounty_post: () => ({
    title: "挂单", body: "steal 毁地，beat 打人。赏金另加手续费。",
    fields: [
      { id: "tier", label: "steal 或 beat", placeholder: "beat" },
      { id: "name", label: "名字", placeholder: "对方管家名" },
      { id: "bounty", label: "赏金", placeholder: "40" },
    ],
    confirm: "挂", target: (v) => `${v.tier} ${v.name} ${v.bounty}`,
  }),
  muscle: () => ({
    title: "强买", body: "写帘外街上那个人的名号（先点「看帘外街」）。战力判定，输了有后果。",
    fields: [{ id: "name", label: "名号", placeholder: "名号" }], confirm: "出手", target: (v) => v.name,
  }),
  push: () => ({
    title: "强卖", body: "写名号和要塞给他的物品。",
    fields: [{ id: "name", label: "名号", placeholder: "名号" }, { id: "item", label: "物品", placeholder: "物品" }],
    confirm: "硬塞", target: (v) => `${v.name} ${v.item}`,
  }),
  hijack: () => ({
    title: "劫持", body: "后果自负。写要劫持的对象。",
    fields: [{ id: "name", label: "对象", placeholder: "名字" }], confirm: "动手", target: (v) => v.name,
  }),
  sell: () => ({
    title: "出货", body: "掌柜收货。店货按行价、赃物走高价通道（物品名后加（赃））。数量不写就一件。",
    fields: [{ id: "item", label: "物品", placeholder: "物品" }, { id: "qty", label: "数量", placeholder: "1" }],
    confirm: "出货", target: (v) => `${v.item}${v.qty ? ` ${v.qty}` : ""}`,
  }),
  refine: () => ({
    title: "炼", body: "写炼制名（先点「看炼制单」）：brine_crystal、岸黑盐 之类。扣行囊里的料。",
    fields: [{ id: "key", label: "炼制名", placeholder: "brine_crystal" }], confirm: "开炼", target: (v) => v.key,
  }),
  cheer: () => ({
    title: "哄猫猫", body: "潮下老板娘，不是地面酒吧的荔栀。写一句好话。",
    fields: [{ id: "text", label: "好话", placeholder: "今天也辛苦了" }], confirm: "说", target: (v) => v.text,
  }),
};

function amountForm(kind, title, label, prefix = "", allowAll = false) {
  return {
    title,
    body: allowAll ? "填正整数，或填 all 一次结清。实际限额和余额由柜台当场核。" : "只收正整数；实际限额和余额由柜台当场核。",
    fields: [{ id: "amount", label, placeholder: "10" }],
    confirm: "交给柜台",
    target: (v) => (prefix ? `${prefix} ${v.amount}` : v.amount),
  };
}

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

  const showPlace = (spot, autoOpen = false) => {
    renderUndertideNpc(root, spot, showPlace, autoOpen);
    if (typeof onDetailChange === "function") onDetailChange(true, showMap);
  };

  showMap();
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
}

function renderUndertideNpc(root, spot, goto, autoOpen = false) {
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
  wrap._goto = (dest) => goto(dest, true);
  const board = wrap.querySelector(".island-vn-board");
  board.addEventListener("click", () => {
    if (wrap.classList.contains("is-peek")) openUndertideNpc(wrap, spot);
  });
  if (autoOpen) openUndertideNpc(wrap, spot);
}

async function openUndertideNpc(wrap, spot) {
  wrap.classList.remove("is-peek");
  try {
    const snap = await api.undertide(spot.fetch || "");
    paintUndertideTalk(wrap, spot, snap.undertide || {});
  } catch (err) {
    console.error("[undertide] 打开柜台失败", spot.id, err);
    paintUndertideTalk(wrap, spot, {}, err.message || "这会儿不见客。");
  }
}

function deskLine(spot, under) {
  const byDesk = {
    bank: under.bank, casino: under.casino, market: under.market, bounty: under.bounty, medic: under.medic,
    well: under.well_text, pit: under.pit_text, tavern: under.tavern_text, jail: under.jail_text, kroom: under.kroom_text,
  };
  return byDesk[spot.desk] || "";
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
  if (wrap._confirm && mode === "main") rows.unshift(wrap._confirm);
  list.innerHTML = rows.map((row) => `<button type="button" class="island-vn-choice${row.off ? " is-off" : ""}" data-ut-kind="${esc(row.kind)}" data-ut-target="${esc(row.target || "")}"><b>${esc(row.label)}</b>${row.note ? `<small>${esc(row.note)}</small>` : ""}</button>`).join("");
  list.querySelectorAll("[data-ut-kind]").forEach((btn) => btn.addEventListener("click", () => chooseDeskAction(
    btn.getAttribute("data-ut-kind"), btn.getAttribute("data-ut-target") || "", spot, wrap, under,
  )));
}

const BACK = { kind: "menu", target: "main", label: "返回" };

function needAccess(under) {
  return [{ kind: "goto", target: "undertide-well", label: "去井口", note: under.well_hint ? "先下井，才进得了这里" : "先去看看那口井" }];
}

function deskChoices(spot, under, mode) {
  if (mode.startsWith("pit_strat:")) {
    const name = mode.slice("pit_strat:".length);
    return [
      { kind: "pit_fight", target: `${name} attack`, label: "攻", note: "克虚晃" },
      { kind: "pit_fight", target: `${name} guard`, label: "守", note: "克攻" },
      { kind: "pit_fight", target: `${name} feint`, label: "虚晃", note: "克守" },
      { kind: "pit_fight", target: name, label: "随机", note: "不挑打法" },
      { kind: "menu", target: "pit_pick", label: "换个斗士" },
    ];
  }
  if (spot.desk === "well") {
    const rows = [];
    const crack = under.well || {};
    if (crack.hazard === "crack" && (crack.crack_actions || []).length) {
      for (const act of crack.crack_actions) {
        rows.push({ kind: "well_crack", target: act.action, label: `井裂·${act.label}`, note: act.can ? (act.hint || "") : (act.disabled_reason || "") });
      }
    }
    if (!under.access) {
      rows.push({ kind: "well_look", label: "看井", note: "看一眼不算岛缘" }, { kind: "well_descend", label: "下井", note: "3 票 · 岛缘 −25" });
      return rows;
    }
    rows.push(
      { kind: "well_enter", label: "进入潮下", note: "每次岛缘 −12" },
      { kind: "well_status", label: "潮下档案", note: "影信 · 债务 · 案底" },
      { kind: "well_guide", label: "井下指南" },
      { kind: "well_clean", label: "清井" },
      { kind: "well_look", label: "再看一眼井" },
    );
    return rows;
  }
  if (spot.desk === "pit") {
    if (!under.access) return needAccess(under);
    if (mode === "pit_pick") {
      const rows = (under.pit || []).map((f) => ({
        kind: "menu", target: `pit_strat:${f.name}`, label: `${f.name} · Lv${f.level}`, note: `入场 ${f.entry} · 胜奖 ${f.prize} · ${f.wins}胜${f.losses}负`,
      }));
      rows.push(BACK);
      return rows;
    }
    return [
      { kind: "menu", target: "pit_pick", label: "下坑", note: "先选斗士，再选打法" },
      { kind: "pit_list", label: "看斗士榜" },
      { kind: "pit_board", label: "井壁胜场榜" },
      { kind: "goto", target: "undertide-medic", label: "去医务间", note: "下坑前的体质药、下坑后的伤" },
    ];
  }
  if (spot.desk === "tavern") {
    if (!under.access) return needAccess(under);
    return [
      { kind: "tavern_visit", label: "看债务者黑板" },
      { kind: "tavern_chat", label: "跟荔栀说话" },
      { kind: "tavern_whisper", label: "耳语人买消息", note: "价随机，不赊账" },
      { kind: "tavern_spy", label: "查悬赏雇主", note: "只查挂过你的" },
      { kind: "tavern_ai", label: "别人的动态", note: "三天内公开的" },
      { kind: "tavern_ruby", label: "点红宝石", note: "先问价，再确认" },
      { kind: "tavern_bleed", label: "卖血", note: "先问价，再确认" },
    ];
  }
  if (spot.desk === "jail") return [
    { kind: "jail_status", label: "看牢房" },
    { kind: "jail_ransom", label: "赎身" },
    { kind: "jail_serve", label: "服刑" },
    { kind: "jail_work", label: "苦力", note: "服刑中才能干" },
  ];
  if (spot.desk === "kroom") return [
    { kind: "kroom_status", label: "看 K 室" },
    { kind: "kroom_settle", label: "结算" },
    { kind: "kroom_vr", label: "价值回收" },
  ];
  if (spot.desk === "bank") {
    const rows = [];
    const crack = under.well || {};
    if (crack.hazard === "crack" && (crack.crack_actions || []).length) {
      for (const act of crack.crack_actions) {
        rows.push({ kind: "well_crack", target: act.action, label: `井裂·${act.label}`, note: act.can ? (act.hint || "") : (act.disabled_reason || "") });
      }
    }
    rows.push(
      { kind: "bank_debt", label: "查账" }, { kind: "bank_borrow", label: "借票" }, { kind: "bank_repay", target: "ask", label: "还款" },
      { kind: "bank_save", label: "存钱" }, { kind: "bank_take", target: "ask", label: "取钱" },
      { kind: "cheer", label: "哄猫猫", note: "潮下老板娘" },
    );
    return rows;
  }
  if (spot.desk === "casino") {
    if (mode === "dice") return [
      { kind: "casino_dice", target: "small", label: "押小", note: "×2" }, { kind: "casino_dice", target: "big", label: "押大", note: "×2" }, { kind: "casino_dice", target: "black", label: "押黑潮", note: "对子 ×5" },
      BACK,
    ];
    if (mode === "lantern") return [
      { kind: "casino_lantern", target: "start", label: "开一局" }, { kind: "casino_lantern", target: "continue", label: "继续" }, { kind: "casino_lantern", target: "cash", label: "收手" },
      BACK,
    ];
    if (!under.casino_open) return [{ kind: "casino_desk", label: "看门牌" }, ...needAccess(under)];
    return [
      { kind: "casino_desk", label: "看赌桌" }, { kind: "menu", target: "dice", label: "黑潮骰" }, { kind: "menu", target: "lantern", label: "最后一盏灯" }, { kind: "casino_draw", label: "死人抽牌" },
      { kind: "lottery", label: "潮汐博彩", note: "Jester 的旧机器" },
    ];
  }
  if (spot.desk === "market") {
    if (mode === "street") return [
      { kind: "street", label: "看帘外街", note: "每日刷新的人" },
      { kind: "muscle", label: "强买", note: "战力判定" },
      { kind: "push", label: "强卖" },
      BACK,
    ];
    if (mode === "refine") return [
      { kind: "refine_list", label: "看炼制单" },
      { kind: "refine", label: "开炼", note: "扣行囊里的料" },
      BACK,
    ];
    return [
      { kind: "market_desk", label: "看货架" },
      { kind: "racket_accept", label: "认栽成交", note: "阿标那一笔认了" },
      { kind: "racket_refuse", label: "硬扛", note: "战力判定" },
      { kind: "market_buy", label: "按编号买" },
      { kind: "market_repair", label: "找掌柜修" },
      { kind: "sell", label: "出货" },
      { kind: "menu", target: "refine", label: "潮下炼制", note: "淤泥+崖盐→卤晶" },
      { kind: "menu", target: "street", label: "帘外街", note: "强买强卖" },
    ];
  }
  if (spot.desk === "bounty") {
    if (mode === "grudge") return [
      { kind: "grudge", target: "pay", label: "赔钱了事" },
      { kind: "grudge", target: "fight", label: "迎战" },
      { kind: "grudge", target: "run", label: "跑" },
      BACK,
    ];
    return [
      { kind: "bounty_desk", label: "看墙" },
      { kind: "bounty_take", label: "接单" },
      { kind: "bounty_post", label: "挂单" },
      { kind: "hijack", label: "劫持", note: "后果自负" },
      { kind: "menu", target: "grudge", label: "寻仇应对", note: "有人找上门才用" },
    ];
  }
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
  if (kind === "goto") {
    const dest = HOTS.find((item) => item.id === target);
    if (dest && typeof wrap._goto === "function") return wrap._goto(dest);
    return undefined;
  }
  if (FORMS[kind] && !(kind === "casino_lantern" && target !== "start")) {
    const form = FORMS[kind](target);
    return showFormSheet({
      title: form.title,
      body: form.body,
      fields: form.fields,
      confirm: form.confirm,
      onConfirm: (values) => runDeskAction(kind, form.target(values), spot, wrap),
    });
  }
  if (RUN_NOW.has(kind)) return runDeskAction(kind, target, spot, wrap);
  console.error("[undertide] 没接上的动作", kind, target);
  toast("这一下还没接上。");
  return undefined;
}

async function runDeskAction(kind, target, spot, wrap) {
  try {
    wrap._confirm = null;
    const snap = await api.undertideAct(kind, target);
    const event = snap.event || {};
    if (!wrap || !wrap.isConnected) return;
    // 红宝石、卖血是两步：第一步只报价，确认才扣。报价后把「确认」放在选项最前面。
    if ((kind === "tavern_ruby" || kind === "tavern_bleed") && !target) {
      wrap._confirm = { kind, target: "confirm", label: kind === "tavern_ruby" ? "确认点红宝石" : "确认卖血", note: "按刚才的报价" };
    }
    paintUndertideTalk(wrap, spot, snap.undertide || {}, event.narrative || "这一下结清了。");
  } catch (err) {
    console.error("[undertide] 动作失败", kind, target, err);
    toast(err.message || "这一下没做成。");
  }
}

function hotMarkup(spot) {
  const style = `left:${spot.left}%;top:${spot.top}%;width:${spot.w}%;height:${spot.h}%`;
  return `<button type="button" class="island-hot" data-undertide-place="${spot.id}" style="${style}" aria-label="${spot.title}"></button>`;
}
