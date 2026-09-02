import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=undertide-scenes1";
import { renderPlace } from "./place.js?v=undertide-scenes1";
import { api } from "../api.js?v=undertide-scenes1";
import { esc, showFormSheet, toast } from "../ui/modal.js?v=undertide-scenes1";

/** 热区对齐井下总览原有的地点牌；底图本身不改动。 */
const HOTS = [
  { id: "undertide-backroom", title: "后室铺", left: 7, top: 16, w: 35, h: 22 },
  { id: "undertide-bounty", title: "恩怨墙", left: 40, top: 21, w: 23, h: 18 },
  { id: "undertide-bank", title: "恶猫钱庄", left: 65, top: 16, w: 31, h: 22, sprite: "cat-bank-president", name: "恶猫钱庄行长" },
  { id: "undertide-casino", title: "死人赌场", left: 65, top: 37, w: 31, h: 20, sprite: "silas", name: "Silas" },
  { id: "undertide-medic", title: "晏安医务间", left: 65, top: 58, w: 31, h: 18 },
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
    if (spot.id === "undertide-bank" || spot.id === "undertide-casino") {
      renderUndertideNpc(root, spot);
    } else {
      renderPlace(root, { id: spot.id, title: spot.title });
    }
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
  const bank = spot.id === "undertide-bank";
  root.innerHTML = `
    <div class="island-vn island-undertide-vn is-peek">
      <div class="island-vn-board">
        ${sceneArt(spot.id)}
        <div class="island-vn-stand is-half"><img class="island-vn-sprite" src="/static/island/assets/sprites/${spot.sprite}.png" alt="${esc(spot.name)}" draggable="false"></div>
        <div class="island-vn-talk is-line">
          <button type="button" class="island-vn-box" data-ut-advance><span class="island-vn-name"></span><p class="island-vn-line"></p><i class="island-vn-more" aria-hidden="true"></i></button>
          <div class="island-vn-choices"></div>
        </div>
        <button type="button" class="island-scene-tap">点一下${bank ? "见行长" : "见 Silas"}</button>
      </div>
    </div>
  `;
  const wrap = root.querySelector(".island-undertide-vn");
  const board = wrap.querySelector(".island-vn-board");
  board.addEventListener("click", () => {
    if (wrap.classList.contains("is-peek")) openUndertideNpc(wrap, bank);
  });
}

async function openUndertideNpc(wrap, bank) {
  wrap.classList.remove("is-peek");
  try {
    const snap = await api.undertide();
    paintUndertideTalk(wrap, bank, snap.undertide || {});
  } catch (err) {
    paintUndertideTalk(wrap, bank, {}, err.message || "这会儿不见客。");
  }
}

function paintUndertideTalk(wrap, bank, under, override = "") {
  const talk = wrap.querySelector(".island-vn-talk");
  const name = wrap.querySelector(".island-vn-name");
  const line = wrap.querySelector(".island-vn-line");
  const box = wrap.querySelector("[data-ut-advance]");
  if (!talk || !name || !line || !box) return;
  name.textContent = bank ? "恶猫钱庄行长" : "Silas";
  line.textContent = override || (bank ? under.bank : under.casino) || "这会儿没有可看的。";
  talk.classList.add("is-line");
  talk.classList.remove("is-picks");
  box.onclick = () => paintUndertideChoices(wrap, bank, under);
}

function paintUndertideChoices(wrap, bank, under, mode = "main") {
  const talk = wrap.querySelector(".island-vn-talk");
  const list = wrap.querySelector(".island-vn-choices");
  if (!talk || !list) return;
  talk.classList.remove("is-line");
  talk.classList.add("is-picks");
  const rows = deskChoices(bank, under, mode);
  list.innerHTML = rows.map((row) => `<button type="button" class="island-vn-choice" data-ut-kind="${esc(row.kind)}" data-ut-target="${esc(row.target || "")}"><b>${esc(row.label)}</b>${row.note ? `<small>${esc(row.note)}</small>` : ""}</button>`).join("");
  list.querySelectorAll("[data-ut-kind]").forEach((btn) => btn.addEventListener("click", () => chooseDeskAction(
    btn.getAttribute("data-ut-kind"), btn.getAttribute("data-ut-target") || "", bank, wrap, under,
  )));
}

function deskChoices(bank, under, mode) {
  if (bank) return [
    { kind: "bank_debt", label: "查账" }, { kind: "bank_borrow", label: "借票" }, { kind: "bank_repay", target: "ask", label: "还款" },
    { kind: "bank_save", label: "存钱" }, { kind: "bank_take", target: "ask", label: "取钱" },
  ];
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

function chooseDeskAction(kind, target, bank, wrap, under) {
  if (kind === "menu") return paintUndertideChoices(wrap, bank, under, target);
  if (kind === "bank_debt" || kind === "casino_desk") return runDeskAction(kind, "", bank, wrap);
  if (kind === "bank_save" || kind === "bank_borrow") return askAmount(kind, "票数", bank, wrap);
  if (kind === "bank_take" || kind === "bank_repay") {
    if (target === "ask") return askAmount(kind, "票数（填 all 可全部）", bank, wrap, "", true);
  }
  if (kind === "casino_dice") return askAmount(kind, "下注票数", bank, wrap, target);
  if (kind === "casino_lantern") return target === "start" ? askAmount(kind, "下注票数", bank, wrap) : runDeskAction(kind, target, bank, wrap);
  if (kind === "casino_draw") {
    return showFormSheet({ title: "死人抽牌", body: "填下注和停牌点（12 到 20），这一把一次结算。", fields: [{ id: "bet", label: "下注票数", placeholder: "10" }, { id: "stand", label: "停牌点", placeholder: "17" }], confirm: "发牌", onConfirm: (values) => runDeskAction(kind, `${values.bet} ${values.stand}`, bank, wrap) });
  }
}

function askAmount(kind, label, bank, wrap, prefix = "", allowAll = false) {
  showFormSheet({
    title: label,
    body: allowAll ? "填正整数，或填 all 一次结清。实际限额和余额由柜台当场核。" : "只收正整数；实际限额和余额由柜台当场核。",
    fields: [{ id: "amount", label, placeholder: "10" }],
    confirm: "交给柜台",
    onConfirm: (values) => runDeskAction(kind, prefix ? `${prefix} ${values.amount}` : values.amount, bank, wrap),
  });
}

async function runDeskAction(kind, target, bank, wrap) {
  try {
    const snap = await api.undertideAct(kind, target);
    const event = snap.event || {};
    if (!wrap || !wrap.isConnected) return;
    paintUndertideTalk(wrap, bank, snap.undertide || {}, event.narrative || "这一下结清了。");
  } catch (err) {
    toast(err.message || "这一下没做成。");
  }
}

function hotMarkup(spot) {
  const style = `left:${spot.left}%;top:${spot.top}%;width:${spot.w}%;height:${spot.h}%`;
  return `<button type="button" class="island-hot" data-undertide-place="${spot.id}" style="${style}" aria-label="${spot.title}"></button>`;
}
