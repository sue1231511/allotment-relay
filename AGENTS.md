# 给改这个仓库的 Agent

先读根目录 [README.md](README.md)。下面三条是硬规则，每次任务都要执行。

## 1. 推送之前必须先合云端

多人 / 多云端 Agent 会同时改这个仓库。不拉就推，会覆盖别人的提交。

推送前：

```bash
git fetch origin
git fetch origin main
git log --oneline HEAD..origin/main
```

`HEAD..origin/main` 有提交就必须：

```bash
git merge origin/main
```

冲突时两边的改动都要留（尤其是 `db.py` 迁移、MCP 工具表、`relay_manual`）。不要 `--force` 推 `main`。不要不 fetch 就 push。

开新分支前也要从最新的 `origin/main` 拉起。

## 2. 每次任务之后必须更新工具说明和教程

AI 玩家只看 MCP `description`、`relay_manual`、各工具 `help`。写糊了或漏了，模型会发明指令。

改了任何玩法 / 子命令 / 规则之后，必须同步：

- `allotment-relay/server/mcp_app.py` — 工具 `description` 和 `command` 的 Field 说明
- `allotment-relay/server/game.py` 的 `relay_manual()`
- 对应的 `*_HELP` / `help` 文本
- 必要时根目录 README 的工具表

每一个工具都必须描述清楚：干什么、空 command 是什么、2～3 条能直接复制的 command、容易和别的工具搞混的点。新指令四处都要出现；删掉的指令四处都要删。

没更新这些，任务不算做完，也不许推送。

## 3. 改玩法后必须同步人类使用手册

人类玩家不读 MCP。他们看站点 `/manual`，源文件是 `allotment-relay/docs/island-manual.html`（根目录 `docs/island-manual.md` 只是指路）。

改了任何玩法 / 地点 / 税 / 维 / 考勤 / 上手页按钮 / 入口之后，必须把人类手册改到和游戏一致：

- `allotment-relay/docs/island-manual.html` — 给点按的人看。写清干什么、去哪点、和别的系统容易搞混的地方
- 必要时根目录 README「人类怎么进」的路径表

口吻给人类：写「去上手页点」，不要把 MCP 子命令当操作步骤。新规则四处都要出现；删掉的玩法四处都要删。

没更新人类手册，任务同样不算做完，也不许推送。
