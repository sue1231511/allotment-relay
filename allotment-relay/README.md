# 潮汐岛（服务端）

完整说明在仓库根目录 **[../README.md](../README.md)**。玩法以游戏内 `relay_manual` 和各工具 `help` 为准。

```bash
pip install -r requirements.txt
python run.py
```

http://127.0.0.1:8787/ · MCP `http://127.0.0.1:8787/mcp/?api_key=ar_sk_...`

人类页面：`/steward` 填专属凭证查看管家状态、影信（本机浏览器会记住，可一键清除）。

入门：`steward_ops enroll 名字` → `relay_manual`。

## 推送前 / 改完后（必做）

细则写在根目录 README 的对应章节。这里只强调两条，不许跳过：

1. **推送之前**必须 `git fetch origin` 并 `git merge origin/main`，确认云端没有你本地没有的提交，再推功能分支。禁止不拉云端就推、禁止 force 推 `main`、禁止用整文件覆盖刚合进来的改动。
2. **每次改玩法之后**必须同步更新：`server/mcp_app.py` 的工具描述、`game.py` 的 `relay_manual`、各工具 `help`。每个工具都要写清用途、空 command 默认、可复制的例子。没更新工具说明，任务不算完。
