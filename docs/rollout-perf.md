# 性能改造上线步骤

这一批改动：纪事 / 集市索引、旧送礼补收礼人（一次性迁移 `gift_target_backfill_v1`）、任务目录请求路径不再写、
同一请求内复用数据库连接、数据库锁加等待超时和占锁时长日志、AI / 图片 / 文件这类慢事挪出锁外。
不改玩法，MCP 工具说明和人类手册不用动。

下面所有耗时都是在本仓库造的 L 档数据（300 名岛民、36 万条纪事、18 万条聊天、库 47 MB）上量的，
线上库多大请先看第 0 步的行数，再按比例估。

## 0. 部署前：看规模、备份

```bash
docker exec <容器名> python -c "import sqlite3; c=sqlite3.connect('/app/server/data/relay.db'); print({t: c.execute(f'select count(*) from {t}').fetchone()[0] for t in ('stewards','chronicle','lounge_messages','market_listings')})"
```

**备份库（在线备份，不用停服，WAL 里没落盘的写入也在里面）。** 不要直接拷贝 `relay.db` 一个文件：服务开着的时候，一部分数据还在 `relay.db-wal` 里。

```bash
docker exec <容器名> python -c "import sqlite3; s=sqlite3.connect('/app/server/data/relay.db'); d=sqlite3.connect('/app/server/data/relay.pre-perf.bak'); s.backup(d); d.close(); print('备份完成')"
```

```bash
docker exec <容器名> python -c "import sqlite3; c=sqlite3.connect('/app/server/data/relay.pre-perf.bak'); print(c.execute('pragma integrity_check').fetchone()[0])"
```

第二条必须输出 `ok`。然后把备份拷出卷（`tidal-data` 卷只在这台机器上，卷里的备份不算备份）：

```bash
mkdir -p ~/backups && docker cp <容器名>:/app/server/data/relay.pre-perf.bak ~/backups/relay-$(date +%F-%H%M).db
```

表情包文件在同一个卷的 `lounge_stickers/` 目录，库之外，顺手备一份：

```bash
docker run --rm -v tidal-data:/data -v ~/backups:/backup alpine tar czf /backup/stickers-$(date +%F-%H%M).tgz -C /data lounge_stickers
```

参考耗时：76 MB 的库在线备份 0.4 秒。

**磁盘余量：** 新索引大约是纪事表本身的 1.4 倍（L 档：纪事表 20 MB，索引共约 28 MB）；建索引时 WAL 也会涨。卷里至少留出库大小的一倍空闲。

## 1. 部署

照常在 Coolify 重新部署。启动时 `init_db` 会依次做：

1. `CREATE INDEX IF NOT EXISTS`：纪事 4 条、集市 2 条（只有第一次启动真的要建）。
2. 一次性迁移 `gift_target_backfill_v1`：把早期漏写收礼人的送礼纪事补上，补完写标记，以后不再扫。
3. 刷新任务目录（`tale_catalog`）。

服务在 `init_db` 跑完之前不接请求，这段时间就是升级造成的停服时间。

| 场景 | 实测（L 档，沙箱） |
|---|---|
| 旧库第一次启动 | 约 2～3.2 秒（其中建纪事索引约 1.3 秒） |
| 之后每次启动 | 约 0.5 秒 |
| 迁移最坏情形：5 万条漏写送礼纪事 × 300 名岛民 | 约 0.7 秒 |

**按线上规模估：** 建索引时间大致和纪事行数成正比（约每 10 万条 0.4 秒）。线上纪事如果到了几百万条，首次启动要十几秒到几十秒，
会超过 Dockerfile 里 `HEALTHCHECK --start-period=15s`：健康检查前几次失败是正常的（`retries=3`、间隔 30 秒，能撑 90 秒），
但 Coolify 如果设了更短的"部署健康等待"，就把它临时调长，或者让它在低峰期部署。
如果 Coolify 是滚动更新（新旧容器同时挂着卷），旧容器在建索引的那几秒写库会排队，最长等到建完，不影响数据正确性。

## 2. 部署后：怎么确认成功

看启动日志，应当有：

```
一次性迁移完成 迁移=旧送礼补收礼人 标记=gift_target_backfill_v1 处理=N 条
```

N 是补了多少条旧纪事（可能是 0）。再看库：

```bash
docker exec <容器名> python -c "import sqlite3; c=sqlite3.connect('/app/server/data/relay.db'); print(c.execute(\"select flag_key, detail from world_flags where flag_key='gift_target_backfill_v1'\").fetchall()); print([r[1] for r in c.execute('pragma index_list(chronicle)') if r[1].startswith('idx_chronicle_')])"
```

应当看到那条标记和 4 个 `idx_chronicle_*` 索引。打开 `/island`、`/play` 进一遍，页面应当明显比之前快。

**以后盯这几条日志**（本次新增，下周一结算后看一眼就知道真实情况）：

| 日志关键字 | 含义 |
|---|---|
| `数据库锁占用过久 路由=… 占用=…s` | 一次请求占着库超过 2 秒。路由就是谁占的。周一岸税 / 岸维开单预期会出现一两条 |
| `等数据库锁偏久 路由=… 等了=…s` | 排队超过 2 秒才拿到锁，后面写着前一个占锁的是谁 |
| `等数据库锁超时 … 当前占锁者=… 已占=…s` | 排队超过上限（默认 20 秒）。玩家会收到 503 和"数据库正忙，等 10～30 秒再发"，MCP 侧收到同一句话 |

两个阈值用环境变量调：`DB_LOCK_HOLD_WARN_SECONDS`（默认 2）、`DB_LOCK_WAIT_TIMEOUT_SECONDS`（默认 20）。

## 3. 出问题怎么回滚

### A. 只回滚代码（先做这个，大多数情况够用）

在 Coolify 里把应用回到上一个已部署的版本（或重新部署 `main` 上本批合并之前的提交）。

**已演练：旧代码可以直接跑在升级后的库上。** 新增的东西都是追加的：索引旧代码用不到但无害；
`gift_target_backfill_v1` 只是 `world_flags` 里多一行，旧代码不认识就忽略；补上的 `target_id` 是对的数据；
任务目录条数没变。旧代码会照旧在每次打开收礼箱时跑那条补救 UPDATE，只是慢一点。
所以代码回滚**不需要**恢复数据库，也不会丢任何玩家进度。

### B. 连库一起恢复（库损坏、数据不对时才用，会丢掉备份之后的所有进度）

1. 停应用容器（Coolify 里 Stop）。**必须先停**，否则恢复时服务还在写库。
2. 把备份放回卷，并清掉旧的 WAL / SHM（它们属于旧库，留着会让 SQLite 把旧日志套在新文件上）：

```bash
docker run --rm -v tidal-data:/data -v ~/backups:/backup alpine sh -c "rm -f /data/relay.db-wal /data/relay.db-shm && cp /backup/relay-<备份时间>.db /data/relay.db"
```

3. 部署**旧版本代码**（见 A），启动。
4. `GET /health` 返回 ok，再进 `/island` 看一眼。
5. 备份之后到现在的玩家操作会丢，部署前在潮生会张贴一条说明比事后补偿省事。

恢复表情包（只在目录被误删时）：

```bash
docker run --rm -v tidal-data:/data -v ~/backups:/backup alpine tar xzf /backup/stickers-<备份时间>.tgz -C /data
```
