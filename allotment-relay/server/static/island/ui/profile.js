import { api } from "../api.js?v=mod-unify1";
import { esc, showFormSheet, toast } from "./modal.js?v=mod-unify1";
import { setPanel, showPanel } from "./panel.js?v=story1";
import { applySnapshot } from "../store.js?v=island-modulefix2";

/** 「这一号」：点状态木牌打开。文字都是 steward_ops 已有的子命令返回的那一段。 */
const MENU = [
  ["sheet", "档案", "精力、票、病症、欠税欠维"],
  ["bond", "岛缘", "岸上加、井下减"],
  ["titles", "成就与称呼", "看已解锁，佩戴或卸下"],
  ["collection", "收集簿", "点亮的永久保存"],
  ["invite", "引航", "邀请码、邀请链接、绑定"],
  ["choices", "灾选", "坏事多选待决"],
  ["tierlog", "灾档", "近日坏事已结"],
  ["gazette", "本周纪事", "全岛这一周"],
  ["repair", "待办", "要修的、要处置的"],
  ["gifts", "收礼", "收到的礼"],
  ["edit", "改档", "座右铭、肖像、岛民名"],
];

let profile = null;
let afterChange = null;

function textView(title, text) {
  return `<article class="island-panel-item"><b>${esc(title)}</b><p class="island-panel-text">${esc(text)}</p></article>`;
}

const BACK = `<button type="button" class="island-btn wide" data-back>回到这一号</button>`;

function head() {
  const p = profile || {};
  return `<article class="island-panel-item is-head">
    <b>${esc(p.name || "岛民")}</b>
    ${p.motto ? `<p>${esc(p.motto)}</p>` : `<small>还没写座右铭。</small>`}
    ${p.portrait ? `<small>肖像：${esc(p.portrait)}</small>` : ""}
  </article>`;
}

function menuHtml() {
  return `${head()}<div class="island-panel-grid">${MENU.map(([id, label, note]) => `<button type="button" class="island-panel-tile" data-menu="${id}"><b>${esc(label)}</b><small>${esc(note)}</small></button>`).join("")}</div>`;
}

async function refresh() {
  try {
    const snap = await api.profile();
    profile = snap.profile || profile;
    applySnapshot(snap);
    if (typeof afterChange === "function") afterChange();
  } catch (err) {
    console.error("[profile] 读取失败", err);
    toast(err.message || "这一号这会儿翻不开。");
  }
}

async function act(kind, target = "") {
  try {
    const snap = await api.profileAct(kind, target);
    profile = snap.profile || profile;
    applySnapshot(snap);
    if (typeof afterChange === "function") afterChange();
    return snap;
  } catch (err) {
    console.error("[profile] 动作失败", kind, target, err);
    toast(err.message || "这一下没做成。");
    return null;
  }
}

function paintMenu() {
  const body = setPanel({ title: "这一号", html: menuHtml() });
  if (!body) return;
  body.querySelectorAll("[data-menu]").forEach((btn) => btn.addEventListener("click", () => openItem(btn.getAttribute("data-menu"))));
}

function showText(title, text, extra = "") {
  const body = setPanel({ title, html: `${textView(title, text)}${extra}${BACK}` });
  if (!body) return null;
  body.querySelectorAll("[data-back]").forEach((btn) => btn.addEventListener("click", paintMenu));
  return body;
}

async function openItem(id) {
  if (id === "edit") return openEdit();
  if (id === "choices") return openChoices();
  if (id === "invite") return openInvite();
  const kindOf = { sheet: "sheet", bond: "bond", titles: "titles", collection: "collection", tierlog: "tierlog", gazette: "gazette", repair: "repair", gifts: "gifts" };
  const snap = await act(kindOf[id]);
  if (!snap) return null;
  const text = snap.event?.narrative || "";
  if (id === "titles") {
    const body = showText("成就与称呼", text, `<div class="island-panel-row"><button type="button" class="island-btn" data-wear>佩戴称呼</button><button type="button" class="island-btn" data-off>卸下称呼</button></div>`);
    if (!body) return null;
    body.querySelector("[data-wear]").addEventListener("click", () => showFormSheet({
      title: "佩戴称呼", body: "写上面列表里已解锁的称呼名。",
      fields: [{ id: "name", label: "称呼", placeholder: "逾篱客", max: 24 }], confirm: "戴上",
      onConfirm: async (v) => {
        const done = await act("title_wear", v.name);
        if (done) showText("佩戴称呼", done.event?.narrative || "戴上了。");
      },
    }));
    body.querySelector("[data-off]").addEventListener("click", async () => {
      const done = await act("title_off");
      if (done) showText("卸下称呼", done.event?.narrative || "卸下了。");
    });
    return null;
  }
  showText(MENU.find((m) => m[0] === id)?.[1] || "这一号", text);
  return null;
}

async function openInvite() {
  await refresh();
  const inv = profile?.invite || {};
  const lines = [
    `你的邀请码：${inv.code || "—"}`,
    `邀请链接：${inv.link || "—"}`,
    inv.bound ? `你由「${inv.inviter || "某位岛民"}」引来。` : "还没绑过引航人。",
    `你引来 ${inv.invited || 0} 人，计入有效 ${inv.valid_count || 0} 人。`,
    "把码或链接给新岛民。登记或首次绑定后关系就定了，不能改绑；自己不能引自己。",
  ];
  const extra = `<div class="island-panel-row">
      <button type="button" class="island-btn" data-copy>复制邀请链接</button>
      ${inv.can_bind ? `<button type="button" class="island-btn" data-bind>绑定邀请码</button>` : ""}
    </div>`;
  const body = showText("引航", lines.join("\n"), extra);
  if (!body) return;
  body.querySelector("[data-copy]").addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(inv.link || "");
      toast("邀请链接复制好了。");
    } catch (err) {
      console.error("[profile] 复制失败", err);
      toast("这个浏览器不让复制，长按上面的链接自己复制。");
    }
  });
  const bindBtn = body.querySelector("[data-bind]");
  if (bindBtn) {
    bindBtn.addEventListener("click", () => showFormSheet({
      title: "绑定邀请码", body: "只能绑一次，不能改绑。",
      fields: [{ id: "code", label: "邀请码", placeholder: "AB12CD34", max: 16 }], confirm: "绑定",
      onConfirm: async (v) => {
        const done = await act("invite_bind", v.code);
        if (done) showText("引航", done.event?.narrative || "绑好了。");
      },
    }));
  }
}

async function openChoices() {
  await refresh();
  const rows = profile?.choices || [];
  if (!rows.length) {
    showText("灾选", "眼下没有待选的坏事。闹脾气、鱼舱进水、疫病、灶台卡火会记在这里。");
    return;
  }
  const html = rows.map((row) => `<article class="island-panel-item"><b>${esc(row.via)}</b>
      <div class="island-panel-row">${row.opts.map((opt) => `<button type="button" class="island-btn" data-choice="${esc(row.key)} ${esc(opt)}">${esc(opt)}</button>`).join("")}</div></article>`).join("");
  const body = setPanel({ title: "灾选", html: `${html}${BACK}` });
  if (!body) return;
  body.querySelectorAll("[data-back]").forEach((btn) => btn.addEventListener("click", paintMenu));
  body.querySelectorAll("[data-choice]").forEach((btn) => btn.addEventListener("click", async () => {
    const done = await act("choice", btn.getAttribute("data-choice"));
    if (done) showText("灾选", done.event?.narrative || "处置了。");
  }));
}

function openEdit() {
  const p = profile || {};
  const body = setPanel({
    title: "改档",
    html: `${head()}<div class="island-panel-row">
      <button type="button" class="island-btn" data-edit="revise">改座右铭与肖像</button>
      <button type="button" class="island-btn" data-edit="rename">改岛民名</button>
    </div><small class="island-fine">改岛民名只能在这里、上手页点，不进 MCP；模型改不了。</small>${BACK}`,
  });
  if (!body) return;
  body.querySelectorAll("[data-back]").forEach((btn) => btn.addEventListener("click", paintMenu));
  body.querySelector('[data-edit="revise"]').addEventListener("click", () => showFormSheet({
    title: "座右铭与肖像", body: "两样至少写一样，不写的那样不动。",
    fields: [
      { id: "motto", label: "座右铭", placeholder: p.motto || "潮声不断", optional: true, max: 200 },
      { id: "portrait", label: "肖像", placeholder: p.portrait || "戴草帽", optional: true, max: 200 },
    ],
    confirm: "改",
    onConfirm: async (v) => {
      if (!v.motto && !v.portrait) {
        toast("两样至少写一样。");
        return;
      }
      const done = await act("revise", `${v.motto}|${v.portrait}`);
      if (done) showText("改档", done.event?.narrative || "改好了。");
    },
  }));
  body.querySelector('[data-edit="rename"]').addEventListener("click", () => showFormSheet({
    title: "改岛民名", body: "2 到 24 个字，不能和别人重名。",
    fields: [{ id: "name", label: "新名字", placeholder: p.name || "", max: 24 }], confirm: "改名",
    onConfirm: async (v) => {
      const done = await act("rename", v.name);
      if (done) showText("改岛民名", done.event?.narrative || "改好了。");
    },
  }));
}

export async function openProfile({ onChange } = {}) {
  afterChange = onChange || null;
  const body = showPanel({ title: "这一号", html: `<p class="island-fine">翻档案…</p>`, onClose: () => { afterChange = null; } });
  if (!body) return;
  await refresh();
  paintMenu();
}
