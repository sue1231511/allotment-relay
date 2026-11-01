import { api } from "../api.js?v=mod-unify1";
import { state } from "../store.js?v=island-modulefix2";
import { openDesk } from "./desk.js?v=home1";

/** 田间管理：肥力、留种、稻草人、监控、砍树腾地、采集、意外记录。都是 plot_ops 已有的子命令。 */
function plotOptions({ treesOnly = false } = {}) {
  const farm = state.farm || {};
  const rows = [];
  [["home", "菜地"], ["orchard", "果园"], ["greenhouse", "温室"]].forEach(([key, label]) => {
    (farm[key] || []).forEach((p) => {
      if (treesOnly && key === "home") return;
      if (p.state === "clearing" || p.state === "empty") return;
      rows.push({ id: String(p.token || p.slot), label: `${label} ${p.token || p.slot} · ${p.name || "空"}` });
    });
  });
  return rows;
}

const slotAsk = (title, body) => ({ title, body, fields: [{ id: "slot", label: "地块", placeholder: "1" }], confirm: "确认", build: (v) => v.slot });

export function openField({ onBack } = {}) {
  openDesk({
    title: "田间管理",
    onBack,
    backLabel: "回到份地",
    run: (kind, target) => api.fieldAct(kind, target),
    pickers: { plot: () => plotOptions(), tree: () => plotOptions({ treesOnly: true }) },
    tabs: [
      {
        key: "soil",
        label: "土与种",
        rows: () => [
          { label: "看肥力", note: "肥力和轮作", kind: "soil" },
          { label: "种子血统", note: "已经留过的种", kind: "seed_list" },
          { label: "留种", note: "耗 1 份收成换 1 份种，记一代", kind: "seed_keep", ask: { title: "留种", body: "写要留种的作物名（果树不行）。", fields: [{ id: "crop", label: "作物", placeholder: "甘蓝" }], confirm: "留种", build: (v) => v.crop } },
          { label: "采集", note: "不选地块就全部能采的", kind: "gather" },
          { label: "觅食", kind: "forage" },
        ],
      },
      {
        key: "guard",
        label: "看地",
        rows: () => [
          { label: "扎稻草人", kind: "scarecrow", pick: "plot", pickBody: "挡鸟啄，选一块地。" },
          { label: "装监控", note: "15 票，记录偷菜、提高抓贼概率", kind: "camera_install", pick: "plot" },
          { label: "拆监控", kind: "camera_remove", pick: "plot" },
          { label: "看监控记录", kind: "camera_check" },
          { label: "意外记录", note: "最近 20 条", kind: "incident_history" },
          { label: "砍树腾地", note: "不可恢复", kind: "chop", pick: "tree", confirm: "这棵树砍了就没了，地腾出来重新种。确定？" },
        ],
      },
    ],
  });
}
