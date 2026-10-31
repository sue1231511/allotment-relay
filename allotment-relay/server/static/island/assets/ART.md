# 手机地图插图位

把图放到同目录 `scenes/{id}.png`，并同步生成同名 `.webp`；现代手机优先读取 WebP，PNG 只留给旧浏览器回退。没有图时显示「插图位」框。

竖屏优先，透明底或铺满都可。建议 **1080×1920**。

| 文件 | 出现在哪 | 建议尺寸 |
|------|----------|----------|
| `scenes/island-map.jpg` | 岛屿总览（已就位；铺满一屏，底下不漏色；小图，进岛不等 3MB） | 972×1619 |
| `scenes/undertide-map.png` | 井下总览（已标注：井下入口、后室铺、恩怨墙、恶猫钱庄、深坑、死人赌场、凯斯酒馆、晏安医务间、地下监牢、K 室） | 941×1672 |
| `scenes/undertide-backroom.png` | 后室铺具体场景（已就位；从井下总览点后室铺进入，能看货架、认栽或硬扛、按编号买、找掌柜修，返回井下地图） | 1024×1536 |
| `scenes/undertide-bank.png` | 恶猫钱庄具体场景（已就位；从井下总览点恶猫钱庄进入，可查账、借还、存取，返回井下地图） | 1024×1536 |
| `scenes/undertide-bounty.png` | 恩怨墙具体场景（已就位；从井下总览点恩怨墙进入，能看墙、接单、挂单，返回井下地图） | 1024×1536 |
| `scenes/undertide-medic.png` | 晏安医务间具体场景（已就位；从井下总览点晏安医务间进入，能治井下伤、看体质药，返回井下地图） | 1024×1536 |
| `scenes/undertide-casino.png` | 死人赌场具体场景（已就位；从井下总览点死人赌场进入，Silas 会出现在场景左侧，可玩骰/灯/抽牌） | 1024×1536 |
| `scenes/undertide-well.png` | 井口具体场景（**待出图**，现为占位框；从井下总览点「井下入口」进入，能看井、下井、进入潮下、看档案和指南、清井；没下过井时深坑、酒馆会引到这里） | 1024×1536 |
| `scenes/undertide-pit.png` | 深坑具体场景（**待出图**，现为占位框；点深坑进入，没下井先引去井口；下井后能选斗士、选打法下坑，看斗士榜和井壁胜场榜） | 1024×1536 |
| `scenes/undertide-tavern.png` | 凯斯酒馆具体场景（**待出图**，现为占位框；点酒馆进入，能看黑板、跟荔栀说话、耳语人买消息、查雇主、看动态、点红宝石、卖血） | 1024×1536 |
| `scenes/undertide-jail.png` | 地下监牢具体场景（**待出图**，现为占位框；点监牢进入，不用下井也能进，能看牢房、赎身、服刑、苦力） | 1024×1536 |
| `scenes/undertide-kroom.png` | K 室具体场景（**待出图**，现为占位框；点 K 室进入，不用下井也能进，能看、结算、价值回收） | 1024×1536 |
| `sprites/cat-bank-president.png` | 恶猫钱庄行长立绘（透明底；钱庄场景使用） | 1024×1536 |
| `sprites/silas.png` | Silas 荷官立绘（透明底；死人赌场场景使用） | 1024×1536 |

以上四张井下具体场景暂直接使用原 PNG，插图槽已标为不请求缺失的 WebP；后续压缩时再补同名 WebP 并移除该标记。
| `scenes/home.png` | 家园院子 | 1080×1920 |
| `scenes/yards.png` | 份地页底图（已就位；总览点进去先看份地景，点一下看地才出格子；海边草地，不是一块纯绿） | 941×1672 |
| `scenes/shore.png` | 海边滩景（已就位；总览点进去再点港口、海边。点港口就出列表，两个选项闲聊和看码头。点海边就出列表，两个选项去见韶年和去赶海） | 1080×1920 |
| `scenes/port.png` | 码头（已就位；滩景点港口就出列表：闲聊 / 看码头。闲聊是全屏聊天记录，能说话、发红包、对暗号、许愿墙，和上手页聊天室同一屋；看码头才进原来的岸边货架，能撒网、坐钓、开船） | 941×1672 |
| `scenes/beach.png` | 沙滩（已就位；滩景点海边就出列表：去见韶年 / 去赶海。去见韶年才出人韶年，底图用这张沙滩景；去赶海才进原来的出海货架，能撒网、坐钓、赶海、开船） | 1086×1448 |
| `scenes/plaza.png` | 潮汐广场（已就位；铺满一屏，底下不漏色；图上点杂货铺 / 灯塔 / 乔乔诊所 / 潮汐公告 / 栗栗流动摊。岸工坊在总览图上） | 941×1672 |
| `scenes/clinic.png` | 乔乔诊所（已就位；广场点进去先进店景，点一下才出人桥桥，半身立绘对话，桥桥站左边，只露上半身（全身的二分之一），先点对话框再出选项，点选项话写在对话框里，不另弹窗；能看病、调理、买药、喂斑鸠，和上手页桥桥同一家） | 941×1672 |
| `scenes/lili.png` | 栗栗流动摊（已就位；广场点进去先进摊车特写，点一下才出人栗栗，半身立绘对话，栗栗站左边，只露上半身（全身的二分之一），先点对话框再出选项，点选项话写在对话框里，不另弹窗；能看货、换货、献壳唤摊、摸夜栖，和上手页同一摊） | 1086×1448 |
| `scenes/shop.png` | Tt酱杂货铺（已就位；广场点进去先看店景，点一下才出货架，和灯塔选项一个样子，底下深色金边框） | 941×1672 |
| `scenes/lighthouse.png` | 灯塔（已就位；广场点进去先进塔景，点一下才出人不醒，不醒站左边，半身立绘对话，先点对话框再出选项，能喝茶、问潮、点灯、守夜） | 941×1672 |
| `sprites/buxing.png` | 守灯人·不醒立绘（已就位；灯塔先进塔景，点一下才出人不醒；对话只取半身、靠左，像橙光那样） | 460×1536 |
| `sprites/xiaoju.png` | 小橘立绘（已就位；剧场看台先进看台景，点一下才出人小橘；对话只取半身，全身的二分之一，靠左；半身框铺满宽度，立绘按原图完整露出，不要切掉右边） | 1024×1536 |
| `sprites/qiaoqiao.png` | 桥桥立绘（已就位；乔乔诊所先进店景，点一下才出人桥桥；对话只取半身，全身的二分之一，靠左） | 1086×1448 |
| `sprites/shaonian.png` | 韶年立绘（已就位；点海边就出列表，去见韶年才出人韶年，底图是沙滩景；对话只取半身，全身的二分之一，靠左） | 941×1672 |
| `sprites/lili.png` | 栗栗立绘（已就位；广场点流动摊先进摊车特写，点一下才出人栗栗；对话只取半身，全身的二分之一，靠左；半身框铺满宽度，立绘按原图完整露出，不要切掉右边摊车） | 1024×1536 |
| `sprites/tt.png` | Tt酱透明底立绘（已接入杂货铺；点店景后与货架一起出现，只露上半身；比上一版上移24px，保留立绘显示区域高度50%的下移，尺寸和货架位置不变；黑发外层、银白内层、双侧黑色长丝带，杂货掌柜工装） | 1024×1536 |
| `sprites/tt.webp` | Tt酱交互加载版（透明 WebP；约 175 KB；进入地图时随进度条预载） | 1024×1536 |
| `audio/island.mp3` | 手机地图背景乐之一（已就位；rumina《Magical Burger Town》。另有 `audio/island.ogg`） | 与花园曲依次循环 |
| `audio/vadim_makes_sound-fantasy-worlds-enchanted-garden-570007.mp3` | 手机地图背景乐之一（Vadim_Makes_Sound《Fantasy Worlds • Enchanted Garden》） | 与岛屿曲依次循环 |
| `audio/ncone-chiptune-garden-fight-535721.mp3` | 潮下专属背景乐（ncone《Chiptune Garden Fight》） | 进入井下切换；离开后回岛屿曲 |
| `scenes/notice.png` | 潮汐公告底（插图后补；广场点潮汐公告不换景，弹出 climate-frame 木牌，底下还是广场） | 1080×1920 |
| `climate-frame.png` | 潮汐木牌框（已就位；原图透明底，不要再抠。页面叠天气 / 潮汐 / 时辰 / 季节，头顶空着。弹窗，广场还在底下。广场点潮汐公告或总览左上角小牌弹出） | 1536×1024 |
| `stats-frame.png` | 左侧原六项数值木牌（影信、饱食、雾智、档信、健康、精力） | 1024×1536 |
| `status-frame.png` | 右侧新状态面板透明原图（工分票 / 等级 / 岛缘三行，右侧留动态数值位；不替换左侧六项木牌） | 1004×1118 |
| `status-frame.webp` | 右侧新状态面板交互加载版（透明 WebP；进入地图时随进度条预载） | 1004×1118 |
| `scenes/hut-1.png` | 棚屋（已就位；总览点小屋。没买房看不见这张图，点进去搭棚屋才解锁。点一下看屋里就能煮、能睡） | 941×1672 |
| `scenes/hut-2.png` | 岸畔小屋（已就位；小屋升到 Lv2 换这张） | 941×1672 |
| `scenes/hut-3.png` | 联盟小宅（已就位；小屋升到 Lv3 换这张） | 941×1672 |
| `scenes/hut-4.png` | 临海邸（已就位；小屋升到 Lv4 换这张） | 941×1672 |
| `scenes/bar.png` | 潮汐酒吧（已就位） | 1080×1920 |
| `scenes/theater.png` | 潮汐剧场院景（已就位；图上点编剧社 / 衣泊坊 / 剧场看台） | 1080×1920 |
| `scenes/writers.png` | 编剧社（已就位；先进店景，点一下才出收稿台） | 941×1672 |
| `scenes/atelier.png` | 衣泊坊（已就位；先进店景，点一下才出列表） | 941×1672 |
| `scenes/hall.png` | 剧场看台（已就位；先进看台景，点一下才出人小橘，半身立绘对话，小橘站左边，只露上半身，先点对话框再出选项，点选项话写在对话框里，不另弹窗，能应援、打赏、点歌、围观，专场才试镜、对戏、演出、领薪） | 941×1672 |
| `scenes/eatery.png` | 岸畔小馆（已就位；先进店景，点一下才出菜单） | 941×1672 |
| `scenes/hui.png` | 潮生会（已就位） | 941×1672 |
| `scenes/market.png` | 集市（已就位；总览进入先选集市 / 花店地名；选集市再进店景，点一下才出摊位列表，能看街摊、买、挂货、下架、扩摊） | 941×1672 |
| `scenes/ting.png` | 听潮亭（已就位） | 941×1672 |
| `scenes/lianli.png` | 连理所（已就位） | 941×1672 |
| `scenes/workshop.png` | 岸工坊（已就位；总览点进去先看店景，点一下才出列表；能打钉、灌盐、打捞；缺料也能点开看去哪弄。广场上的工坊位已改成乔乔诊所） | 941×1672 |
| `scenes/quarry.png` | 盐风崖（已就位；总览点进去先看店景，点一下才出列表；能买镐、探脉、挖、洗） | 941×1672 |
| `plot.png` | 份地土地（已就位；和草地拼装，一页最多 9 块） | 512×512 |
| `grass.png` | 份地草地（已就位；空位垫草） | 512×512 |
| `chip-back.png` | 进地点后左上角贴边「返回地图」（原图透明底，未另扣） | 2000×667 |
| `chip-bag.png` | 进地点后右上角背包（现宽约为先前两倍）；总览图上不显示；位置在贝壳音乐钮左边 | 550×185 |
| `chip-date.png` | 双贝壳爱心约会图标（内置 image_gen 生成，原始透明 PNG）；在背包左边同一水平，图案缩小三分之一至约29.3px宽，点击范围仍为44×66px；总览仍显示，点击看邀请/应邀/旁白/回忆，不直接扣票 | 1254×1254 |
| `chip-bgm-pause.png` | 右上角最边上贝壳音乐钮（正在播，点一下静音；两竖条） | 420×285 |
| `chip-bgm-play.png` | 右上角最边上贝壳音乐钮（已静音，点一下出声；三角） | 420×295 |
| `prompt-frame.png` | 手机地图提示框（已就位；打理 / 开垦 / 买货 / 岛上的事） | 840×840 |
| `bag-frame.png` | 进地点后点右上角背包弹出的行囊框（已就位；4×5 共 20 格，多了左右翻） | 941×1672 |
| `crops/{key}.png` | 作物图，按 catalog 英文 id | 256×256 |

参考原图可以放 `_src/`，运行时不读。

## 默语花房（2026-09-02）

使用内置 image_gen 分别生成，下列 PNG 是复制到仓库的原始输出，未另行裁切或抠图。可独立替换，不改变集市总览入口。

- `scenes/florist.png`：941×1672，店内背景；花草、香茅姜串、花茶罐，无人物。
- `sprites/momo.png`：1157×1360，默默半身立绘，RGBA 透明底；左侧柜台叠加。

背景完整提示词：

> Use case: stylized-concept. Asset type: portrait background for a cozy Chinese coastal life-simulation mobile game. Generate ONE background image, 9:16 portrait composition, warm finely detailed watercolor and gouache storybook illustration with delicate hand-drawn texture, soft turquoise daylight and natural wood, matching a gentle seaside village. Interior of a small flower shop, no people: overflowing fresh flowers in simple buckets, potted herbs, bundles of dried lemongrass and ginger hanging from wood beams, a row of flower-tea glass jars behind a wooden counter. The counter runs across the lower-middle area, leaving a clear space on its left for an adult shopkeeper sprite to be overlaid later, and the bottom quarter can sit behind a game dialogue panel. Through a side window a hint of the coastal market outside. Cozy, lived-in, not extravagant. No lettering, no logo, no UI, no watermark. Complete frame, no blank margins.

立绘完整提示词：

> Use case: stylized-concept. Asset type: one transparent PNG NPC sprite for a cozy seaside mobile life simulation. Subject: 默默, an unmistakably adult florist around 30, gentle and androgynous appearance, dark brown hair loosely tied back, cream linen shirt with rolled sleeves and a muted green florist apron, holding a small wrapped bouquet with relaxed natural hands, welcoming reserved smile, looking toward the viewer. Style: refined hand-drawn watercolor storybook game character, fine warm outlines, delicate watercolor paper shading, compatible with soft coastal village illustrations. Framing: head to waist only, full head and both shoulders visible with padding, upper body centered, intended to overlay at the left of a shop counter; not a full-body figure, no legs, no chibi proportions. GENUINELY TRANSPARENT alpha background with clean edges, no checkerboard illustration, no environment, no text, no watermark, no props outside the held bouquet.

## 井下五处（2026-10-31，待出图）

下面五张图在 `/island` 里现在显示「插图位」框，功能已接好。生成后放 `scenes/{id}.png`（1024×1536，竖屏，无人物），再把 `scenes/` 下对应项在 `ui/art.js` 的 `SLOTS` 里保持 `noWebp: true`（出了同名 WebP 再去掉）。统一画风：和已就位的井下总览、后室铺、钱庄、赌场一致——藤蔓爬满的石洞、暖黄提灯、青绿水光、手绘水彩加水粉的绘本质感。底部四分之一会被对话框盖住，别把关键物件放在最下面；左侧留一块空地，以后要加立绘能站。

公共后缀（每条提示词都要带）：

> No people, no characters, no lettering, no logo, no UI, no watermark. Complete frame, no blank margins.

井口完整提示词：

> Use case: stylized-concept. Asset type: portrait background for a cozy Chinese coastal life-simulation mobile game, underground area. Generate ONE background image, 2:3 portrait composition, warm finely detailed watercolor and gouache storybook illustration with delicate hand-drawn texture, overgrown stone cave lit by hanging brass lanterns, teal water glints and green vines, matching an earlier map of the same cave. Subject: the top of a deep old well shaft seen from just inside the cave entrance: a round mossy stone well rim in the middle foreground with a wooden ladder and a rope disappearing down into a faintly glowing teal darkness, a half-boarded wooden cover leaning at its side, a few lanterns hanging from rope above, pale daylight and falling vines at the very top edge, small pool of shallow water at the base. Quiet, slightly uneasy mood. The lower quarter stays calm and uncluttered for a dialogue panel; an open flat stone floor at the left side.

深坑完整提示词：

> Use case: stylized-concept. Asset type: portrait background for a cozy Chinese coastal life-simulation mobile game, underground area. Generate ONE background image, 2:3 portrait composition, warm finely detailed watercolor and gouache storybook illustration with delicate hand-drawn texture, vine-covered stone cave lit by brass lanterns, matching an earlier map of the same cave. Subject: a circular underground fighting pit seen slightly from above: round sand-and-stone arena floor with a faded compass-like mosaic in the center, curved stone spectator steps rising in rings, torn red-coral banners and rope barriers, a weapon rack and a bucket of water at the edge, lanterns on posts, moss and small flowers softening the harshness. Tense but storybook-gentle, no blood, no injuries. Keep the lower quarter calm for a dialogue panel; open floor at the left side.

凯斯酒馆完整提示词：

> Use case: stylized-concept. Asset type: portrait background for a cozy Chinese coastal life-simulation mobile game, underground area. Generate ONE background image, 2:3 portrait composition, warm finely detailed watercolor and gouache storybook illustration with delicate hand-drawn texture, vine-covered stone cave lit by brass lanterns, matching an earlier map of the same cave. Subject: the interior of a round underground tavern, no people: a curved wooden bar counter with a row of round stools, shelves of bottles and glass jars behind it, a teal scalloped awning over the counter, a few small round tables with candles, a chalkboard on the wall covered in scribbled but unreadable marks, a dim corner table with an empty chair, warm amber light with the lowest, brightest glow in the middle. Lived-in and a little shady, not luxurious. The lower quarter stays calm for a dialogue panel; open floor at the left side.

地下监牢完整提示词：

> Use case: stylized-concept. Asset type: portrait background for a cozy Chinese coastal life-simulation mobile game, underground area. Generate ONE background image, 2:3 portrait composition, warm finely detailed watercolor and gouache storybook illustration with delicate hand-drawn texture, vine-covered stone cave lit by brass lanterns, matching an earlier map of the same cave. Subject: a small underground jail inside a round cave chamber: a curved wrought-iron cage fence with an open door in the front, a plain wooden bench and a bucket inside, a heavy wooden work table with a rope and a pile of sacks outside the cage, a hanging lantern, a ring of keys on a nail, damp stone floor with a puddle reflecting lantern light, a little moss. Austere but gentle, storybook not grim, no chains on anyone. The lower quarter stays calm for a dialogue panel; open floor at the left side.

K 室完整提示词：

> Use case: stylized-concept. Asset type: portrait background for a cozy Chinese coastal life-simulation mobile game, underground area. Generate ONE background image, 2:3 portrait composition, warm finely detailed watercolor and gouache storybook illustration with delicate hand-drawn texture, vine-covered stone cave lit by brass lanterns, matching an earlier map of the same cave. Subject: the front of a private office door at the end of an underground passage: a large round arched wooden door with a brass ship-wheel style handle at the center, teal silk drapes tied back on both sides, brass lamp posts topped with glowing lanterns, a worn rug with a seashell motif leading to the door, small pools of water and starfish at the edges, a faint warm light leaking from under the door. Quiet, expensive, slightly intimidating. The lower quarter stays calm for a dialogue panel; open floor at the left side.

## 界面图标（手绘 SVG，不用 emoji）

`/island` 不用 emoji 当图标。图标在 `ui/icons.js`（24×24 线描 SVG，颜色跟随文字），服务端文案和数据名字里带的 emoji 在落进页面时由 `ui/emoji-svg.js` 换成对应图标；聊天室消息和表情包是玩家写的内容，原样保留。

- emoji → 图标的对照表是生成的：`python scripts/gen_emoji_icons.py`（`ui/emoji-map.js`，别手改）。新加了 emoji 没归类会落到通用小圆点，`tests/test_island_icons.py` 会提醒对照表过期。
- ★ ☆ ♡ ✓ 是版面符号（星级、好感、对错），不当图标，保留为文字。
- 要换更精致的图标：改 `icons.js` 里同名那一条，或补一条新图标再改生成脚本里的规则。
