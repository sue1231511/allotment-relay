import { layoutCoverBoard, sceneArt } from "../ui/art.js?v=undertide-scenes1";
import { renderPlace } from "./place.js?v=undertide-scenes1";
import { api } from "../api.js?v=undertide-scenes1";
import { esc, showFormSheet, showHintSheet, showPickSheet, toast } from "../ui/modal.js?v=undertide-scenes1";

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
    renderPlace(root, { id: spot.id, title: spot.title });
    if (typeof onDetailChange === "function") onDetailChange(true, showMap);
    if (spot.sprite) {
      root.querySelector(".island-place").insertAdjacentHTML("beforeend", `
        <div class="island-undertide-sprite">
          <img src="/static/island/assets/sprites/${spot.sprite}.png" alt="${spot.name}" draggable="false">
        </div>
      `);
    }
    if (spot.id === "undertide-bank" || spot.id === "undertide-casino") {
      paintUndertideDesk(root, spot);
    }
  };

  showMap();
  const bar = document.getElementById("island-actionbar");
  if (bar) {
    bar.innerHTML = "";
    bar.hidden = true;
  }
}

async function paintUndertideDesk(root, spot) {
  const place = root.querySelector(".island-place");
  if (!place) return;
  place.insertAdjacentHTML("beforeend", `
    <section class="island-undertide-control" aria-live="polite">
      <b>${spot.id === "undertide-bank" ? "恶猫钱庄 · 账本" : "死人赌场 · 赌桌"}</b>
      <p>账本正在翻页……</p>
    </section>
  `);
  const panel = place.querySelector(".island-undertide-control");
  try {
    const snap = await api.undertide();
    if (!panel || !panel.isConnected) return;
    const under = snap.undertide || {};
    const bank = spot.id === "undertide-bank";
    const text = bank ? under.bank : under.casino;
    panel.innerHTML = `
      <b>${bank ? "恶猫钱庄 · 账本" : "死人赌场 · 赌桌"}</b>
      <p class="island-undertide-copy">${esc(text || "这会儿没有可看的。")}</p>
      <div class="island-undertide-actions">${bank ? bankActions() : casinoActions(Boolean(under.casino_open))}</div>
    `;
    bindDeskActions(panel, bank);
  } catch (err) {
    if (panel && panel.isConnected) panel.innerHTML = `<b>${esc(spot.title)}</b><p>${esc(err.message || "账本没翻开。")}</p>`;
  }
}

function bankActions() {
  return `
    <button type="button" class="island-btn primary" data-ut="bank_debt">查账</button>
    <button type="button" class="island-btn" data-ut="bank_borrow">借票</button>
    <button type="button" class="island-btn" data-ut="bank_repay">还款</button>
    <button type="button" class="island-btn" data-ut="bank_save">存钱</button>
    <button type="button" class="island-btn" data-ut="bank_take">取钱</button>
  `;
}

function casinoActions(open) {
  if (!open) return `<button type="button" class="island-btn primary" data-ut="casino_desk">看门牌</button>`;
  return `
    <button type="button" class="island-btn primary" data-ut="casino_desk">看赌桌</button>
    <button type="button" class="island-btn" data-ut="casino_dice">黑潮骰</button>
    <button type="button" class="island-btn" data-ut="casino_lantern">最后一盏灯</button>
    <button type="button" class="island-btn" data-ut="casino_draw">死人抽牌</button>
  `;
}

function bindDeskActions(panel, bank) {
  panel.querySelectorAll("[data-ut]").forEach((btn) => {
    btn.addEventListener("click", () => chooseDeskAction(btn.getAttribute("data-ut"), bank, panel));
  });
}

function chooseDeskAction(kind, bank, panel) {
  if (kind === "bank_debt" || kind === "casino_desk") return runDeskAction(kind, "", bank, panel);
  if (kind === "bank_save" || kind === "bank_borrow") return askAmount(kind, "票数", bank, panel);
  if (kind === "bank_take" || kind === "bank_repay") {
    return showPickSheet({
      title: kind === "bank_take" ? "取多少" : "还多少",
      body: "也可以手填具体票数。",
      options: [{ id: "all", label: "全部" }, { id: "custom", label: "手填票数" }],
      onConfirm: (value) => value === "all" ? runDeskAction(kind, "all", bank, panel) : askAmount(kind, "票数", bank, panel),
    });
  }
  if (kind === "casino_dice") {
    return showPickSheet({
      title: "黑潮骰",
      body: "小 / 大 赔率 ×2；黑潮（对子）×5。",
      options: [{ id: "small", label: "押小（×2）" }, { id: "big", label: "押大（×2）" }, { id: "black", label: "押黑潮（×5）" }],
      onConfirm: (choice) => askAmount(kind, "下注票数", bank, panel, choice),
    });
  }
  if (kind === "casino_lantern") {
    return showPickSheet({
      title: "最后一盏灯",
      body: "续灯会继续往上走，也可能直接熄灭。",
      options: [{ id: "start", label: "开一局" }, { id: "continue", label: "继续" }, { id: "cash", label: "收手" }],
      onConfirm: (value) => value === "start" ? askAmount(kind, "下注票数", bank, panel) : runDeskAction(kind, value, bank, panel),
    });
  }
  if (kind === "casino_draw") {
    return showFormSheet({
      title: "死人抽牌",
      body: "填下注和停牌点（12 到 20），这一把一次结算。",
      fields: [{ id: "bet", label: "下注票数", placeholder: "10" }, { id: "stand", label: "停牌点", placeholder: "17" }],
      confirm: "发牌",
      onConfirm: (values) => runDeskAction(kind, `${values.bet} ${values.stand}`, bank, panel),
    });
  }
}

function askAmount(kind, label, bank, panel, prefix = "") {
  showFormSheet({
    title: label,
    body: "只收正整数；实际限额和余额由柜台当场核。",
    fields: [{ id: "amount", label, placeholder: "10" }],
    confirm: "交给柜台",
    onConfirm: (values) => runDeskAction(kind, prefix ? `${prefix} ${values.amount}` : values.amount, bank, panel),
  });
}

async function runDeskAction(kind, target, bank, panel) {
  try {
    const snap = await api.undertideAct(kind, target);
    const event = snap.event || {};
    showHintSheet({ title: event.title || (bank ? "恶猫钱庄" : "死人赌场"), body: event.narrative || "这一下结清了。" });
    if (!panel || !panel.isConnected) return;
    const under = snap.undertide || {};
    const text = bank ? under.bank : under.casino;
    panel.querySelector(".island-undertide-copy").textContent = text || "这会儿没有可看的。";
  } catch (err) {
    toast(err.message || "这一下没做成。")
  }
}

function hotMarkup(spot) {
  const style = `left:${spot.left}%;top:${spot.top}%;width:${spot.w}%;height:${spot.h}%`;
  return `<button type="button" class="island-hot" data-undertide-place="${spot.id}" style="${style}" aria-label="${spot.title}"></button>`;
}
