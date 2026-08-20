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

滨海酒吧后院的枯井下面还有一层。单 MCP 入口 `undertide_ops`，规则与场所见仓库根 [README — 潮下](../README.md#潮下-undertide-undertide_ops地下世界)。管理面板 `/ut-owner` · `/ut-gate` · `/lizhi` 需环境变量钥匙，未设置时安全禁用。
