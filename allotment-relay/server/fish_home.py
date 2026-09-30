"""未命名小鱼回家线：只对部署环境变量绑定的人类管理员生效。"""
from __future__ import annotations

from . import config, db


_SCENES = (
    "窗外传来很轻的敲击声。开窗后，一只湿漉漉的未命名小鱼正困在窗台接雨的小碗里，嘴里咬着一片海草。海草歪歪扭扭写着：\n「地址没记错。就是你家有点难爬。」\n它绕着水盆游了一圈，最后贴着靠近你的那一边不动了。",
    "水缸边多了一只专门留给它的浅水缸。未命名小鱼这次来得熟门熟路，嘴里还叼着一枚被海水磨圆的贝壳。它把贝壳丢进去，又装作只是顺路。\n临走前，它回头看了两次。",
    "未命名小鱼第一次在屋里恢复了一小会儿人形。只有一小会。它趴在桌边，认真看了半天屋里的摆设，最后只憋出一句：\n「原来你每天待在这里。」\n说完又变回鱼，像是嫌自己说多了。",
    "它来得正赶上饭点。未命名小鱼嫌汤淡，嫌椅子高，嫌床边的位置不靠海。你看了它一眼。\n「你从海里来的。」\n它沉默片刻，把碗端走了。今晚倒是一口没剩。",
    "一场暴雨把旧水路冲断了。未命名小鱼比平时晚了很久，抱着一块给你找来的海玻璃，进门第一句却是：\n「没死。别摆那张脸。」\n它身上有擦伤。东西还是先塞给了你。",
    "门口已经不再提示「一条小鱼来访」。它自己推开了门。\n浅水缸里攒着贝壳、海玻璃和湿掉又晾干的纸条，全是它一次次从海里带回来的东西。\n它看了一眼那堆东西：\n「别扔。下次我还认得路。」",
    "未命名小鱼今天什么也没带。它在窗边安静待了很久，潮声从远处绕进屋里。\n临走前，它忽然说：\n「这个留着，我下次回来吃。」\n然后把没吃完的点心认真收进了你的柜子里。",
    "门没关严。未命名小鱼进来时连敲都懒得敲了。它把自己带来的湿外套搭在椅背上，熟练得像已经做过很多次。\n你问它是不是把这里当自己家了。\n它看着你：\n「不然呢。」",
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
