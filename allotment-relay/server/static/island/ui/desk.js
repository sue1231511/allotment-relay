import { esc, showActSheet, showFormSheet, showPickSheet, toast } from "./modal.js?v=mod-unify1";
import { setPanel, showPanel } from "./panel.js?v=story1";

/**
 * 面板里的「柜台」：几个页签，每个页签一排按钮。点按钮 → 选人 / 选地块 / 填表 / 确认 → 调接口 → 显示结果文字。
 * 邻居与互助、田间管理共用。每一行只描述「点了会发哪个 kind、要问什么」，不在前端拼游戏指令。
 *
 * row: { label, note?, kind, pick?: "neighbor"|"plot"|"tree"|"boat", ask?: { title, body, fields, build(vals, picked) },
 *        confirm?, target? }
 */
export function openDesk({ title, tabs, run, pickers = {}, loader, onBack, backLabel = "回上一页" }) {
  let tab = tabs[0].key;
  let data = null;
  const root = showPanel({ title, html: `<p class="island-fine">翻开…</p>` });
  if (!root) return;

  const rowsOf = () => (tabs.find((t) => t.key === tab)?.rows(data) || []);

  const paint = () => {
    const rows = rowsOf();
    const tabBar = tabs.length > 1
      ? `<div class="island-panel-tabs" role="tablist">${tabs.map((t) => `<button type="button" role="tab" class="island-panel-tab${t.key === tab ? " is-on" : ""}" data-tab="${esc(t.key)}" aria-selected="${t.key === tab}">${esc(t.label)}</button>`).join("")}</div>`
      : "";
    const extra = tabs.find((t) => t.key === tab)?.header?.(data) || "";
    const body = setPanel({
      title,
      html: `${tabBar}${extra}<div class="island-panel-grid">${rows.map((r, i) => `<button type="button" class="island-panel-tile" data-row="${i}"><b>${esc(r.label)}</b>${r.note ? `<small>${esc(r.note)}</small>` : ""}</button>`).join("")}</div>${onBack ? `<button type="button" class="island-btn wide" data-desk-back>${esc(backLabel)}</button>` : ""}`,
    });
    if (!body) return;
    body.querySelectorAll("[data-tab]").forEach((b) => b.addEventListener("click", () => { tab = b.getAttribute("data-tab"); paint(); }));
    body.querySelectorAll("[data-row]").forEach((b) => b.addEventListener("click", () => start(rows[Number(b.getAttribute("data-row"))])));
    const back = body.querySelector("[data-desk-back]");
    if (back) back.addEventListener("click", onBack);
    body.querySelectorAll("[data-person]").forEach((b) => b.addEventListener("click", () => {
      const row = (tabs.find((t) => t.key === tab)?.personRows?.(data, b.getAttribute("data-person"))) || [];
      pickAction(b.getAttribute("data-person"), row);
    }));
  };

  const result = (heading, text) => {
    const body = setPanel({
      title,
      html: `<article class="island-panel-item"><b>${esc(heading)}</b><p class="island-panel-text">${esc(text)}</p></article><button type="button" class="island-btn wide" data-back>回到这一栏</button>`,
    });
    if (body) body.querySelector("[data-back]").addEventListener("click", async () => { await refresh(); paint(); });
  };

  const send = async (row, target) => {
    try {
      const snap = await run(row.kind, target);
      data = loader ? { ...data, ...(await loader(snap)) } : data;
      result(row.label, snap.event?.narrative || "办好了。");
    } catch (err) {
      console.error("[desk] 动作失败", row.kind, target, err);
      toast(err.message || "这一下没做成。");
    }
  };

  const withForm = (row, picked) => {
    const finish = (target) => {
      if (row.confirm) {
        showActSheet({ title: row.label, body: row.confirm, confirm: "确认", onConfirm: () => send(row, target) });
      } else {
        send(row, target);
      }
    };
    if (row.ask) {
      showFormSheet({
        title: row.ask.title || row.label,
        body: row.ask.body || "",
        fields: row.ask.fields,
        confirm: row.ask.confirm || "确认",
        onConfirm: (vals) => finish(row.ask.build(vals, picked)),
      });
    } else {
      finish(row.pick ? picked : (row.target ?? ""));
    }
  };

  function start(row) {
    if (!row) return;
    if (row.pick) {
      const options = (pickers[row.pick]?.(data) || []);
      if (!options.length) {
        toast(row.pick === "neighbor" ? "岛上还没有别的岛民。" : "没有可选的。");
        return;
      }
      showPickSheet({
        title: row.label,
        body: row.pickBody || "",
        options,
        onConfirm: (picked) => withForm(row, picked),
      });
      return;
    }
    withForm(row, "");
  }

  function pickAction(person, rows) {
    if (!rows.length) return;
    showPickSheet({
      title: person,
      body: "对 TA 做什么？",
      options: rows.map((r, i) => ({ id: String(i), label: r.label })),
      onConfirm: (i) => {
        const row = rows[Number(i)];
        if (row) withForm(row, person);
      },
    });
  }

  async function refresh() {
    if (!loader) return;
    try {
      data = await loader();
    } catch (err) {
      console.error("[desk] 读取失败", err);
      toast(err.message || "这会儿读不到。");
    }
  }

  (async () => {
    await refresh();
    paint();
  })();
}
