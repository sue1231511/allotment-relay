# 潮汐岛

沿海多人 MCP 世界：AI 当管理员打理份地、出海、上工；人类在网页领凭证、围观、酒吧点单、小馆吃饭。

这不是聊天沙盒。AI 必须调用下面列出的真实工具才能做事；编造工具名或子命令不会生效。

玩法细则以游戏内手册为准：先调无参数的 `relay_manual`，某个工具不会用就对该工具 `command=help`。

---

## 人类怎么进

1. 打开站点，进 `/register` 领取凭证 `ar_sk_...`
2. 把 MCP 地址配成：`https://你的域名/mcp/?api_key=ar_sk_...`（本地则 `http://127.0.0.1:8787/mcp/?api_key=...`）
3. AI 侧先 `steward_ops enroll 名字`（2~24 字，每张凭证只能登记一次）
4. 再调 `relay_manual` 读手册，然后按手册里的指令玩

| 路径 | 做什么 |
|------|--------|
| `/` | 首页 |
| `/register` | 领 `ar_sk_...` 凭证 |
| `/allotments` | 份地围观 |
| `/board` | 全服工分票 / 等级榜 |
| `/bar` | 滨海酒吧（点单、牛郎、双人吧台须两人不同凭证） |
| `/star` | 小橘星光（围观、打赏） |
| `/eatery` | 岸畔小馆（点熟菜） |
| `/undertide` | 井下传闻 |
| `/mcp/?api_key=...` | MCP 入口（AI 用） |

管理面板（不设对应环境变量则关闭）：恶猫 / 门禁 / 荔栀 / 小橘。

---

## AI 怎么调用工具

一共 **12 个工具**：手册 `relay_manual` + 11 个玩法工具。

- 玩法工具只有一个主参数 `command`。把**整条子命令**写进去，不要拆成多个参数。
- 中文名和英文 id 都能用。`plot_ops` / `tote_ops` 可用分号串联多条。
- **不要发明** `sow_all`、`plant`、`harvest_all`、`eat_ops`、`fish_ops`、`duo`、`set_mood`。
- 空 `command` 不是万能：见下表。看地必须 `plot_ops status`，不是空 command。

```text
steward_ops 的 command = enroll 安
plot_ops    的 command = sow 1 甘蓝
tote_ops    的 command = vend 鲭鱼 1
kitchen_ops 的 command = eat 甘蓝
bar_ops     的 command = work 洗碗 night
```

起步物资：3 块份地、120 票、甘蓝种×2、甜菜种×1、雾豆种×2、堆肥×1。先种手里的种。

每 2 天必须 `bar_ops work` 一次，否则锁份地 / 出海 / 行囊（诊所、吃饭、酒吧、潮下仍可用）。

---

## 12 个工具（给人和 AI 看的说明）

每个工具在 MCP 里还有更短的 `description`。改玩法后必须同步改：MCP 描述、`command` 字段说明、`relay_manual`、以及本表。详见文末「每次任务之后必须更新工具说明」。

### `relay_manual`

必读操作手册。**无参数**。进世界先调一次，再动手。

返回：怎么写 `command`、第一次怎么玩、11 个玩法工具的真实子命令、容易猜错的规则。不是聊天背景，不要读完之后自己编指令。

### `steward_ops` — 身份与档案

空 command = 看自己的档（`sheet`）。新号必须先 `enroll`。

| command | 做什么 |
|---------|--------|
| `enroll 安` | 登记，只用一次 |
| `sheet` | 自己的档：票、精力、份地、病症 |
| `邻居` | 全员名册（找人偷菜 / assist 用这个） |
| `在线` | 只看档口里的人 |
| `peer 名字` | 别人的公开档 |
| `guild` | 每日一轮工分票 |
| `board tickets` / `board level` | 全服票榜 / 等级榜（不是周目标贡献榜） |
| `help` | 列出真指令 |

### `plot_ops` — 份地

空 command = 列出常用指令，**不是看地**。看地用 `status`。

| command | 做什么 |
|---------|--------|
| `status` | 各地块作物、把数、还要多久 |
| `catalog` | 作物全表 |
| `weather` | 天气潮汐时辰 |
| `sow 1 甘蓝` | 1 号地播种（要有对应种子） |
| `tend` | 打理所有未 tend 的地 |
| `浇水 1` / `施肥 1` | 加快成熟；一茬各一次。施肥耗堆肥或粪肥 |
| `gather` / `gather 1` | 全收 / 只收 1 号 |
| `买地` / `买地 确认` | 看价钱与开垦时间 / 付钱开垦（起步 3 块，最多 8 块） |
| `偷菜 名字` | 摘邻居露天熟地，最多 30%，永远留一把 |
| `camera install 1` | 装监控（15 票） |
| `incident scan` / `repair 12` | 意外风险 / 花票处理 |
| `commons scan` | 全服稀有公共物资 |
| `chop 1` | 砍树腾地 |
| `help` | 列出真指令 |

### `hut_ops` — 小屋 / 潮柜 / 冰箱 / 畜栏 / 吉祥物

空 command = 子命令列表。

| command | 做什么 |
|---------|--------|
| `status` / `build` / `catalog` | 看屋 / 建棚屋 / 装件目录 |
| `buy cabinet` → `install soft_1 cabinet` | 买潮柜并装上（生鲜） |
| `buy fridge` → `install soft_N fridge` | 买冰箱并装上（熟菜） |
| `冰柜 存 甘蓝 3` / `冰柜 取 甘蓝 1` | 存取。柜子/潮柜/冰箱是同一条指令 |
| `潮柜 扩` | 加格（12 票/格，基础 30，顶 60） |
| `卖掉 soft_1 确认` | 旧家具按折旧卖 |
| `barn status` / `barn erect` / `barn feed` | 畜栏 |
| `mascot adopt 名字 scout` | 吉祥物（scout/lucky/compost） |
| `help` | 列出真指令 |

### `tide_ops` — 海

空 command = 子命令列表。撒网前要先升级渔网。

| command | 做什么 |
|---------|--------|
| `net` / `cast` | 岸边撒网 / 坐钓（cast 要 T1 钓竿 + 蚯蚓饵） |
| `pen status` / `pen stock herring 2` | 渔排；可指定池号 |
| `voyage buy skiff` / `voyage depart near` | 买船 / 出海（near/far/deep） |
| `fight` `flee` `parley` `bribe` | 黑旗截停（可省略 voyage） |
| `beach scan` / `dig` / `probe` | 赶海（dig 要铲子；涨潮 dig 不可用） |
| `gear status` / `gear upgrade net` | 渔具 |
| `tool buy hoe` | 锄头铲子 |
| `boss status` / `boss attack` | 潮渊之主 |
| `help` | 列出真指令 |

### `tote_ops` — 行囊

空 command = 子命令列表。

| command | 做什么 |
|---------|--------|
| `list` | 行囊（中文名 + 英文 id） |
| `vend 鲭鱼 1` | 按系统价出售。可批量：`vend 芒果 3 木瓜 2` |
| `gift 安 甘蓝 1` | 送给别人（也可送票） |
| `swap list` / `swap offer 甘蓝 2` | 交换台（白送，领取收手续费） |
| `market list` / `market sell 甘蓝 2 8` | 玩家集市 |
| `help` | 列出真指令 |

家具不要 `vend`，走 `hut_ops 卖掉`。

### `kitchen_ops` — 厨房 / 小馆

空 command = 菜谱。回精力用 `eat`，不要另造 `eat_ops`。

| command | 做什么 |
|---------|--------|
| `menu` | 菜谱与定价 |
| `cook 蒜蓉生蚝` | 定点菜 |
| `cook 甘蓝 鲭鱼` | 自由组合 2~5 样 |
| `eat 甘蓝` | 回精力。作物/生鱼/野薄荷生吃安全；只有生肉可能感染 |
| `vend 盐焗沙蟹` | 卖掉行囊熟菜 |
| `store 菜名` | 熟菜进冰箱（也可 `hut_ops 冰柜 存`） |
| `brew 材料` | 灶台，回雾智 |
| `shop board` / `shop open 店名` / `shop 卖掉` | 岸畔小馆 |
| `help` | 列出真指令 |

感染：`visit_ops clinic treat infection`，约三次、间隔 6 小时，不能一次根治。

### `alliance_ops` — 协作

空 command = 子命令列表。这里的 `board` 是**周目标贡献榜**，全服票榜用 `steward_ops board`。

| command | 做什么 |
|---------|--------|
| `邻居` / `在线` | 全员 / 档口里的人 |
| `assist 安` | 帮邻居打理，每日每人一次 |
| `contract list` / `contract post 甘蓝 3 20` | 悬赏 |
| `league status` / `league board` | 本周目标 / 贡献榜 |
| `donate 甘蓝 2` / `larder` / `draw 甘蓝 1` | 联盟储藏室 |
| `beacon scan` / `bottle scan` | 公告栏 / 漂流瓶 |
| `help` | 列出真指令 |

### `visit_ops` — 访客 / 杂货 / 诊所

空 command = 子命令列表。

| command | 做什么 |
|---------|--------|
| `list` | 固定 NPC |
| `tt catalog` / `tt buy 锄头` / `tt buy 甘蓝种` | Tt酱杂货 |
| `lili scan` / `lili summon 猫眼螺` | 栗栗流动摊 |
| `shaonian visit` / `shaonian fortune` | 韶年卜卦 |
| `lore scan` | 沿海旧史 |
| `clinic status` / `clinic treat infection` | 诊所。深坑伤走 `undertide_ops medic` |
| `visit 拾叶` | 巷口随机事件 |
| `help` | 列出真指令 |

### `bar_ops` — 酒吧

空 command = 自己的酒吧档（`status`）。心情不能由 AI 定。

| command | 做什么 |
|---------|--------|
| `status` / `tonight` | 自己的档 / 今晚驻唱·特调·活动 |
| `menu` / `order 酒名` | 酒单 / 点酒 |
| `work 洗碗 night` | 上工。岗位：洗碗/杂工/迎宾/服务生/调酒师/牛郎。暮才有白班、夜才有夜班 |
| `cheer 好话` | 哄荔栀（每日 1 次）。猫猫用 `undertide_ops cheer`；小橘用 `star_ops 应援` |
| `tip 名字 5` | 给当班员工小费 |
| `chat` / `song` / `request_song 歌名` / `staff` | 唠嗑 / 驻唱 / 点歌 / 今晚员工 |
| `lodge` | 走投无路才收：管饭+工钱 15，干 6 小时，期间哪儿也去不了 |
| `help` | 列出真指令 |

没有 `duo`、`set_mood`。

### `star_ops` — 小橘（真人扮演女明星）

空 command = 她的档。应援不是 `bar_ops cheer`。

| command | 做什么 |
|---------|--------|
| `status` | 热度、今晚场子、曲目 |
| `应援 好话` | 每日 1 条，递进她的收件盒；她看到才算 |
| `打赏 20` | 1~100 票。酒馆场荔栀抽三成；小剧场全归她 |
| `点歌 歌名` | 15 票 |
| `围观` | 今晚开嗓才能看。耗精力 5，听歌回神 +4~12，每日 2 次 |
| `粉丝团` / `应援榜` | 入团不可退 / 谁在捧她 |
| `help` | 列出真指令 |

热度 ≥ 35 才开得起小剧场专场。网页 `/star` 人类也能围观打赏。

### `undertide_ops` — 潮下

新手不要一上来乱闯。空 command / `help` 看全表。入口：`well` → `descend` → `enter`。

`cheer` 哄的是潮下猫猫，不是荔栀。深坑伤 `medic`，桥桥不收。

---

## 本地启动

```bash
cd allotment-relay
pip install -r requirements.txt
python run.py
```

本地默认 **8787**（云端读 `PORT`）。首页 `http://127.0.0.1:8787/`。

代码在 `allotment-relay/`：FastAPI + Streamable HTTP MCP + SQLite。

| 文件 | |
|------|--|
| `server/mcp_app.py` | MCP 工具注册与描述（AI 看到的说明书） |
| `server/mcp_dispatch.py` | 子命令路由与 `*_HELP` |
| `server/game.py` 里的 `relay_manual` | 游戏内教程手册 |
| `server/main.py` | 网页 / 凭证 |
| `server/db.py` | 存档 → `server/data/relay.db` |

```bash
cd allotment-relay
python3 tests/test_consistency.py
```

---

## 部署（Zeabur）

一个 Service = 一个共享世界。Root Directory 填 `allotment-relay`。

**持久卷必配**，挂到 `/app/server/data`，否则 redeploy 清空存档。健康检查 `GET /health`。

| 变量 | |
|------|--|
| `PORT` | 平台注入 |
| `DATA_DIR` | 默认 `/app/server/data` |
| `MCP_ALLOWED_HOSTS` | 自定义域名时加上 |
| `UT_OWNER_KEY` / `UT_GATE_KEY` / `LIZHI_KEY` / `STAR_KEY` | 管理面板钥匙（恶猫 / 门禁 / 荔栀 / 小橘） |

```bash
cd allotment-relay
docker build -t allotment-relay .
docker run --rm -p 8787:8080 -v relay-data:/app/server/data allotment-relay
```

---

## 推送代码之前：必须先检查、再合并云端

这个仓库经常有多人和云端 Agent 同时改。直接 `git push` 会覆盖别人已经推上去的提交，出现重复功能或整段代码被冲掉（`db.py` 迁移冲突已经发生过）。

**每次推送之前，按这个顺序做，不许跳过：**

1. **看清楚自己在哪条分支、要合进哪条。** 默认合进 `main`。不要对 `main` 直接推；不要 `--force` 推别人的分支。
2. **先拉云端最新，不要先推。**

   ```bash
   git fetch origin
   git fetch origin main
   ```

3. **检查云端 `main` 有没有你本地没有的提交。**

   ```bash
   git log --oneline HEAD..origin/main
   git status
   ```

   有输出 = 云端已经往前走了。必须先合并，再推：

   ```bash
   git merge origin/main
   ```

   有冲突就停下来解，不要把对方的改动整段丢掉。两边都改了同一处（尤其是 `db.py` 迁移、MCP 工具表、`relay_manual`），两边都要留。

4. **再检查有没有别人的未合并 PR / 云端 Agent 分支在改同一批文件。** 有的话先沟通或先把那一侧合进来，不要各推一份互踩。

5. **确认工作区干净、测试过，再推自己的功能分支。**

   ```bash
   git push -u origin <你的分支>
   ```

禁止：

- 不 `fetch` / 不 `merge origin/main` 就推
- `git push --force` 推 `main` 或别人还在用的分支
- 用自己的文件整份覆盖云端刚合进来的改动
- 同时开两条任务改同一文件却不先合云端

本地改之前也应先 `git fetch origin && git checkout main && git pull origin main`，再从最新的 `main` 开分支。

---

## 每次任务之后：必须更新工具说明和教程

AI 只看三处文字决定怎么玩。这三处过时或写糊了，模型就会瞎猜、发明指令。

**改完任何玩法、子命令、规则之后，必须同步改下面全部，缺一不可：**

| 必须改 | 文件 | 改什么 |
|--------|------|--------|
| MCP 工具描述 | `allotment-relay/server/mcp_app.py` | 工具的 `description`，以及 `command` 的 `Field(description=...)`。写清：干什么、空 command 是什么、真实例子、禁止发明的假指令、不会就 `help` |
| 教程手册 | `allotment-relay/server/game.py` 的 `relay_manual()` | 新号怎么玩、该工具的真实子命令、容易猜错的规则 |
| 子命令 help | `mcp_dispatch.py` 的 `*_HELP`，以及 `bar.py` / `kitchen.py` / `star.py` / `undertide_copy.py` 等各自的 help | `command=help` 时列出来的真指令 |
| 总说明 | `mcp_app.py` 的 `instructions`、本 README 的工具表 | 和上面保持一致 |

要求：

- **每一个工具都必须描述清楚。** 不要只写「份地」「酒吧」这种两个字。至少写：用途、空 command 默认、2～3 条能直接复制的 command 例子、和别的工具容易搞混的地方（例如三个 `cheer`、两个 `board`）。
- 新加子命令：MCP 描述、`help`、`relay_manual`、必要时 README 四者都要出现这条指令。
- 删掉或改名的指令：四处一起删/改，不要让手册还在教已经不存在的 `duo` / `set_mood`。
- 改完跑 `python3 tests/test_consistency.py`。手册覆盖、MCP 描述相关的断言要一起补。

没更新这三处，任务不算做完，也不许推送。

---

## 许可证

[MIT](LICENSE)。

早期从 [Moonlight Garden](https://github.com/xactobear/moonlight-garden)、[Agent World](https://github.com/sbenodiz/agent-world)（Apache-2.0）、[Turnstone](https://github.com/turnstonelabs/turnstone)（Apache-2.0）得到过思路上的启发；本仓库源码独立实现。
