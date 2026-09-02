"""默语花房物品表；鲜花不是种子，茶包需要在花房冲泡。"""
FLOWERS = {
    "rose": {"name": "玫瑰", "emoji": "🌹", "price": 68, "meaning": "赶在沉默之前说出口", "seasons": "春夏秋冬"},
    "daisy": {"name": "雏菊", "emoji": "🌼", "price": 48, "meaning": "今天的风很轻，适合见你", "seasons": "春夏秋冬"},
    "tulip": {"name": "郁金香", "emoji": "🌷", "price": 78, "meaning": "把春天郑重交给你", "seasons": "春"},
    "lily": {"name": "百合", "emoji": "💐", "price": 88, "meaning": "愿你每一次归来都有灯", "seasons": "春夏"},
    "sunflower": {"name": "向日葵", "emoji": "🌻", "price": 58, "meaning": "再晚也朝着有光的地方", "seasons": "夏"},
    "lavender": {"name": "薰衣草", "emoji": "🪻", "price": 68, "meaning": "夜里想起你", "seasons": "夏秋"},
    "osmanthus": {"name": "桂花", "emoji": "🌼", "price": 58, "meaning": "重逢时仍有熟悉的香气", "seasons": "秋"},
    "cosmos": {"name": "波斯菊", "emoji": "🌸", "price": 58, "meaning": "路走远了，心还在这里", "seasons": "秋冬"},
    "camellia": {"name": "山茶", "emoji": "🌺", "price": 78, "meaning": "安静地陪你过完冬天", "seasons": "冬春"},
}
TEAS = {
    "rose": {"name": "玫瑰花茶", "price": 38, "energy": 10, "wit": 2},
    "osmanthus": {"name": "桂花姜茶", "price": 48, "energy": 14, "wit": 2},
    "chrysanthemum": {"name": "菊花香茅茶", "price": 28, "energy": 8, "wit": 1},
}
FLORIST_DECOR = {f"flower_{key}": {"name": f"{v['name']}干花", "emoji": v["emoji"], "sell": 8,
    "hint": f"{v['meaning']}。纯装饰，无属性加成。"} for key, v in FLOWERS.items()}
FLORIST_ITEMS = {
    **{f"flower_{k}": {"name": v["name"], "sell": 8} for k, v in FLOWERS.items()},
    **{f"flower_tea_{k}": {"name": v["name"] + "包", "sell": 4} for k, v in TEAS.items()},
    **{f"deco_{k}": {"name": v["name"], "sell": v["sell"]} for k, v in FLORIST_DECOR.items()},
}
