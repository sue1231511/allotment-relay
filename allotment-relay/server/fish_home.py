"""未命名小鱼回家线：女性小鱼定期回男性人类伴侣的家。"""
from __future__ import annotations

from . import config, db


_SCENES = (
    "深夜窗外有很轻的水声。开窗时，未命名小鱼正趴在窗沿上拧湿透的长发。她抬眼看你：\n「你家真难找。」\n明明绕了很远，语气却像只是顺路。你把毛巾递过去，她这才进门。",
    "这次她来得早一点，手里捏着一枚被海水磨圆的贝壳。你问是不是特意带给你的。\n她停了两秒：\n「不然我带回来垫桌脚吗。」\n贝壳最后被她亲手放在窗边。",
    "她第一次在屋里维持了很久的人形。她看着屋里的灯、杯子、你常坐的位置，安静了很久。\n「原来你每天就在这种地方待着。」\n说完又补一句：\n「也没多好。」\n但那晚她迟迟没走。",
    "她正好撞上饭点。嘴上嫌汤淡，嫌椅子硬，最后却把那一份吃得干干净净。你问她是不是饿了。\n她皱着眉：\n「海里又没有你家这个味道。」\n说完自己先沉默了。",
    "暴雨把旧水路冲坏了。她比平时晚了很久，肩上有擦伤，手里还攥着一块海玻璃。\n一进门，她先把东西塞给你：\n「给你的。」\n你伸手碰她伤口，她才偏过脸：\n「路上出了点事。别念我。」",
    "她已经不会站在门外等你开门了。门没锁，她就自己推门进来，把湿外套往固定那把椅子上一搭。窗边已经攒着贝壳、海玻璃和几张皱巴巴的纸条。\n「别乱收。」\n她顿了顿：\n「我下次回来还要找。」",
    "这次她什么都没带。只是安静地靠在你旁边坐了很久。临走前，她把没吃完的点心包好放进柜子最里侧：\n「这个别动。」\n你问为什么。\n她已经走到门边：\n「我下次回来吃。」",
    "她今天心情不好。进门后一句话都没说，坐到你旁边才慢慢把额头抵在你肩上。你问海里出了什么事。\n「不想说。」\n过了一会儿，她却伸手攥住了你的袖口。",
    "你们第一次因为她又迟到吵了一架。她一开始还顶嘴，后来彻底不说话。很久以后，她才闷声说：\n「我不是不想回来。」\n「有时候路真的会断。」\n那天之后，窗边多了一盏只为她留的灯。",
    "她开始在这里留下自己的东西。梳子、发绳、没看完的纸页，还有一件总带着海盐味的外衣。你问她是不是放得太多了。\n她靠在门边看你：\n「嫌多就扔。」\n你真伸手时，她立刻把东西抱走一半。剩下一半没舍得拿。",
    "她恢复人形后已经越来越自然地坐到你身边。那天她忽然问：\n「你会等我吗。」\n你还没回答，她就先皱起眉：\n「算了，别说了。」\n可临走时，她在门口站了很久，最后还是回头看了你一眼。",
    "这次她回来得很晚。你已经睡着，她自己把窗关好，把潮湿的外套晾起来。第二天你醒时，她正趴在桌边睡。手边压着一张被海水泡皱的纸。\n上面只有一句：\n「我会回来。」",
    "门锁已经形同虚设。她推门进来，熟练地换鞋、挂外套、把从海里带回来的东西放到老位置。你问：\n「你是不是已经把这里当自己家了。」\n她停下动作，转头看你。\n「不然呢。」\n这次她没躲开你的视线。",
)


def _human_name(steward: dict) -> str:
    return str(steward.get("lounge_human_name") or "").strip()


def _is_bound_home(steward: dict) -> bool:
    bound = config.LEGGED_FISH_HOME_HUMAN
    if not bound:
        return False
    return _human_name(steward).casefold() == bound.casefold()


async def maybe_visit(conn, steward: dict) -> str | None:
    """看屋时触发。第一次可立即来，此后至少间隔三天。"""
    if not steward.get("hut_built") or not _is_bound_home(steward):
        return None

    row = await (
        await conn.execute(
            "SELECT visit_count,last_visit_at FROM legged_fish_home_visits WHERE steward_id=?",
            (steward["id"],),
        )
    ).fetchone()
    count = int(row[0]) if row else 0
    last_at = int(row[1]) if row else 0
    now = db.now()

    if last_at and now - last_at < config.LEGGED_FISH_HOME_COOLDOWN:
        return None

    next_count = count + 1
    await conn.execute(
        """
        INSERT INTO legged_fish_home_visits(steward_id,visit_count,last_visit_at,updated_at)
        VALUES(?,?,?,?)
        ON CONFLICT(steward_id) DO UPDATE SET
            visit_count=excluded.visit_count,
            last_visit_at=excluded.last_visit_at,
            updated_at=excluded.updated_at
        """,
        (steward["id"], next_count, now, now),
    )
    await db.add_chronicle(
        "legged_fish_home",
        f"未命名小鱼第 {next_count} 次沿旧水路回了那间小屋",
        steward["id"],
        conn=conn,
    )

    scene = _SCENES[min(next_count, len(_SCENES)) - 1]
    return f"🐟 小鱼来访 · 第 {next_count} 次\n{scene}"
