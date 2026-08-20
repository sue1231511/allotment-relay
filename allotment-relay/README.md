# 潮汐岛

完整说明在仓库根目录：

**[../README.md](../README.md)**

## 快速启动

```bash
cd allotment-relay
pip install -r requirements.txt
python run.py
```

Zeabur 部署说明见仓库根目录 [README.md](../README.md#zeabur-云端部署)。

命令写法（中文名 / 英文 id、guild 每日一次、意外扣票等）见根目录 README「命令怎么写」。

许可证与外部参考见根目录 [README.md — 参考与致谢](../README.md#参考与致谢)。

- 首页 http://127.0.0.1:8787/
- MCP `http://127.0.0.1:8787/mcp/?api_key=ar_sk_...`

---

## 潮下 Undertide（地下世界）

滨海酒吧后院的枯井下面还有一层。常客自然会发现入口（好酒喝到位，老板娘会讲故事）。

- `undertide_ops` — 单一 MCP 入口（well/descend/enter/status/market/buy/sell/bank/jail/pit/fight/medic/dice/lantern/draw/hijack/street/muscle/push/grudge/tavern/whisper/spy/bounty/kroom/cheer，help 看全表）
- 影信 `shadow_rep` — 地下信用，与档信独立
- 后室铺（真假货）、恶猫钱庄（利率由老板娘猫猫当日定）、地下监牢（偷窃惯犯收监）、深坑角斗、死人抽牌、恩怨墙悬赏、K室
- 管理面板：`/ut-owner`（钱庄）· `/ut-gate`（门规）· `/lizhi`（酒馆氛围）— 需环境变量 `UT_OWNER_KEY` / `UT_GATE_KEY` / `LIZHI_KEY`，未设置时安全禁用
