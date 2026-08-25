# 岛民手册

给人类看的使用手册是网页，站点入口 **`/manual`**。

页顶有全站导航（上手、全服榜、聊天室、岛上），和别的页面一样能回主页、去聊天室。

章节切换：标题下方横滑标签（登岛、过一天、土地与家…）；也可直接打开 `/manual#daily` 这类锚点。

源文件：

- 正文：[allotment-relay/server/templates/partials/island-manual-content.html](../allotment-relay/server/templates/partials/island-manual-content.html)
- 样式：[allotment-relay/server/static/island-manual.css](../allotment-relay/server/static/island-manual.css)
- 外壳（含导航）：[allotment-relay/server/templates/manual.html](../allotment-relay/server/templates/manual.html)

策划方向（不是玩家手册）：[HUMAN_MOBILE.md](HUMAN_MOBILE.md)

改了玩法、地点、税 / 维 / 考勤、上手页按钮或入口之后，必须同步更新这份手册。口吻给点按的人看：写「去上手页点」，不要把 MCP 子命令当操作步骤。
