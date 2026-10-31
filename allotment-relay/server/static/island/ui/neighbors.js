import { api } from "../api.js?v=mod-unify1";
import { esc } from "./modal.js?v=mod-unify1";
import { openDesk } from "./desk.js?v=home1";

/** 邻居与互助：名册 / 互助 / 周目标·合约·储藏室。每个动作都是 alliance、steward、plot 已有的子命令。 */
const BOATS = ["切波艇", "近海帆撬", "漂航船", "延绳船"];

const askQty = (title, body) => ({
  title, body,
  fields: [{ id: "item", label: "物品", placeholder: "甘蓝" }, { id: "qty", label: "数量", placeholder: "1" }],
  confirm: "确认", build: (v) => `${v.item} ${v.qty}`,
});

const askId = (title, body) => ({
  title, body, fields: [{ id: "id", label: "合约编号", placeholder: "1" }], confirm: "确认", build: (v) => v.id,
});

function rosterRows(person) {
  return [
    { label: "看公开档", kind: "peer", target: person },
    { label: "协作度", kind: "rapport", target: person },
    { label: "帮忙打理", kind: "assist", target: person },
    {
      label: "去偷菜", kind: "steal", confirm: `对 ${person} 动手：最多掐走 30%，永远留一把，被抓会罚票、掉档信。要地块就写，不写让游戏挑。`,
      ask: { title: `偷 ${person} 的菜`, body: "地块写数字或 园1、棚1；留空就不指定。", fields: [{ id: "slot", label: "地块（可不写）", placeholder: "1", optional: true }], confirm: "动手", build: (v) => `${person}${v.slot ? ` ${v.slot}` : ""}` },
    },
    { label: "致歉", kind: "amends", target: person },
  ];
}

export function openNeighbors({ onBack } = {}) {
  openDesk({
    title: "邻居与互助",
    onBack,
    backLabel: "回到这一号",
    run: (kind, target) => api.neighborsAct(kind, target),
    loader: async () => (await api.neighbors()).neighbors,
    pickers: {
      neighbor: (d) => (d?.people || []).map((p) => ({ id: p.name, label: `${p.name}${p.home ? " · 在档口" : ""}` })),
      boat: () => BOATS.map((b) => ({ id: b, label: b })),
    },
    tabs: [
      {
        key: "roster",
        label: "名册",
        header: (d) => `<p class="island-fine">全岛 ${esc(String(d?.total ?? "—"))} 位管理员，${esc(String(d?.online ?? 0))} 位在档口（${esc(String(d?.window_min ?? 15))} 分钟内有操作）。点一个名字选要做的事。</p>
          <div class="island-panel-people">${(d?.people || []).map((p) => `<button type="button" class="island-panel-person${p.home ? " is-home" : ""}" data-person="${esc(p.name)}"><b>${esc(p.name)}</b><small>${esc(p.title)} · ${p.ripe ? `熟地 ${esc(String(p.ripe))}` : "暂无熟地"} · 协作 ${esc(String(p.rapport))}</small>${p.motto ? `<small>${esc(p.motto)}</small>` : ""}</button>`).join("") || `<p class="island-fine">岛上还没有别的岛民。</p>`}</div>`,
        personRows: (_d, person) => rosterRows(person),
        rows: () => [],
      },
      {
        key: "link",
        label: "互助",
        rows: () => [
          { label: "借船给邻居", note: "协作 60 起，借 3 日", kind: "loan_give", pick: "neighbor" },
          { label: "借船状态", kind: "loan_status" },
          { label: "合伙买大船", note: "协作 50 起，满 2 人各付一半", kind: "share_open", pick: "boat", pickBody: "切波艇、近海帆撬、漂航船、延绳船。" },
          { label: "入伙", note: "加入某人的合伙船", kind: "share_join", pick: "neighbor" },
          { label: "合伙状态", kind: "share_status" },
          { label: "散伙", kind: "share_end", confirm: "合伙散了，按已付的算。" },
          { label: "托养送出", note: "协作 40 起", kind: "foster_out", pick: "neighbor", ask: { title: "托养送出", body: "写你栏里的栏位号。", fields: [{ id: "slot", label: "栏位", placeholder: "1" }], confirm: "送出", build: (v, who) => `${who} ${v.slot}` } },
          { label: "托养接回", kind: "foster_back", pick: "neighbor", ask: { title: "托养接回", body: "写邻居那边的栏位号。", fields: [{ id: "slot", label: "栏位", placeholder: "1" }], confirm: "接回", build: (v, who) => `${who} ${v.slot}` } },
          { label: "托养列表", kind: "foster_list" },
          { label: "开菜篮", note: "供应方开通", kind: "basket_open" },
          { label: "订菜篮", note: "25 票 / 7 天，协作 30 起", kind: "basket_order", pick: "neighbor" },
          { label: "领菜篮", note: "每日一次", kind: "basket_claim" },
          { label: "订共耕", note: "协作 45 起，14 日", kind: "cofarm_order", pick: "neighbor" },
          { label: "共耕状态", kind: "cofarm_status" },
          { label: "解共耕", kind: "cofarm_end", pick: "neighbor" },
        ],
      },
      {
        key: "league",
        label: "周目标与合约",
        rows: () => [
          { label: "本周目标", note: "东八区周一换班", kind: "league_status" },
          { label: "贡献榜", kind: "league_board" },
          { label: "贡献周目标", kind: "league_contribute", ask: askQty("贡献周目标", "只收本周目标要的那样东西。") },
          { label: "合约列表", kind: "contract_list" },
          { label: "我挂的合约", kind: "contract_mine" },
          { label: "接合约", kind: "contract_take", ask: askId("接合约", "写合约编号。") },
          { label: "交合约", kind: "contract_fill", ask: askId("交合约", "写合约编号，交的货从行囊扣。") },
          { label: "撤合约", kind: "contract_cancel", ask: askId("撤合约", "写你挂的合约编号。") },
          { label: "挂合约", kind: "contract_post", ask: { title: "挂合约", body: "写要的物品、数量和酬票；酬票先押在合约里。", fields: [{ id: "item", label: "物品", placeholder: "石蟹王" }, { id: "qty", label: "数量", placeholder: "1" }, { id: "reward", label: "酬票", placeholder: "40" }], confirm: "挂出", build: (v) => `${v.item} ${v.qty} ${v.reward}` } },
          { label: "挂看护委托", note: "他人接单后每天帮你打理", kind: "contract_post_labor", ask: { title: "挂看护委托", body: "天数和酬票；酬票每天至少有保底。", fields: [{ id: "days", label: "天数", placeholder: "3" }, { id: "reward", label: "酬票", placeholder: "60" }], confirm: "挂出", build: (v) => `${v.days} ${v.reward}` } },
          { label: "看联盟储藏室", kind: "larder_list" },
          { label: "存进储藏室", kind: "larder_donate", ask: askQty("存进储藏室", "存的货联盟都能领。") },
          { label: "从储藏室领", note: "领取 2 票，每日 3 次", kind: "larder_draw", ask: askQty("从储藏室领", "写物品和数量。") },
        ],
      },
    ],
  });
}
