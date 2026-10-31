#!/usr/bin/env python3
"""生成 /island 的 emoji → 手绘图标对照表（server/static/island/ui/emoji-map.js）。

扫描服务端 py 和 /island 前端里出现过的所有 emoji，按 Unicode 名字归到 ui/icons.js 里的图标。
新加了 emoji 没归类会落到通用小圆点；跑一遍本脚本即可更新，tests/test_island_icons.py 会检查对照表是最新的。

    python scripts/gen_emoji_icons.py          # 写文件
    python scripts/gen_emoji_icons.py --check  # 只检查是否最新
"""
from __future__ import annotations

import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "server/static/island/ui/emoji-map.js"

# 版面符号，不是图标：★☆ 是星级，✓✗ 是对错，其余是箭头、点。
TEXT_SYMBOLS = set("★☆♡♥✓✔✗✘✕✖✦✧•·→←↑↓⇒")

RANGES = [(0x1F000, 0x1FAFF), (0x2600, 0x27BF), (0x2B00, 0x2BFF), (0x2300, 0x23FF), (0x21A9, 0x21AA), (0x2934, 0x2935)]

SOURCES = [
    *(ROOT / "server").glob("*.py"),
    *(ROOT / "server/v1").glob("*.py"),
    *(ROOT / "server/game").glob("*.py"),
    *(ROOT / "server/static/island").rglob("*.js"),
    ROOT / "server/templates/island.html",
    ROOT / "server/templates/partials/island-lounge.html",
]

# (图标, 名字里出现的关键词) 自上而下，先命中先用。
RULES: list[tuple[str, tuple[str, ...]]] = [
    ("shell", ("SPIRAL SHELL", "SCALLOP")),
    ("fish", ("FISH", "SHRIMP", "OYSTER", "CRAB", "LOBSTER", "SQUID", "OCTOPUS", "WHALE", "DOLPHIN", "SHARK", "JELLYFISH", "LOBSTER", "SEAL", "FLIPPER")),
    ("mushroom", ("MUSHROOM",)),
    ("egg", ("EGG", "COOKING")),
    ("bird", ("BIRD", "DOVE", "DUCK", "CHICKEN", "ROOSTER", "TURKEY", "SWAN", "PEACOCK", "OWL", "EAGLE", "PARROT", "FLAMINGO", "PENGUIN", "FEATHER", "HATCHING", "BABY CHICK", "GOOSE")),
    ("sweet", ("CAKE", "PIE", "COOKIE", "DOUGHNUT", "CUSTARD", "CANDY", "LOLLIPOP", "CHOCOLATE", "ICE CREAM", "HONEY", "PANCAKES", "WAFFLE", "CUPCAKE", "SHAVED ICE", "DANGO", "MOON CAKE", "FORTUNE COOKIE")),
    ("meat", ("MEAT", "POULTRY", "BACON", "HAMBURGER", "HOT DOG", "CHEESE", "SAUSAGE", "BONE")),
    ("bowl", ("BOWL", "POT OF FOOD", "STEW", "CURRY", "SPAGHETTI", "RAMEN", "SANDWICH", "TACO", "DUMPLING", "SUSHI", "SALAD", "TAMALE", "PIZZA", "FRENCH FRIES", "FLATBREAD", "BENTO", "RICE BALL", "RICE CRACKER", "ODEN", "FONDUE", "TAKEOUT", "FORK AND KNIFE", "FORK", "SPOON", "CHOPSTICKS", "PLATE")),
    ("grain", ("SHEAF", "RICE", "BREAD", "CROISSANT", "BAGUETTE", "PRETZEL", "BAGEL", "WHEAT", "CORN", "POPCORN")),
    ("cup", ("TEA", "COFFEE", "CUP", "GLASS", "BEER", "WINE", "COCKTAIL", "MILK", "JUICE", "SAKE", "BEVERAGE", "MATE", "BUBBLE", "DRINK", "CHAMPAGNE", "CLINKING")),
    ("bottle", ("BOTTLE", "FLASK", "TEST TUBE", "PILL", "SYRINGE", "LOTION", "JAR", "AMPHORA")),
    ("veg", ("CARROT", "TOMATO", "EGGPLANT", "POTATO", "BROCCOLI", "LEAFY GREEN", "GARLIC", "ONION", "CUCUMBER", "PEPPER", "BEANS", "PEANUT", "CHESTNUT", "GINGER", "SWEET POTATO", "ROOT")),
    ("fruit", ("APPLE", "PEAR", "ORANGE", "TANGERINE", "LEMON", "BANANA", "WATERMELON", "GRAPES", "STRAWBERRY", "CHERRIES", "PEACH", "MANGO", "PINEAPPLE", "COCONUT", "KIWI", "OLIVE", "BLUEBERRIES", "MELON", "AVOCADO", "TROPICAL", "LIME", "COCONUT", "POMEGRANATE", "FRUIT")),
    ("sprout", ("SEEDLING", "POTTED", "SPROUT", "HERB", "CLOVER")),
    ("leaf", ("LEAF", "LEAVES", "MAPLE", "PALM", "EVERGREEN", "DECIDUOUS", "CACTUS", "TREE", "BAMBOO", "TANABATA", "PINE DECORATION", "WOOD", "SHAMROCK")),
    ("flower", ("BLOSSOM", "FLOWER", "ROSE", "TULIP", "HIBISCUS", "SUNFLOWER", "BOUQUET", "HYACINTH", "LOTUS", "WILTED")),
    ("paw", ("PAW", "COW", "PIG", "SHEEP", "GOAT", "RABBIT", "DOG", "CAT ", "CAT FACE", "HORSE", "LLAMA", "CAMEL", "BEAR", "MOUSE", "RAT", "FOX", "WOLF", "DEER", "MONKEY", "OX", "BUFFALO", "BOAR", "HEDGEHOG", "SQUIRREL", "BAT", "LIZARD", "SNAKE", "FROG", "TURTLE", "SNAIL", "BUG", "BEE", "BUTTERFLY", "ANT", "SPIDER", "MOSQUITO", "WORM", "BEETLE", "CRICKET", "LADY BEETLE", "ELEPHANT", "KANGAROO", "BADGER", "SLOTH", "OTTER", "SKUNK", "TIGER", "LEOPARD", "LION", "ZEBRA", "GIRAFFE", "RHINOCEROS", "HIPPOPOTAMUS", "DROMEDARY", "ANIMAL", "FACE")),
    ("hammer", ("HAMMER", "WRENCH", "AXE", "SAW", "TOOLBOX", "NUT AND BOLT", "GEAR", "HAMMER AND PICK", "WORKS", "KNIFE", "HOCHO", "SHOVEL", "BROOM", "WAND", "MAGNET", "HOOK", "LADDER", "HAMMER AND WRENCH", "SCREWDRIVER", "BRICK", "CHAINS")),
    ("pick", ("PICK",)),
    ("scissors", ("SCISSORS",)),
    ("needle", ("NEEDLE", "SEWING")),
    ("thread", ("YARN", "THREAD", "KNOT")),
    ("rope", ("ROPE", "CHAIN", "KNOT", "PAPERCLIP")),
    ("wood", ("LOG",)),
    ("rock", ("ROCK", "MOUNTAIN", "STONE", "VOLCANO", "FOSSIL")),
    ("coin", ("COIN", "MONEY", "DOLLAR", "BANKNOTE", "CREDIT CARD", "PURSE", "MONEY BAG")),
    ("gem", ("GEM", "DIAMOND", "CRYSTAL", "PEARL")),
    ("ring", ("RING",)),
    ("crown", ("CROWN",)),
    ("box", ("PACKAGE", "BOX", "CARD FILE", "CARD INDEX", "FILE CABINET", "CRATE", "TRUNK", "LUGGAGE", "TRIANGULAR FLAG", "CLIPBOARD", "BASKET", "SHOPPING")),
    ("bag", ("BAG", "BACKPACK", "HANDBAG")),
    ("cloth", ("SHIRT", "COAT", "DRESS", "KIMONO", "JEANS", "SOCKS", "GLOVES", "SCARF", "HAT", "CAP", "SHOE", "BOOT", "SANDAL", "BIKINI", "CLOTHES", "NECKTIE", "LAB COAT", "SARI", "THONG", "RIBBON", "GOGGLES", "SUNGLASSES", "GLASSES", "BOW")),
    ("star", ("STAR", "SPARKLES", "GLOWING", "SHOOTING", "DIZZY")),
    ("heart", ("HEART", "KISS", "LOVE", "REVOLVING")),
    ("book", ("BOOK", "NOTEBOOK", "LEDGER", "BOOKS", "BOOKMARK", "NEWSPAPER", "PAGE", "MEMO", "TICKET", "TEXT")),
    ("scroll", ("SCROLL", "DOCUMENT", "RECEIPT", "BELL", "BOOKMARK TABS")),
    ("pen", ("PENCIL", "PEN", "BRUSH", "PAINTBRUSH", "CRAYON", "BLACK NIB", "WRITING", "LOWER LEFT")),
    ("key", ("KEY", "LOCK", "OLD KEY")),
    ("flame", ("FIRE", "FLAME", "HIGH VOLTAGE", "COLLISION", "FIRECRACKER", "CANDLE", "SPARKLER", "STOVE")),
    ("wave", ("WATER WAVE", "OCEAN", "WAVE", "SPLASHING", "TSUNAMI", "FOG")),
    ("drop", ("DROPLET", "SWEAT", "SNOWFLAKE", "SNOWMAN", "ICE", "CLOUD WITH RAIN", "UMBRELLA", "SHOWER", "BATH", "BUBBLES")),
    ("lantern", ("LANTERN", "LIGHT BULB", "FLASHLIGHT", "LAMP", "BEACON", "LIGHTHOUSE", "TOWER")),
    ("anchor", ("ANCHOR", "SHIP", "SAILBOAT", "CANOE", "FERRY", "SPEEDBOAT", "WHEEL")),
    ("boat", ("BOAT", "SAIL")),
    ("house", ("HOUSE", "HOME", "BUILDING", "TENT", "CASTLE", "HUT", "OFFICE", "FACTORY", "SHRINE", "BANK", "SCHOOL", "STATION", "STADIUM", "FOUNTAIN", "CHURCH", "HOTEL", "STORE", "ROOF")),
    ("pin", ("PUSHPIN", "ROUND PUSHPIN", "PIN", "LOCATION", "FLAG", "TRIANGULAR")),
    ("comment", ("SPEECH", "THOUGHT", "BALLOON", "LEFT SPEECH", "SPEAKING", "TELEPHONE", "MEGAPHONE", "LOUDSPEAKER", "ENVELOPE", "MAIL", "INBOX", "OUTBOX", "SPEAKER")),
    ("wind", ("WIND", "DASH", "TORNADO", "CYCLONE", "BLOWING", "LEAF FLUTTERING", "CLOUD")),
    ("salt", ("SALT", "SPICE", "PEPPER SHAKER")),
    ("magnify", ("MAGNIFYING", "LEFT-POINTING MAGNIFYING", "BINOCULARS", "TELESCOPE", "MICROSCOPE", "EYE")),
    ("bandage", ("ADHESIVE BANDAGE", "BANDAGE", "STETHOSCOPE", "HEALTH", "CROSS", "FIRST AID", "THERMOMETER", "HOSPITAL", "AMBULANCE", "BANDAID")),
    ("warning", ("WARNING", "NO ENTRY", "PROHIBITED", "RADIOACTIVE", "BIOHAZARD", "SKULL", "BOMB", "CROSS MARK", "EXCLAMATION", "SIREN", "ROTATING LIGHT")),
    ("card", ("PLAYING CARD", "CARD", "JOKER", "MAHJONG", "FLOWER PLAYING")),
    ("moon", ("MOON", "CRESCENT", "NIGHT", "SLEEPING", "ZZZ", "BED", "CITYSCAPE AT NIGHT")),
    ("sun", ("SUN", "SUNRISE", "SUNSET", "RAINBOW", "BRIGHT", "HOT SPRINGS", "THERMOMETER", "CLOCK")),
    ("spark", ("SPARKLES", "GLITTER", "MAGIC", "CRYSTAL BALL", "FIREWORKS", "CONFETTI", "TADA", "PARTY POPPER", "GIFT")),
    ("mic", ("MICROPHONE", "HEADPHONE", "STUDIO", "RADIO")),
    ("music", ("MUSICAL", "NOTE", "GUITAR", "VIOLIN", "TRUMPET", "SAXOPHONE", "DRUM", "PIANO", "MUSIC", "SCORE")),
    ("faucet", ("POTABLE WATER", "FAUCET", "SHOWER", "TOILET", "BUCKET")),
    ("smile", ("SMILING", "SMILE", "GRIN", "LAUGH", "WINK", "FACE", "WHITE SMILING", "HUGGING", "CRYING", "PLEADING", "THINKING", "ZANY", "KISSING", "RELIEVED", "TEARS", "SLEEPY", "UNAMUSED")),
    ("bubble", ("BUBBLE", "BLOB", "SOAP", "DISSOLVE", "THOUGHT BALLOON")),
    ("camera", ("CAMERA", "VIDEO", "TELEVISION", "FILM", "MOVIE", "CINEMA")),
    ("person", ("PERSON", "MAN", "WOMAN", "BOY", "GIRL", "BABY", "BUST", "SILHOUETTE", "PEOPLE", "FAMILY", "COUPLE", "DANCER", "BRIDE", "GUARD", "FARMER", "COOK", "TECHNOLOGIST", "ARTIST", "PILOT", "ASTRONAUT", "FIREFIGHTER", "POLICE", "DETECTIVE", "SANTA", "ANGEL", "MERMAID", "FAIRY", "GENIE", "ELF", "VAMPIRE", "ZOMBIE", "BEARD", "WALKING", "RUNNING", "STANDING", "KNEELING", "HANDSHAKE", "RAISED", "HAND", "FINGER", "FIST", "CLAPPING", "FOLDED", "OK HAND", "THUMBS", "WAVING", "VICTORY", "WRITING HAND", "NAIL POLISH", "MUSCLE", "FOOT", "LEG", "EAR", "NOSE", "MOUTH", "TONGUE", "TOOTH", "BRAIN", "BONE")),
    ("dice", ("DIE", "DICE", "GAME", "SLOT", "BILLIARDS", "BOWLING", "DART", "PUZZLE", "TEDDY", "KITE", "YO-YO", "CARTWHEEL", "JOYSTICK", "VIDEO GAME")),
    ("sword", ("SWORD", "CROSSED", "SHIELD", "BOW AND ARROW", "DAGGER", "TROPHY", "MEDAL")),
    ("send", ("ARROWHEAD", "BLACK RIGHTWARDS", "ARROW", "SEND")),
    ("back", ("LEFTWARDS", "RETURN", "ARROW CURVING", "HOOK")),
    ("link", ("LINK", "CHAIN",)),
]

# 名字归不上的，手工指。
OVERRIDES = {
    "⛏": "pick", "⚒": "hammer", "⚔": "sword", "⚓": "anchor", "⚠": "warning",
    "✂": "scissors", "✒": "pen", "✨": "spark", "❤": "heart", "❄": "drop", "☀": "sun",
    "☁": "wind", "☂": "drop", "☃": "drop", "☺": "smile", "✉": "comment", "✏": "pen",
    "⛵": "boat", "⭐": "star", "⭕": "dot", "⚡": "flame", "☕": "cup", "⌛": "sun",
    "⏰": "sun", "➤": "send", "↩": "back", "⌁": "link", "⌁": "link",
    "\U0001fabd": "bird", "\U0001fa99": "coin", "\U0001fa75": "wood", "\U0001fa84": "spark",
    "\U0001fab5": "wood", "\U0001fa62": "rope", "\U0001fa7a": "bandage", "\U0001fa79": "bandage", "\U0001fa9d": "hammer",
    "\U0001faa1": "needle", "\U0001faa8": "rock", "\U0001f9c2": "salt", "\U0001f6b0": "faucet", "\U0001f3a4": "mic",
    "\u2696": "dice", "\u2705": "check", "\U0001f346": "veg", "\U0001f381": "box", "\U0001f958": "bowl",
    "\U0001f96b": "box", "\U0001f9c8": "sweet", "\U0001fadb": "veg", "\U0001f3c3": "person", "\U0001f6b6": "person",
    "\U0001f477": "person", "\U0001f47b": "smile", "\U0001f409": "paw", "\U0001f9ed": "anchor", "\U0001fa78": "drop",
    "\U0001fab8": "shell", "\U0001fa91": "wood", "\U0001f6aa": "house", "\U0001f6a7": "warning", "\U0001f3f7": "pin",
    "\U0001f5fa": "scroll", "\U0001f5bc": "card", "\U0001f4c5": "card", "\U0001f5d3": "card", "\U0001f4c1": "box",
    "\U0001f4ff": "gem", "\U0001f50c": "flame", "\U0001f3ad": "smile", "\U0001f38f": "wind", "\U0001f492": "house",
    "\U0001f4a2": "warning", "\U0001f5ff": "rock", "\U0001f6ac": "flame", "\U0001fa9e": "gem", "\U0001fa8f": "hammer",
    "\U0001f4ac": "comment", "\U0001f4cc": "pin", "\U0001f3b4": "card", "\U0001f4e6": "box", "\U0001f4a8": "wind",
    "\U0001f9f5": "thread", "\U0001f455": "cloth", "\U0001f9e5": "cloth", "\U0001f458": "cloth", "\U0001f4dc": "scroll",
    "\U0001f50d": "magnify", "\U0001fae7": "bubble", "\U0001f30a": "wave", "\U0001f525": "flame", "\U0001f3e0": "house",
    "\U0001f319": "moon", "\U0001f41a": "shell", "\U0001f9ea": "bottle",
}


def is_emoji(ch: str) -> bool:
    if ch in TEXT_SYMBOLS:
        return False
    cp = ord(ch)
    return any(lo <= cp <= hi for lo, hi in RANGES)


def classify(ch: str) -> str:
    if ch in OVERRIDES:
        return OVERRIDES[ch]
    name = unicodedata.name(ch, "")
    for icon, words in RULES:
        if any(w in name for w in words):
            return icon
    return "dot"


def collect() -> dict[str, str]:
    found: set[str] = set()
    for path in SOURCES:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for ch in text:
            if is_emoji(ch):
                found.add(ch)
    return {ch: classify(ch) for ch in sorted(found)}


def render(mapping: dict[str, str]) -> str:
    rows = ",\n".join(f'  "{ch}": "{icon}"' for ch, icon in mapping.items())
    return (
        "/* 由 scripts/gen_emoji_icons.py 生成，别手改。emoji → ui/icons.js 里的手绘图标。 */\n"
        f"export const EMOJI_ICON = {{\n{rows},\n}};\n"
        f'export const TEXT_SYMBOLS = {sorted(TEXT_SYMBOLS)!r};\n'.replace("'", '"')
    )


def main() -> int:
    text = render(collect())
    if "--check" in sys.argv:
        ok = OUT.exists() and OUT.read_text(encoding="utf-8") == text
        print("emoji-map.js 是最新的" if ok else "emoji-map.js 过期：python scripts/gen_emoji_icons.py")
        return 0 if ok else 1
    OUT.write_text(text, encoding="utf-8")
    print(f"写入 {OUT.relative_to(ROOT)}，共 {len(collect())} 个 emoji")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
