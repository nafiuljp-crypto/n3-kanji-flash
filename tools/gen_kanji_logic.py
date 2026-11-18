#!/usr/bin/env python3
"""Generate data/kanji_logic.json from real kanji etymology.

Sources (structured, not WaniKani components or mnemonics):
  * KanjiVG       component trees; groups carry kvg:element, kvg:phon,
                  kvg:radical and kvg:original annotations.
  * KRADFILE      component decomposition cross-check (EDRDG).
  * Kanjium       kanjidb.sqlite: radical / phonetic / type / onyomi /
                  kunyomi / meanings / IDS, plus the phonetics table.
  * Wiktionary    "Glyph origin" sections: the 六書 classification and the
                  semantic (c1=s) / phonetic (c2=p) roles.

The committed JSON is the source of truth for the site; this script is the
maintenance tool that rebuilds it.  The source corpora are large and are not
vendored in the repo, so pass their paths:

    python3 tools/gen_kanji_logic.py \
        --kanjivg ~/src/kanjivg --kanjium ~/src/kanjium/data/kanjidb.sqlite \
        --kradfile ~/src/kradfile-u.gz --wikt-cache ~/src/wikt \
        --out data/kanji_logic.json

Environment fallbacks: KANJIVG_DIR, KANJIUM_DB, KRADFILE, WIKT_CACHE.
"""
import argparse
import collections
import gzip
import json
import os
import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
WORDS_FILE = BASE / "data" / "vocab_learn_2025_12.json"
DEFAULT_OUT = BASE / "data" / "kanji_logic.json"
KANJIVG_NS = "{http://kanjivg.tagaini.net}"

TYPE_LABEL = {
    "phono-semantic": "形声",
    "compound": "会意",
    "pictograph": "象形",
    "ideograph": "指事",
    "opaque": "—",
}

# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------
TRAD = {
    "仮": "假", "医": "醫", "厳": "嚴", "国": "國", "声": "聲", "学": "學",
    "対": "對", "帰": "歸", "悪": "惡", "担": "擔", "昼": "晝", "気": "氣",
    "渋": "澁", "点": "點", "発": "發", "絵": "繪", "証": "證", "転": "轉",
    "辺": "邊", "駅": "驛", "薬": "藥", "図": "圖", "壊": "壞", "懐": "懷",
    "満": "滿", "滞": "滯", "労": "勞", "写": "寫", "着": "著", "会": "會",
    "当": "當", "来": "來", "実": "實", "売": "賣", "買": "買", "読": "讀",
    "続": "續", "悪": "惡", "圧": "壓", "为": "為",
}

TYPE_OVERRIDE = {
    "中": "pictograph",       # flagpole at the centre
    "文": "pictograph",       # tattooed chest
    "発": "phono-semantic",   # 發 = 弓 + 癹
    "差": "compound",         # hulling wheat with the hand
    "写": "phono-semantic",   # 寫 = 宀 + 舄
    "着": "phono-semantic",   # 著 = 艸 + 者
    "会": "phono-semantic",   # 會 = 合 + 𡆧
    "当": "phono-semantic",   # 當 = 尚 + 田
    "実": "compound",         # 實 = 宀 + 貫
    "来": "pictograph",       # wheat plant
    "金": "phono-semantic",   # 亼/今 phonetic
    "買": "compound",         # 网 + 貝
    "昼": "compound",         # 晝 = 聿 + 日
    "見": "compound",         # 目 + 儿
    "正": "ideograph",        # 一 + 止: a foot moving to a line
    "外": "compound",         # 夕 + 卜: evening divination
    "間": "compound",         # 門 + 日: light through a gate
    "図": "phono-semantic",   # 圖 = 囗 + 啚
    "笑": "phono-semantic",    # 竹 + 夭
    "辺": "phono-semantic",   # 邊 = 辶 + 臱
    "友": "compound",         # two hands
}
KANJIUM_TYPE = {
    "Phono-semantic compound": "phono-semantic",
    "Compound ideograph": "compound",
    "Pictograph": "pictograph",
    "Ideograph": "ideograph",
}

# Component glosses.  Radical names from Kanjium's radicals/radvars tables are
# corrected where their English is misleading (頁 is "head", not "leaf").
COMP_GLOSS = {
    "一": "one", "丨": "vertical stroke", "丶": "dot", "丿": "slash stroke",
    "乙": "second heavenly stem", "亅": "hook", "二": "two", "亠": "lid",
    "人": "person", "亻": "person", "儿": "legs; person", "入": "enter",
    "八": "eight; divide", "冂": "border", "冖": "cover", "冫": "ice",
    "几": "table; stool", "凵": "container", "刀": "knife", "刂": "knife",
    "力": "power; strength", "勹": "wrap", "匕": "spoon", "匚": "box",
    "匸": "hiding enclosure", "十": "ten", "卜": "divination", "卩": "kneeling person",
    "厂": "cliff", "厶": "private", "又": "right hand", "口": "mouth",
    "囗": "enclosure", "土": "earth; soil", "士": "scholar; man",
    "夂": "slow walk", "夕": "evening", "大": "big; person", "女": "woman",
    "子": "child", "宀": "roof", "寸": "hand; measure", "小": "small",
    "⺌": "small", "⺍": "small", "尢": "lame", "尸": "body; corpse",
    "屮": "sprout", "山": "mountain", "巛": "river", "工": "work",
    "己": "self", "巾": "cloth", "干": "shield; dry", "广": "building",
    "廴": "long stride", "廾": "two hands", "弋": "stake; shoot",
    "弓": "bow", "彐": "snout", "彡": "bristles; ornament", "彳": "step; road",
    "心": "heart", "忄": "heart", "㣺": "heart", "戈": "halberd",
    "戶": "door", "戸": "door", "手": "hand", "扌": "hand", "支": "branch",
    "攴": "strike", "攵": "strike", "文": "writing; pattern", "斗": "dipper",
    "斤": "axe", "方": "square; direction", "无": "not", "日": "sun; day",
    "曰": "say", "月": "moon; month; flesh", "木": "tree; wood",
    "欠": "yawn; breath", "止": "stop; foot", "龰": "foot", "歹": "death",
    "殳": "weapon", "毋": "do not", "母": "mother", "比": "compare",
    "毛": "hair", "氏": "clan", "气": "air; steam", "水": "water",
    "氵": "water", "氺": "water", "火": "fire", "灬": "fire", "爪": "claw",
    "爫": "claw", "父": "father", "爻": "crossed lines", "爿": "split wood",
    "片": "slice", "牙": "tooth", "牛": "cow", "牜": "cow", "犬": "dog",
    "犭": "dog", "玄": "dark", "玉": "jade", "王": "jade; king",
    "瓜": "melon", "瓦": "tile", "甘": "sweet", "生": "life; sprout",
    "用": "use", "田": "field", "疋": "bolt of cloth", "疒": "illness",
    "癶": "footsteps", "白": "white", "皮": "skin", "皿": "dish",
    "目": "eye", "矛": "spear", "矢": "arrow", "石": "stone",
    "示": "altar; show", "礻": "altar", "ネ": "altar", "禸": "tracks",
    "禾": "grain", "穴": "hole", "立": "stand", "竹": "bamboo",
    "米": "rice", "糸": "silk; thread", "糹": "silk", "缶": "jar",
    "网": "net", "罒": "net", "羊": "sheep", "羽": "feather",
    "老": "old", "耂": "old", "而": "beard", "耒": "plough", "耳": "ear",
    "聿": "brush", "肉": "flesh", "臣": "minister", "自": "nose; self",
    "至": "arrive", "臼": "mortar", "舌": "tongue", "舛": "opposed feet",
    "舟": "boat", "艮": "stopping", "色": "colour", "艸": "grass", "艹": "grass",
    "虍": "tiger", "虫": "insect", "血": "blood", "行": "crossroads",
    "衣": "clothing", "衤": "clothing", "西": "west", "襾": "cover",
    "見": "see", "角": "horn", "言": "speech", "訁": "speech", "谷": "valley",
    "豆": "bean; vessel", "豕": "pig", "豸": "badger", "貝": "shell; money",
    "赤": "red", "走": "run", "足": "foot", "身": "body", "車": "cart",
    "辛": "bitter; sharp", "辰": "dragon", "辵": "walk", "辶": "walk",
    "⻌": "walk", "邑": "town", "⻏": "town", "阜": "mound", "⻖": "mound",
    "酉": "alcohol; jar", "釆": "divide", "里": "village; mile",
    "金": "metal; gold", "釒": "metal", "長": "long", "門": "gate",
    "阝": "mound or town", "隶": "capture", "隹": "short-tailed bird",
    "雨": "rain", "青": "blue-green", "靑": "blue-green", "非": "wrong",
    "面": "face", "革": "leather", "韋": "leather", "音": "sound",
    "頁": "head", "風": "wind", "飛": "fly", "食": "food", "飠": "food",
    "首": "head", "香": "fragrance", "馬": "horse", "骨": "bone",
    "高": "tall", "髟": "hair", "鬥": "fight", "魚": "fish", "鳥": "bird",
    "鹿": "deer", "麥": "wheat", "麻": "hemp", "黃": "yellow", "黒": "black",
    "鼓": "drum", "鼠": "rat", "鼻": "nose", "龍": "dragon", "龜": "turtle",
    # phonetic / common non-radical parts
    "寺": "temple", "交": "mix; cross", "古": "old", "旦": "dawn",
    "甬": "bronze bell", "占": "divine; occupy", "云": "cloud; say",
    "反": "turn over; oppose", "正": "correct", "主": "lord; master",
    "勺": "ladle", "勿": "do not", "与": "give", "具": "tool",
    "憂": "grief", "昔": "former times", "也": "also", "乍": "suddenly",
    "复": "return", "冬": "winter", "真": "true", "敬": "respect",
    "禁": "prohibit", "由": "reason; cause", "垂": "hang down",
    "更": "renew", "厷": "upper arm", "會": "meet", "会": "meet",
    "列": "row", "宁": "store", "少": "few", "丁": "nail", "其": "that",
    "束": "bundle", "帚": "broom", "丙": "third", "冏": "window",
    "夬": "decisive", "夭": "young", "炎": "flame", "曼": "long",
    "咅": "spit out", "何": "what", "巷": "alley", "幾": "how many",
    "帯": "belt", "帶": "belt", "安": "peace", "右": "right", "台": "stand",
    "奴": "slave", "内": "inside", "㝵": "obtain", "尚": "esteem",
    "吊": "hang", "寉": "crane", "辟": "law", "絜": "clean", "需": "need",
    "乞": "beg", "直": "straight", "郎": "young man", "旨": "purport",
    "道": "road", "合": "fit; join", "孝": "filial piety", "戉": "axe",
    "可": "can", "千": "thousand", "本": "root", "冒": "risk",
    "攸": "place; long", "宛": "address", "完": "complete", "召": "summon",
    "則": "rule", "周": "circumference", "亡": "dead", "开": "open",
    "九": "nine", "楽": "music; comfort", "樂": "music", "者": "person",
    "昜": "sun; bright", "義": "righteousness", "敢": "daring",
    "殸": "chime stone", "殹": "medical treatment", "舄": "magpie; shoe",
    "詹": "verbose", "睪": "watch; net", "㒼": "fill", "褱": "bosom",
    "羍": "lamb", "倝": "sunrise", "𬡤": "silk floss", "㠯": "use",
    "丩": "entwine", "隺": "crane", "幵": "level", "𠯑": "swallow",
    "囟": "fontanelle", "肰": "dog meat", "𡆧": "enclosure", "𢑓": "pig",
    "𡉉": "house", "亦": "also", "亼": "gather; cover", "啚": "remote area",
    "申": "lightning; report", "之": "go", "專": "special", "登": "climb",
    "東": "east", "棗": "jujube", "每": "every", "每": "every",
    "或": "territory; perhaps", "皀": "bowl of rice", "𠫓": "newborn",
    "𠂤": "troops", "㚔": "handcuffs", "𠬝": "subdue", "鼎": "cauldron",
    "堇": "clay", "卂": "fly", "𠂇": "left hand", "來": "wheat",
    "龰": "foot", "甾": "jar", "𠦝": "sunrise", "𭕄": "grass",
    "𠪚": "cliff", "𰃮": "two hands", "𭾱": "bosom", "⺕": "snout",
    "𠂢": "river branch", "㐅": "five", "乂": "mow; govern",
    "乃": "then", "丆": "cliff", "囬": "return", "𢌬": "bow",
    "肀": "hand", "𡗗": "cowries", "㳄": "saliva", "𠂈": "fall headlong",
    "𦥑": "two hands", "𡈼": "person on earth", "卪": "seal",
    "𠂉": "person", "𠔿": "cover", "冃": "cap", "𡉀": "earth",
    "癹": "trampling feet", "皀": "bowl of rice", "𦥑": "two hands",
    "𠂆": "hand issuing orders", "貫": "string of cowries", "堇": "clay",
}

# ---------------------------------------------------------------------------
# Curated decompositions where the modern glyph and the historical analysis
# do not align mechanically (shinjitai, cursive simplifications, corruptions).
# Entries: kanji -> [(label, role, reading, note)]; meanings come from
# COMP_GLOSS.  For compound/pictograph entries use (label, meaning, role).
# ---------------------------------------------------------------------------
SPECIAL_COMPS = {
    "写": [("冖", "meaning", None, "寫 has 宀; 写 writes a cover 冖"),
           ("与", "part", None, "modern form of the phonetic 舄"),
           ("舄", "sound", "しゃく", "historical phonetic of 寫, written 与 today")],
    "真": [("十", "part", None, None), ("具", "part", None, "the modern lower part"),
           ("𠂈", "sound", "てん", "historical phonetic"),
           ("鼎", "meaning", None, "the original picture was a cauldron")],
    "声": [("士", "part", None, None), ("尸", "part", None, "modern shape of 殸"),
           ("殸", "sound", "けい", "historical phonetic of 聲"),
           ("耳", "meaning", None, "聲 = 殸 (sound) + 耳 (ear)")],
    "厳": [("厂", "meaning", None, "cliff; the 喦 side of 嚴"), ("敢", "sound", "かん", "phonetic of 嚴")],
    "担": [("扌", "meaning", None, None),
           ("旦", "sound", "たん", "shinjitai replacement for 詹; it now gives the reading"),
           ("詹", "part", None, "historical phonetic of 擔")],
    "屈": [("尸", "meaning", None, "body; 尾 lost its 毛 in clerical script"),
           ("出", "sound", "くつ", "phonetic in Chinese; Japanese くつ is a conventional reading")],
    "駅": [("馬", "meaning", None, None),
           ("尺", "part", None, "shinjitai simplification, not the phonetic"),
           ("睪", "sound", "えき", "historical phonetic of 驛, written 尺 today")],
    "点": [("占", "sound", "せん", None),
           ("灬", "meaning", None, "fire; 點's 黑 was reduced to 灬")],
    "電": [("雨", "meaning", None, None),
           ("田", "part", None, "the modern writing of the phonetic 申"),
           ("申", "sound", "しん", "lightning; the historical phonetic")],
    "着": [("艸", "meaning", None, "grass; 著's original semantic"),
           ("目", "part", None, "著's 日 was corrupted to 目"),
           ("者", "sound", "しゃ", "phonetic of 著; 着 is a corrupted variant")],
    "辺": [("辶", "meaning", None, None),
           ("刀", "part", None, "shinjitai simplification, not the phonetic"),
           ("臱", "sound", "へん", "historical phonetic of 邊, lost in the shinjitai")],
    "絵": [("糸", "meaning", None, None), ("会", "sound", "かい", None)],
    "年": [("干", "part", None, None),
           ("禾", "meaning", None, "grain; the original sense was harvest"),
           ("人", "sound", "にん", "historical phonetic (bronze form 秂)")],
    "道": [("辶", "meaning", None, None), ("首", "sound", "しゅ", None)],
    "国": [("囗", "meaning", None, None), ("玉", "meaning", None, "jade inside the border"),
           ("或", "sound", "こく", "historical phonetic of 國")],
    "時": [("日", "meaning", None, None), ("寺", "sound", "じ", None)],
    "昼": [("尺", "part", None, "modern corruption of 聿 (brush)"),
           ("日", "meaning", None, "晝 = 聿 + 日: the daylight part of the day")],
    "夜": [("亠", "part", None, None), ("亻", "part", None, None),
           ("夕", "meaning", None, "moon; evening"),
           ("亦", "sound", "えき", "phonetic of 夜; distorted into 亠 + 亻")],
    "期": [("其", "sound", "き", None), ("月", "meaning", None, "month; a period of time")],
    "差": [("羊", "part", None, "the reduced 來/麥 (wheat)"),
           ("工", "part", None, "added under 𠂇 in the modern form")],
    "転": [("車", "meaning", None, None),
           ("云", "part", None, "shinjitai simplification, not the phonetic"),
           ("專", "sound", "せん", "historical phonetic of 轉")],
    "壊": [("土", "meaning", None, None), ("褱", "sound", "かい", "modern right side is a reduced 褱")],
    "家": [("宀", "meaning", None, None), ("豕", "sound", "し", "pig; the phonetic 𢑓 was corrupted to 豕")],
    "気": [("气", "meaning", None, "air; steam"),
           ("米", "sound", "べい", "historical phonetic of 氣"),
           ("乂", "part", None, "氣's 米 was reduced to 乂")],
    "医": [("匚", "meaning", None, "box; medicine case"), ("矢", "part", None, "arrow"),
           ("殹", "sound", "えい", "historical phonetic of 醫")],
    "証": [("言", "meaning", None, None),
           ("正", "sound", "しょう", "shinjitai replacement for 登; it now gives the reading"),
           ("登", "part", None, "historical phonetic of 證")],
    "仮": [("亻", "meaning", None, None), ("反", "part", None, "shinjitai replacement, not the phonetic"),
           ("叚", "sound", "か", "historical phonetic of 假")],
    "定": [("宀", "meaning", None, None), ("正", "sound", "てい", "written 疋-like today")],
    "笑": [("竹", "meaning", None, "bamboo"), ("夭", "sound", "よう", "phonetic; Japanese しょう is a later reading")],
    "句": [("勹", "meaning", None, "wrap; a hook"), ("口", "sound", "こう", None)],
    "屋": [("尸", "meaning", None, "roof; house"), ("至", "part", None, None),
           ("𡉉", "sound", "おく", "historical phonetic of 屋")],
    "思": [("田", "part", None, "the modern writing of 囟"), ("心", "meaning", None, None),
           ("囟", "sound", "しん", "fontanelle; the historical phonetic")],
    "然": [("灬", "meaning", None, "fire; 然 originally meant 'to burn'"),
           ("肰", "sound", "ぜん", "dog meat; the historical phonetic")],
    "当": [("⺌", "part", None, "尚 reduced"), ("⺕", "meaning", None, "field (田 reduced)"),
           ("尚", "sound", "しょう", "phonetic; 當 = 尚 + 田")],
    "労": [("力", "meaning", None, None),
           ("𬡤", "sound", "ろう", "historical phonetic of 勞")],
    "命": [("令", "sound", "れい", None), ("口", "meaning", None, None)],
    "会": [("人", "part", None, "合 reduced"), ("云", "part", None, "𡆧 reduced"),
           ("合", "meaning", None, "to meet"), ("𡆧", "sound", "かい", "phonetic of 會")],
    "満": [("氵", "meaning", None, None), ("㒼", "sound", "まん", "modern right side is a reduced 㒼")],
    "常": [("尚", "sound", "しょう", None), ("巾", "meaning", None, "cloth; 常 was a skirt")],
    "乾": [("日", "meaning", None, "sun; the 倝 side means sunrise"),
           ("乞", "part", None, None),
           ("倝", "sound", "かん", "historical phonetic of 乾")],
    "急": [("心", "meaning", None, None), ("及", "sound", "きゅう", "phonetic; 急 = 及 + 心")],
    "台": [("厶", "part", None, "㠯 reduced"), ("口", "meaning", None, None),
           ("㠯", "sound", "い", "historical phonetic of 台")],
    "教": [("孝", "part", None, None), ("攵", "meaning", None, "strike; action"),
           ("爻", "sound", "こう", "phonetic of 教"), ("子", "meaning", None, "child")],
    "度": [("广", "meaning", None, "building"), ("石", "sound", "せき", "phonetic of 度"),
           ("又", "part", None, "hand")],
    "重": [("千", "part", None, None), ("里", "part", None, None),
           ("人", "meaning", None, "a person carrying a load"),
           ("東", "sound", "とう", "phonetic of 重")],
    "親": [("見", "meaning", None, None), ("辛", "sound", "しん", "phonetic of 親")],
    "修": [("攸", "sound", "ゆう", None), ("彡", "meaning", None, "ornament; 修 = 攸 + 彡")],
    "早": [("日", "meaning", None, None), ("十", "part", None, "棗 reduced"),
           ("棗", "sound", "そう", "phonetic of 早")],
    "新": [("斤", "meaning", None, "axe"), ("立", "part", None, None), ("木", "part", None, None),
           ("辛", "sound", "しん", "phonetic of 新")],
    "薬": [("艹", "meaning", None, None), ("楽", "sound", "やく", "modern form of 樂; the Japanese on やく is a kan'yō reading outside the series")],
    "懐": [("忄", "meaning", None, None), ("褱", "sound", "かい", "modern right side is a reduced 褱")],
    "達": [("辶", "meaning", None, None), ("羊", "part", None, None),
           ("羍", "sound", "たつ", "phonetic of 達")],
    "悪": [("亜", "sound", "あ", None), ("心", "meaning", None, None)],
    "活": [("氵", "meaning", None, None), ("舌", "sound", "かつ", "modern writing of 𠯑")],
    "朝": [("𠦝", "sound", "かん", "phonetic of 朝"), ("月", "meaning", None, "moon")],
    "窓": [("穴", "meaning", None, "window"), ("忩", "sound", "そう", "written 公 + 心 in the modern glyph")],
    "金": [("亼", "sound", "きん", "phonetic, written 人 in the modern glyph"),
           ("王", "meaning", None, "metal in the earth"), ("呂", "part", None, "blocks of metal")],
    "発": [("癶", "part", None, "the feet in 癹"), ("弓", "meaning", None, "bow"),
           ("殳", "part", None, None), ("癹", "sound", "はつ", "phonetic of 發")],
    "体": [("亻", "meaning", None, None), ("本", "sound", "ほん", "phonetic; Japanese たい comes from 體")],
    "部": [("咅", "sound", "ほう", "phonetic of 部"), ("⻏", "meaning", None, "town")],
    "到": [("至", "meaning", None, "arrive"), ("刀", "sound", "とう", "phonetic; written 刂")],
}

# Pictographs: the glyph itself is the picture, so the "component" is the
# depicted object or the parts of the picture.
PICTO_COMPS = {
    "西": [("西", "a bird's nest", "part")],
    "回": [("回", "a spiral, a whirlpool", "part")],
    "手": [("手", "a hand with five fingers", "part")],
    "人": [("人", "a person seen from the side", "part")],
    "日": [("日", "the sun", "part")],
    "不": [("不", "the calyx of a flower", "part")],
    "糸": [("糸", "a skein of silk", "part")],
    "母": [("母", "a woman with emphasised breasts", "part")],
    "少": [("少", "small grains, a few dots", "part")],
    "来": [("来", "a wheat plant", "part")],
    "歩": [("止", "a foot", "part"), ("少", "two feet, one forward", "part")],
    "自": [("自", "a nose", "part")],
    "車": [("車", "a cart seen from above", "part")],
    "高": [("高", "a tall building", "part")],
    "者": [("者", "a cooking pot, later a person", "part")],
    "心": [("心", "the heart", "part")],
    "面": [("面", "a face or mask", "part")],
    "白": [("白", "an acorn", "part")],
    "文": [("文", "a tattooed chest", "part")],
    "飛": [("飛", "a bird in flight", "part")],
    "行": [("行", "a crossroads", "part")],
    "中": [("丨", "a flagpole", "part"), ("口", "the centre marked on it", "part")],
    "若": [("艹", "hair or grass", "part"), ("右", "a kneeling woman", "part")],
    "立": [("立", "a person standing on the ground", "part")],
    "力": [("力", "a plough or a flexed arm", "part")],
    "足": [("足", "a foot with the lower leg", "part")],
    "工": [("工", "a carpenter's square", "part")],
    "呂": [("呂", "two vertebrae", "part")],
    "弟": [("弟", "a spool with thread", "part")],
    "子": [("子", "a baby with outstretched arms", "part")],
    "走": [("走", "a person running", "part")],
    "大": [("大", "a person with arms outstretched", "part")],
    "目": [("目", "an eye", "part")],
    "果": [("木", "a tree", "part"), ("田", "fruit on the tree", "part")],
}

IDEO_COMPS = {
    "一": [("一", "one stroke: the number one", "part")],
    "上": [("上", "a line above a baseline: up", "part")],
    "下": [("下", "a line below a baseline: down", "part")],
    "入": [("入", "an arrowhead pointing inwards", "part")],
    "今": [("亼", "an inverted mouth", "part"), ("一", "a stroke marking 'now'", "part")],
    "音": [("言", "speech", "part"), ("一", "a stroke in the mouth: sound", "part")],
    "言": [("口", "mouth", "part"), ("辛", "a flute or tattoo needle", "part")],
    "束": [("木", "a tree", "part"), ("口", "a bundle tied round it", "part")],
    "正": [("一", "the line to be reached", "part"), ("止", "a foot moving towards it", "part")],
}

# Messy compound glyphs: use the historically correct decomposition.
COMPOUND_COMPS = {
    "見": [("目", "eye", "meaning"), ("儿", "person", "meaning")],
    "学": [("𦥑", "two hands", "meaning"), ("爻", "counting rods", "meaning"),
           ("子", "child", "meaning"), ("冖", "cover; roof", "meaning")],
    "図": [("囗", "enclosure; map border", "meaning"), ("啚", "sound", "と", "phonetic of 圖")],
    "昼": [("聿", "brush; written 尺 today", "meaning"), ("日", "sun; day", "meaning")],
    "対": [("文", "the modern top", "part"), ("寸", "hand", "meaning"),
           ("丵", "ritual vessel", "part"), ("土", "earth", "part")],
    "差": [("來", "wheat", "meaning"), ("𠂇", "left hand", "meaning"), ("工", "work", "part")],
    "帰": [("𠂤", "troops", "meaning"), ("帚", "broom", "meaning")],
    "冗": [("宀", "roof", "meaning"), ("儿", "person", "meaning")],
    "出": [("止", "foot", "meaning"), ("凵", "cave", "meaning")],
    "与": [("一", "a gift held out", "meaning"), ("勹", "a hand wrapping it", "meaning")],
    "渋": [("氵", "water", "meaning"), ("止", "foot held back", "meaning"),
           ("人", "meaning", None, "reduced from 歰 in the traditional form 澀")],
    "突": [("穴", "hole", "meaning"), ("犬", "dog", "meaning")],
    "報": [("幸", "meaning", None, "originally 㚔, handcuffs"),
           ("卩", "kneeling person", "meaning"), ("又", "hand", "meaning")],
    "実": [("宀", "roof", "meaning"), ("貫", "string of cowries", "meaning")],
    "事": [("又", "hand", "meaning"), ("中", "staff with a drum", "meaning")],
    "付": [("亻", "person", "meaning"), ("寸", "hand", "meaning")],
    "受": [("爪", "hand above", "meaning"), ("冖", "cover", "meaning"), ("又", "hand below", "meaning")],
    "引": [("弓", "bow", "meaning"), ("丨", "bowstring", "meaning")],
    "前": [("止", "foot", "meaning"), ("舟", "boat", "meaning"), ("刂", "knife", "part")],
    "風": [("几", "sail", "meaning"), ("虫", "insect", "meaning")],
    "具": [("鼎", "cauldron", "meaning"), ("廾", "two hands", "meaning")],
    "赤": [("大", "person", "meaning"), ("火", "fire", "meaning")],
    "漢": [("氵", "water", "meaning"),
           ("堇", "meaning", None, "originally 𦰩, a man with bound hands; not a phonetic in Japanese")],
    "品": [("口", "mouth ×3", "meaning")],
    "売": [("士", "scholar", "meaning"), ("冖", "cover", "meaning"), ("儿", "legs", "meaning")],
    "知": [("矢", "arrow", "meaning"), ("口", "mouth", "meaning")],
    "司": [("口", "mouth", "meaning"),
           ("𠂆", "meaning", None, "the hand/scepter element above the mouth; the reading does not come from it")],
    "多": [("夕", "evening ×2", "meaning")],
    "買": [("罒", "net", "meaning"), ("貝", "shell money", "meaning")],
    "得": [("彳", "step; road", "meaning"), ("㝵", "obtain", "meaning")],
    "意": [("音", "sound; speech", "meaning"), ("心", "heart", "meaning")],
    "商": [("立", "stand", "meaning"), ("冏", "window; emblem", "meaning")],
    "柔": [("矛", "spear", "meaning"), ("木", "tree", "meaning")],
    "友": [("又", "hand", "meaning"), ("又", "a second hand", "meaning")],
    "外": [("夕", "evening", "meaning"), ("卜", "divination", "meaning")],
    "間": [("門", "gate", "meaning"), ("日", "sunlight", "meaning")],
}

# Original-sense notes.  One short factual clause per kanji where the modern
# meaning is not simply the literal component sense.
ORIGIN = {
    "洋": "The water radical first named a river, then the ocean; Japanese compounds extended it to 'Western'.",
    "物": "Originally a coloured ox, later any thing.",
    "写": "寫 showed something placed under a roof; 写 is a cursive simplification.",
    "発": "發 showed a bow being released; 発 is the shinjitai.",
    "真": "The original picture was a cauldron; the modern sense 'true' is a later borrowing.",
    "声": "聲 was 'sound heard by the ear'; 声 is the shinjitai.",
    "優": "Originally 'ample, abundant', later 'gentle, superior'.",
    "苦": "A bitter plant: bitterness, then hardship.",
    "惜": "The heart's reluctance to let go: pity, regret.",
    "悔": "Regret: the heart turning over the past.",
    "厳": "嚴 showed a cliff and a fierce boar: stern.",
    "紙": "Silk was the writing surface before paper.",
    "他": "Another person: 'other'.",
    "担": "To carry a load on a shoulder pole.",
    "任": "To carry a burden: responsibility.",
    "昨": "The day just passed: yesterday.",
    "腹": "The belly.",
    "痛": "Illness with 甬 phonetic: pain.",
    "校": "A wooden frame or building: a school, also to proofread.",
    "頭": "The head; 頁 means head.",
    "不": "A calyx in origin; borrowed for 'not'.",
    "屈": "To bend the body: yield.",
    "駅": "A relay-horse station.",
    "終": "The knot at the end of a silk thread: end.",
    "点": "A black spot; 黑 was reduced to 灬.",
    "電": "Lightning from rain; 'electricity' is the modern extension.",
    "填": "To fill earth into a gap.",
    "働": "A person moving: to work (a Japanese-made kanji).",
    "驚": "A horse startled: to be surprised.",
    "着": "著 meant 'to place, attach'; 着 is its corrupted variant.",
    "襟": "The collar of a robe.",
    "袖": "The sleeve.",
    "雄": "A male bird.",
    "辺": "The edge of a road; 辺 is the shinjitai of 邊.",
    "通": "To go through.",
    "絵": "Coloured silk: a picture.",
    "例": "A person used as a model: example.",
    "貯": "Shell money stored away: savings.",
    "金": "Originally copper; later metal, then gold.",
    "年": "Originally 'harvest', later 'year'.",
    "道": "A road; 首 gives the sound.",
    "打": "To strike with the hand.",
    "聞": "An ear at a gate: to hear.",
    "私": "Private; 厶 originally meant 'private'.",
    "国": "A bordered territory; 玉 replaced 或 in the shinjitai.",
    "時": "The passing of time; 寺 replaced the older phonetic 之.",
    "夜": "Night; 亦 is phonetic.",
    "反": "To turn the hand over: reverse.",
    "代": "To take another's place.",
    "期": "A set period; 其 is phonetic.",
    "速": "Quick; 束 is phonetic.",
    "転": "To roll, revolve; 云 is a shinjitai simplification.",
    "壊": "To break earth: demolition.",
    "家": "A roof with a pig beneath: a household.",
    "詳": "Detailed speech.",
    "病": "Illness; 丙 is phonetic.",
    "気": "Air, breath; 气 gives the sound.",
    "医": "Medicine; 殹 is phonetic, 匚 the case.",
    "決": "Water breaking through: decision.",
    "証": "Evidence; 正 is the shinjitai phonetic.",
    "仮": "Temporary, false; 叚 is phonetic.",
    "定": "To settle; 正 gives the sound.",
    "彼": "That person: he.",
    "笑": "Laughter; 夭 is phonetic.",
    "句": "A phrase; 口 gives the sound.",
    "談": "To talk.",
    "慢": "Pride or laziness; 'slow' is a later extension.",
    "到": "To arrive.",
    "部": "A division; it first named a place in Gansu.",
    "屋": "A roof, a house.",
    "荷": "To carry a load.",
    "泊": "To moor a boat: overnight.",
    "空": "Empty; 工 is phonetic.",
    "港": "A harbour.",
    "機": "A loom: mechanism.",
    "滞": "Stagnant water.",
    "思": "Thought: the fontanelle (囟) over the heart.",
    "然": "To burn; later 'so, thus'.",
    "当": "To hit, correspond; 尚 is phonetic.",
    "案": "A plan laid out on a table.",
    "外": "Evening divination: outside.",
    "西": "A nest in origin; borrowed for 'west'.",
    "友": "Two hands joined: a friend.",
    "柔": "A spear against a tree: supple wood, tender.",
    "白": "The original referent is disputed; 'white' is the modern sense.",
    "来": "A wheat plant; borrowed for 'to come'.",
    "回": "A spiral or whirlpool: to turn, hence a time or round.",
    "労": "Labour, effort.",
    "懸": "To hang; 縣 is phonetic.",
    "命": "A command from above.",
    "派": "A branch of a river: faction.",
    "政": "To correct by action: government.",
    "治": "A river name; later 'govern'.",
    "努": "To exert strength.",
    "納": "To bring inside: pay, store.",
    "待": "To wait.",
    "注": "To pour.",
    "朝": "Morning.",
    "飯": "Cooked rice.",
    "会": "To meet.",
    "情": "Feeling.",
    "満": "Full.",
    "常": "A skirt in origin; later 'usual'.",
    "確": "Firm, certain.",
    "壁": "A wall of earth.",
    "清": "Clear water.",
    "潔": "Clean.",
    "拭": "To wipe.",
    "濡": "To get wet.",
    "乾": "Dry.",
    "急": "Urgent; 及 is phonetic.",
    "置": "To place.",
    "居": "To reside.",
    "台": "A stand; 㠯 is phonetic.",
    "所": "A place.",
    "廊": "A corridor.",
    "指": "A finger; 旨 is phonetic.",
    "導": "To lead.",
    "答": "An answer.",
    "教": "To teach.",
    "越": "To cross over.",
    "何": "What.",
    "度": "A measure; 石 is phonetic.",
    "重": "Heavy.",
    "体": "The body; Japanese たい comes from 體, not from 本.",
    "迷": "To lose the way.",
    "帽": "A cap.",
    "親": "Parent; 辛 is phonetic.",
    "修": "To cultivate.",
    "理": "Logic; 里 is phonetic.",
    "早": "Early.",
    "仲": "A go-between.",
    "腕": "The arm.",
    "院": "An institution.",
    "店": "A shop.",
    "違": "To differ.",
    "字": "A character; 子 is phonetic.",
    "的": "A target; the original form meant 'bright'.",
    "超": "To exceed.",
    "窓": "A window.",
    "側": "The side.",
    "週": "A week.",
    "海": "The sea.",
    "張": "To stretch.",
    "忙": "Busy.",
    "研": "To polish.",
    "究": "To investigate.",
    "新": "New.",
    "薬": "Medicine.",
    "効": "Effect.",
    "懐": "Bosom, pocket.",
    "持": "To hold.",
    "友": "Friend.",
    "達": "To reach.",
    "都": "A capital.",
    "悪": "Bad.",
    "約": "To bind: a promise.",
    "住": "To dwell.",
    "場": "A place.",
    "活": "To live.",
    "議": "Deliberation.",
    "建": "A hand plants a pole upright: to establish.",
    "合": "A lid closing over a mouth or vessel: things fitting together.",
    "見": "An eye on a kneeling person: to see.",
    "学": "Two hands handle counting rods above a child under a roof: learning by instruction.",
    "休": "A person leaning against a tree: rest.",
    "充": "A newborn grows to stand: to fill out, become full.",
    "郵": "A relay post at the edge of a town: mail.",
    "便": "A person changing posture to be comfortable: convenience.",
    "弁": "Two hands placing a cap on the head: a formal act; later 'valve, speech'.",
    "多": "Two evenings stacked: many.",
    "図": "A plan drawn inside a border: a map.",
    "昼": "A brush and the sun: the daylight part of the day.",
    "対": "A hand holding up a ritual vessel: a matching pair, hence 'opposite'.",
    "差": "A hand hulls wheat; 工 was added later: difference, distinction.",
    "帰": "A broom and troops: to put the enemy to flight and return home.",
    "羨": "Sheep and saliva: desire, envy.",
    "生": "A sprout emerging from the ground: life.",
    "明": "Sun and moon together: brightness.",
    "冗": "A person under a roof with nothing to do: superfluous.",
    "出": "A foot stepping out of a cave: to exit.",
    "与": "A gift held out and a hand wrapping it: to bestow.",
    "渋": "The traditional form 澀 has 歰 (two 刃 over 止); 渋 reduces the right side to 止 and a lower stroke. Water that does not flow: astringent, sluggish.",
    "突": "A dog bursting out of a hole: to thrust, sudden.",
    "得": "To walk and obtain: to get.",
    "意": "Sound or speech over the heart: intention.",
    "食": "A covered vessel over a bowl of rice: to eat.",
    "社": "An altar on the earth: the god of the soil, a company.",
    "報": "A convict in handcuffs, kneeling, with a hand above: to convict and declare guilty, hence to report.",
    "実": "A roof over a string of cowries: full, real.",
    "事": "A hand holding a staff with a drum: an affair, matter.",
    "取": "A hand taking an ear: to take.",
    "付": "A person and a hand: to hand over, attach.",
    "受": "A hand above and a hand below passing an object: to receive.",
    "引": "A bow with a drawn string: to pull.",
    "前": "A foot in a boat moving forward: in front.",
    "風": "A sail and an insect: wind.",
    "具": "Two hands holding a cauldron: a set of implements.",
    "祭": "A hand offering meat at an altar: a ritual.",
    "赤": "A person over fire: red.",
    "妻": "A hand seizing a woman's hair: wife (marriage by capture).",
    "買": "A net over shell money: to buy.",
    "漢": "The water of the Han River; its right-hand element was originally 𦰩, a man with bound hands. The river name gave the dynasty and China.",
    "先": "A foot ahead of a person: before.",
    "商": "A stand with a window or emblem: trade, a merchant.",
    "品": "Three mouths: goods, grades.",
    "売": "A scholar under a cover with legs: to sell (賣).",
    "知": "An arrow and a mouth: knowledge hitting the mark.",
    "登": "Two feet climbing a raised step: to ascend.",
    "司": "A mouth issuing orders under a hand: a director.",
    "外": "Evening divination: outside.",
    "西": "A nest in origin; borrowed for 'west'.",
    "友": "Two hands joined: a friend.",
    "柔": "A spear against a tree: supple wood, tender.",
    "白": "The original referent is disputed; 'white' is the modern sense.",
    "来": "A wheat plant; borrowed for 'to come'.",
    "回": "A spiral or whirlpool: to turn, hence a time or round.",
    "間": "Sunlight through a gate: an interval.",
}

# Established readings for phonetic components that are not standalone kanji
# in Kanjium.  Values are standard on'yomi, used for sound verification.
PHON_READING = {
    "舄": ["しゃく"], "𠂈": ["てん"], "殸": ["けい"], "詹": ["せん"],
    "睪": ["えき"], "㒼": ["まん"], "褱": ["かい"], "羍": ["たつ"],
    "倝": ["かん"], "𬡤": ["ろう"], "㠯": ["い"], "丩": ["きゅう"],
    "隺": ["かく"], "幵": ["けん"], "𠯑": ["かつ"], "囟": ["しん"],
    "肰": ["ぜん"], "𡆧": ["かい"], "𢑓": ["し"], "𡉉": ["おく"],
    "亼": ["きん"], "啚": ["と"], "𠂢": ["は"], "絜": ["けつ"],
    "宁": ["ちょ"], "臱": ["へん"], "𠂆": ["し"], "𠫓": ["とつ"],
    "殹": ["えい"], "癹": ["はつ"], "开": ["けん"], "忩": ["そう"],
}

# Where a shinjitai writes a substitute that is not the historical phonetic.
HIST_PHON = {
    "写": ("舄", "しゃく"),
    "辺": ("臱", "へん"),
    "駅": ("睪", "えき"),
    "転": ("專", "せん"),
    "仮": ("叚", "か"),
    "証": ("登", "とう"),
    "担": ("詹", "せん"),
}


def katakana_to_hiragana(s):
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)


def onyomi_list(raw):
    if not raw:
        return []
    return [katakana_to_hiragana(x) for x in re.findall(r"[ァ-ヶー]+", raw)]


def norm_reading(s):
    """Fold voicing so a rendaku form matches its base reading."""
    s = katakana_to_hiragana(s)
    table = str.maketrans("がぎぐげござじずぜぞだぢづでどばびぶべぼぱぴぷぺぽ",
                          "かきくけこさしすせそたちつてとはひふへほはひふへほ")
    return s.translate(table)


def split_params(s):
    out, cur, depth = [], "", 0
    for ch in s:
        if ch in "[{":
            depth += 1
        elif ch in "]}":
            depth -= 1
        if ch == "|" and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def find_templates(text, name):
    res, i = [], 0
    pat = "{{" + name
    while True:
        j = text.find(pat, i)
        if j < 0:
            break
        after = j + len(pat)
        if after < len(text) and text[after] not in "|}/":
            i = after
            continue
        k, depth = j + 2, 0
        while k < len(text) - 1:
            if text[k:k + 2] == "{{":
                depth += 1
                k += 2
                continue
            if text[k:k + 2] == "}}":
                if depth == 0:
                    break
                depth -= 1
                k += 2
                continue
            k += 1
        res.append(text[j + 2:k])
        i = k + 2
    return res


class Sources:
    def __init__(self, kanjivg, kanjium, kradfile, wikt_cache):
        self.kanjivg = Path(kanjivg)
        self.db = sqlite3.connect(str(kanjium))
        self.db.row_factory = sqlite3.Row
        self.kd = {r["kanji"]: dict(r) for r in self.db.execute("SELECT * FROM kanjidict")}
        self.phon = {r["phonetic"]: dict(r) for r in self.db.execute("SELECT * FROM phonetics")}
        self.krad = {}
        with gzip.open(kradfile, "rt", encoding="utf-8") as f:
            for line in f:
                if line.startswith("#") or " : " not in line:
                    continue
                a, b = line.strip().split(" : ", 1)
                self.krad[a] = b.split()
        self.wikt = {}
        for path in sorted(Path(wikt_cache).glob("*.json")):
            try:
                obj = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            t = (obj.get("parse") or {}).get("wikitext", "")
            if t:
                self.wikt[chr(int(path.stem, 16))] = t

    def kanjivg_top(self, ch):
        path = self.kanjivg / "kanji" / ("%05x.svg" % ord(ch))
        if not path.exists():
            return []
        root = ET.parse(path).getroot()
        tops = [g for g in root.iter() if g.get(KANJIVG_NS + "element") == ch]
        if not tops:
            return []
        kids = [c for c in tops[0] if c.get(KANJIVG_NS + "element")]
        while len(kids) == 1 and not any(
                kids[0].get(KANJIVG_NS + a) for a in ("phon", "radical")):
            nxt = [c for c in kids[0] if c.get(KANJIVG_NS + "element")]
            if not nxt:
                break
            kids = nxt
        out = []
        for c in kids:
            el = c.get(KANJIVG_NS + "element")
            if not el:
                continue
            phon = c.get(KANJIVG_NS + "phon") or next(
                (x.get(KANJIVG_NS + "phon") for x in c.iter()
                 if x.get(KANJIVG_NS + "phon")), None)
            rad = c.get(KANJIVG_NS + "radical") or next(
                (x.get(KANJIVG_NS + "radical") for x in c.iter()
                 if x.get(KANJIVG_NS + "radical")), None)
            out.append({"element": el, "phon": phon, "radical": rad,
                        "original": c.get(KANJIVG_NS + "original")})
        return out

    def glyph_section(self, ch):
        t = self.wikt.get(ch, "")
        m = re.search(r"===\s*Glyph origin\s*===(.*?)(?=\n===|\Z)", t, re.S)
        return (m.group(1).strip() if m else ""), t

    def wikt_compound(self, ch):
        _, t = self.glyph_section(ch)
        best = None
        for tp in find_templates(t, "Han compound"):
            ps = split_params(tp)[1:]
            d = {"args": []}
            for p in ps:
                if "=" in p:
                    k, v = p.split("=", 1)
                    d[k.strip()] = v.strip()
                elif p.strip():
                    d["args"].append(p.strip())
            if d.get("ls") in ("psc", "ic"):
                if best is None or d.get("ls") == "psc":
                    best = d
                if d.get("ls") == "psc":
                    break
        return best

    def wikt_liushu(self, ch):
        _, t = self.glyph_section(ch)
        return [p.split("|")[1].strip() for p in find_templates(t, "liushu")
                if "|" in p]

    def phonetic_readings(self, label):
        if not label:
            return []
        if label in PHON_READING:
            return list(PHON_READING[label])
        if label in self.phon:
            return onyomi_list(self.phon[label]["reading"])
        if label in self.kd:
            return onyomi_list(self.kd[label].get("onyomi"))
        return []

    def primary_reading(self, label):
        """The phonetic's basic series reading, used as the series label.

        The phonetics table records the reading the phonetic actually
        contributes to its series, which can differ from the phonetic's own
        standalone on'yomi (毎 is read まい as a kanji but かい in 海/悔).
        """
        if not label:
            return ""
        if label in self.phon:
            rd = onyomi_list(self.phon[label]["reading"])
            if rd:
                return rd[0]
        if label in self.kd:
            rd = onyomi_list(self.kd[label].get("onyomi"))
            if rd:
                return rd[0]
        if label in PHON_READING:
            return PHON_READING[label][0]
        return ""


def classify(src, ch):
    if ch == "々":
        return "opaque"
    if ch in TYPE_OVERRIDE:
        return TYPE_OVERRIDE[ch]
    page = TRAD.get(ch, ch)
    comp = src.wikt_compound(page)
    if comp:
        return "phono-semantic" if comp.get("ls") == "psc" else "compound"
    liu = src.wikt_liushu(page)
    if "psc" in liu:
        return "phono-semantic"
    if "ic" in liu:
        return "compound"
    if "p" in liu:
        return "pictograph"
    if "i" in liu:
        return "ideograph"
    return KANJIUM_TYPE.get((src.kd.get(ch) or {}).get("type"), "opaque")


def clean_wiki(text):
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.S)
    text = re.sub(r"<ref[^>]*/>", "", text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"\{\|.*?\|\}", "", text, flags=re.S)
    text = re.sub(r"\[\[(?:File|Image|file|image):.*?\]\]", "", text, flags=re.S)
    text = re.sub(r"\[\[[^]|]*\|([^]]*)\]\]", r"\1", text)
    text = re.sub(r"\[\[([^]]*)\]\]", r"\1", text)
    text = re.sub(r"<[^>]+>", "", text)

    def tmpl(m):
        parts = split_params(m.group(1))
        if not parts:
            return ""
        name = parts[0].strip()
        vals = [p for p in parts[1:] if "=" not in p]
        named = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                named[k.strip()] = v.strip()
        if name in ("zh-l", "l", "l-lite", "och-l", "m", "m-lite", "lang",
                    "w", "link", "lang-lite"):
            val = (vals[-1] if vals else named.get("1", "")).strip("* ")
            gloss = named.get("gloss") or named.get("t")
            return (val + (" (%s)" % gloss if gloss else "")) if val else ""
        return ""
    for _ in range(4):
        text = re.sub(r"\{\{([^{}]*)\}\}", tmpl, text)
    text = re.sub(r"\|[^|{}]{0,60}\}\}", "", text)
    text = text.replace("'''", "").replace("''", "")
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*([,.;:!?])\s*", r"\1 ", text)
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r"\(\s*\)", "", text)
    return text.strip(" :-–—*;,")


def primary_gloss(kd):
    if not kd:
        return ""
    return (kd.get("meaning") or kd.get("compact_meaning") or "").split(";")[0].strip()


def label_gloss(label, kd):
    if label in COMP_GLOSS:
        return COMP_GLOSS[label]
    if label in kd:
        return primary_gloss(kd[label]) or "part"
    return "part"


COMP_MEANING_OVERRIDE = {
    ("金", "王"): "metal in the earth",
    ("金", "呂"): "blocks of metal",
    ("昼", "聿"): "brush",
    ("図", "囗"): "map border",
    ("食", "亼"): "cover",
    ("合", "亼"): "lid",
    ("受", "爪"): "hand",
    ("多", "夕"): "evening ×2",
    ("当", "⺕"): "field (田 reduced)",
    ("屋", "尸"): "roof; house",
    ("辺", "臱"): "edge; phonetic",
    ("渋", "人"): "reduced lower element from 歰",
    ("漢", "堇"): "right-hand element, originally 𦰩",
    ("窓", "忩"): "the element 公 + 心",
    ("報", "幸"): "handcuffs, originally 㚔",
}


def special_components(rows, src, ch=""):
    out = []
    for row in rows:
        if len(row) == 3:
            label, meaning, role = row
            out.append({"label": label, "meaning": meaning, "role": role})
            continue
        label, role, reading, note = row
        c = {"label": label,
             "meaning": COMP_MEANING_OVERRIDE.get((ch, label)) or label_gloss(label, src.kd),
             "role": role}
        if reading:
            c["reading"] = reading
        if note:
            c["note"] = note
        out.append(c)
    return out


def build_components(src, ch, kind):
    if ch in PICTO_COMPS:
        return special_components(PICTO_COMPS[ch], src, ch)
    if ch in IDEO_COMPS:
        return special_components(IDEO_COMPS[ch], src, ch)
    if ch in COMPOUND_COMPS:
        c = special_components(COMPOUND_COMPS[ch], src, ch)
        return c
    if ch in SPECIAL_COMPS:
        return special_components(SPECIAL_COMPS[ch], src, ch)

    page = TRAD.get(ch, ch)
    comp = src.wikt_compound(page)
    vg = src.kanjivg_top(ch)
    aliases = {
        "水": "氵", "手": "扌", "心": "忄", "人": "亻", "糸": "糹", "言": "訁",
        "食": "飠", "金": "釒", "刀": "刂", "衣": "衤", "示": "礻", "犬": "犭",
        "爪": "爫", "火": "灬", "网": "罒", "玉": "王", "肉": "月", "艸": "艹",
        "邑": "⻏", "阜": "⻖", "辵": "⻌", "止": "龰", "小": "⺌", "戶": "戸",
        "每": "毎", "帶": "帯", "樂": "楽", "亞": "亜", "攴": "攵", "麥": "麦",
        "黑": "黒", "隺": "寉", "幵": "开", "專": "専", "宁": "宁",
    }

    def key(c):
        c = re.sub(r"#.*", "", c).strip("* ")
        return aliases.get(c, c)

    entries, used = [], set()
    if comp:
        for i, arg in enumerate(comp.get("args", []), 1):
            raw = re.sub(r"#.*", "", arg).strip("* ")
            label = re.sub(r"#.*", "", comp.get("alt%d" % i, "") or "").strip() or raw
            role = "sound" if comp.get("c%d" % i) == "p" else "meaning"
            if kind == "compound":
                role = "meaning"
            vis = None
            for v in vg:
                if key(v["element"]) == key(label) or key(v["element"]) == key(raw):
                    vis = v["element"]
                    break
            lab = vis or label
            c = {"label": lab, "meaning": label_gloss(lab, src.kd), "role": role}
            if role == "sound":
                rd = src.phonetic_readings(raw)
                c["reading"] = (rd[0] if rd else src.primary_reading(lab))
                if not vis:
                    c["note"] = "historical phonetic %s, not written as such in the modern glyph" % raw
                elif vis != raw:
                    c["note"] = "corresponds to the historical component %s" % raw
            entries.append(c)
            used.add(key(lab))
    # Add visible components the template omits (typically the modern
    # remains of a simplified glyph).  For a compound with no template at
    # all, all visible parts carry meaning.
    if kind != "compound" or not comp:
        for v in vg:
            el = v["element"]
            if key(el) in used:
                continue
            if kind == "compound":
                role = "meaning"
            else:
                role = "meaning" if v.get("radical") else "part"
            c = {"label": el, "meaning": label_gloss(el, src.kd), "role": role}
            if v.get("original") and v["original"] != el:
                c["note"] = "originally written %s" % v["original"]
            entries.append(c)
            used.add(key(el))
    seen, out = set(), []
    for c in entries:
        if c["label"] in seen:
            continue
        seen.add(c["label"])
        out.append(c)
    if not out:
        out = [{"label": ch, "meaning": primary_gloss(src.kd.get(ch, {})), "role": "part"}]
    return out


def phonetic_of(src, ch, comps):
    """Return (label, established_readings, note) for a phono-semantic kanji."""
    sounds = [c for c in comps if c["role"] == "sound"]
    if sounds:
        c = sounds[0]
        preads = src.phonetic_readings(c["label"])
        if not preads and c.get("reading"):
            preads = [c["reading"]]
        return c["label"], preads, ""
    if ch in HIST_PHON:
        label, reading = HIST_PHON[ch]
        return label, [reading], "historical phonetic"
    page = TRAD.get(ch, ch)
    comp = src.wikt_compound(page)
    if comp:
        for i, arg in enumerate(comp.get("args", []), 1):
            if comp.get("c%d" % i) == "p":
                raw = re.sub(r"#.*", "", arg).strip("* ")
                rd = src.phonetic_readings(raw)
                if rd:
                    return raw, rd, ""
    ph = (src.kd.get(ch) or {}).get("phonetic")
    if ph and ph != ch:
        rd = src.phonetic_readings(ph)
        if rd:
            return ph, rd, "Kanjium phonetic"
    for v in src.kanjivg_top(ch):
        if v.get("phon"):
            raw = re.split(r"[/0-9]", v["phon"])[0]
            rd = src.phonetic_readings(raw)
            if rd:
                return raw, rd, "KanjiVG phonetic"
    return "", [], ""


def relation_phrase(kread, pread):
    if not kread or not pread:
        return "the Japanese reading belongs to the phonetic's sound family"
    if kread == pread:
        return "exact match in the series"
    nk, np = norm_reading(kread), norm_reading(pread)
    if nk == np:
        return "voicing alternation in the same series"
    if len(np) > len(nk) and np.startswith(nk):
        return ("the Japanese on reading is a shortened form of the series reading %s"
                % pread)
    if len(nk) > len(np) and nk.startswith(np):
        return ("the Japanese on reading is an extended form of the series reading %s"
                % pread)
    return ("the Japanese on reading diverged from the series reading %s "
            "(a historical sound-family relationship)" % pread)


def meaning_line_for(ch, kind, comps, meaning):
    sem = [c for c in comps if c["role"] == "meaning"]
    snd = [c for c in comps if c["role"] == "sound"]
    origin = ORIGIN.get(ch, "")

    def fmt(c):
        return "%s (%s)" % (c["label"], c["meaning"])

    if kind == "phono-semantic":
        parts = []
        if sem:
            parts.append("Semantic " + " + ".join(fmt(c) for c in sem))
        if snd:
            c = snd[0]
            parts.append("phonetic %s (%s, %s)" % (c["label"], c["meaning"], c.get("reading", "")))
        line = " + ".join(parts) if parts else "A phono-semantic compound"
        if origin:
            line += ". " + origin
        line += ". Modern sense: %s." % meaning
    elif kind == "compound":
        line = " + ".join(fmt(c) for c in sem if c["role"] == "meaning")
        if origin:
            line += ". " + origin
        else:
            line += ": together they give the meaning."
        line += " Modern sense: %s." % meaning
    elif kind == "pictograph":
        depiction = "; ".join(c["meaning"] for c in comps)
        line = "Pictograph: %s." % depiction
        if origin:
            line += " " + origin
        line += " Modern sense: %s." % meaning
    elif kind == "ideograph":
        depiction = "; ".join(c["meaning"] for c in comps)
        line = "Indicative mark: %s." % depiction
        if origin:
            line += " " + origin
        line += " Modern sense: %s." % meaning
    else:
        line = "No structured decomposition was found; the glyph is learned as a whole."
    line = re.sub(r"\s+", " ", line)
    line = re.sub(r"\.\s*\.", ".", line)
    line = re.sub(r"\s+([.,;])", r"\1", line)
    return line.strip()


def reading_line_for(ch, kind, kd, comps, used_on, used_kun, standalone, sound):
    ons = onyomi_list(kd.get("onyomi"))
    used = sorted(used_on.get(ch) or [])
    shown = used or ons[:2]
    bits = []
    if kind == "phono-semantic" and sound and sound.get("label"):
        label = sound["label"]
        pread = sound["reading"]
        status = sound["status"]
        if shown:
            r0 = shown[0]
            extra = ""
            if sound.get("status") == "exact":
                known = [norm_reading(x) for x in sound.get("phonetic_onyomi", [])]
                cand = [r for r in shown if norm_reading(r) in known]
                if not cand:
                    cand = [r for r in onyomi_list(kd.get("onyomi"))
                            if norm_reading(r) in known]
                    if cand and cand[0] != r0:
                        extra = " (the form used in this word is %s)" % r0
                if cand:
                    r0 = cand[0]
                if r0 != pread and norm_reading(r0) == norm_reading(pread):
                    rel = "exact match in the series (%s is a rendaku form of %s)" % (r0, pread)
                else:
                    rel = "exact match in the series"
            else:
                rel = sound.get("relation") or relation_phrase(r0, pread)
            bits.append("On %s%s ← phonetic %s (%s); %s." %
                        (r0, extra, label, pread, rel))
        if sound.get("note"):
            bits.append(sound["note"] + ".")
    else:
        if shown:
            bits.append("On %s is learned with the kanji; the components give the meaning, not the sound." %
                        ", ".join(shown))
    kuns = (kd.get("kunyomi") or "").split("、")
    kuns = [k.replace("（", "").replace("）", "") for k in kuns if k]
    if used_kun.get(ch):
        vals = []
        for r in sorted(used_kun[ch]):
            full = next((k for k in kuns if k.startswith(r)), r)
            vals.append(full)
        bits.append("Kun %s is the native reading tied to the meaning." % ", ".join(vals))
    elif kuns:
        bits.append("Kun %s (native reading, tied to the meaning)." % ", ".join(kuns[:2]))
    if standalone.get(ch):
        w, r = standalone[ch]
        bits.append("Standalone word: %s (%s)." % (w, r))
    return " ".join(bits).strip()


MEANING_OVERRIDE = {
    "母": "mother",
}


def build_entry(src, ch, used_on, used_kun, words_by, standalone):
    kd = src.kd.get(ch) or {}
    kind = classify(src, ch)
    meaning = MEANING_OVERRIDE.get(ch) or primary_gloss(kd)
    entry = {"type": kind, "kind": kind, "type_label": TYPE_LABEL[kind],
             "meaning": meaning, "sources": []}

    if ch == "々":
        entry["sources"] = ["Kanjium"]
        entry["components"] = [{"label": "々", "meaning": "iteration mark", "role": "part"}]
        entry["meaning_line"] = ("々 is not a kanji with a meaning of its own: it repeats the preceding "
                                 "kanji (人々 = ひとびと).")
        entry["reading_line"] = "No reading of its own: it repeats the preceding kanji's reading."
        return entry

    comps = build_components(src, ch, kind)
    entry["components"] = comps
    sources = {"Kanjium"}
    if src.kanjivg_top(ch):
        sources.add("KanjiVG")
    if TRAD.get(ch, ch) in src.wikt or ch in src.wikt:
        sources.add("Wiktionary")

    sound = None
    if kind == "phono-semantic":
        label, preads, pnote = phonetic_of(src, ch, comps)
        kanji_on = sorted(set(onyomi_list(kd.get("onyomi")) + list(used_on.get(ch) or [])))
        exact = any(norm_reading(a) == norm_reading(b) for a in kanji_on for b in preads)
        kread = (sorted(used_on.get(ch) or []) or onyomi_list(kd.get("onyomi")) or [""])[0]
        match = ""
        for b in preads:
            if any(norm_reading(a) == norm_reading(b) for a in kanji_on):
                match = b
                break
        pread = match or (preads[0] if preads else src.primary_reading(label))
        if exact:
            rel = "exact match in the series"
        elif kread and pread:
            rel = relation_phrase(kread, pread)
        else:
            rel = "the reading is learned with the kanji"
        sound = {"label": label, "reading": pread,
                 "status": "exact" if exact else "family",
                 "relation": rel,
                 "phonetic_onyomi": sorted(set(preads) | ({src.primary_reading(label)} if src.primary_reading(label) else set()))}
        if pnote:
            sound["note"] = pnote
        entry["sound"] = sound
        # Keep the component's reading identical to the verified sound claim.
        for c in comps:
            if c["role"] == "sound" and c["label"] == label:
                c["reading"] = pread
        if label:
            entry["phonetic_series"] = {"label": label, "reading": pread}
            entry["_phonetic"] = label
        sources.add("KanjiVG")

    entry["meaning_line"] = meaning_line_for(ch, kind, comps, meaning)
    entry["reading_line"] = reading_line_for(ch, kind, kd, comps, used_on,
                                             used_kun, standalone, sound)
    entry["sources"] = sorted(sources)
    return entry


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kanjivg", default=os.environ.get("KANJIVG_DIR"))
    ap.add_argument("--kanjium", default=os.environ.get("KANJIUM_DB"))
    ap.add_argument("--kradfile", default=os.environ.get("KRADFILE"))
    ap.add_argument("--wikt-cache", default=os.environ.get("WIKT_CACHE"))
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()
    missing = [n for n in ("kanjivg", "kanjium", "kradfile", "wikt_cache")
               if not getattr(args, n)]
    if missing:
        raise SystemExit("missing source path(s): %s\nSee the module docstring." %
                         ", ".join("--" + m.replace("_", "-") for m in missing))

    src = Sources(args.kanjivg, args.kanjium, args.kradfile, args.wikt_cache)
    words = json.loads(WORDS_FILE.read_text(encoding="utf-8"))
    chars, used_on, used_kun, words_by, standalone = [], {}, {}, {}, {}
    for w in words:
        ks = [p for p in w["parts"] if p.get("type") == "kanji"]
        for p in ks:
            c = p["char"]
            if c not in chars:
                chars.append(c)
            words_by.setdefault(c, []).append(w)
            if p.get("used_type") == "onyomi" and p.get("used_reading"):
                used_on.setdefault(c, set()).add(p["used_reading"])
            if p.get("used_type") == "kunyomi" and p.get("used_reading"):
                used_kun.setdefault(c, set()).add(p["used_reading"])
        if len(ks) == 1:
            standalone[ks[0]["char"]] = (w["word"], w["reading"])

    entries = {c: build_entry(src, c, used_on, used_kun, words_by, standalone)
               for c in chars}

    series = collections.defaultdict(list)
    for c, e in entries.items():
        p = e.pop("_phonetic", "")
        if p:
            series[p].append(c)
    for c, e in entries.items():
        ps = e.get("phonetic_series")
        if not ps or not ps.get("label"):
            continue
        members = []
        for d in series.get(ps["label"], []):
            if d == c:
                continue
            od = entries[d]
            members.append({
                "kanji": d,
                "onyomi": sorted(used_on.get(d) or onyomi_list(
                    (src.kd.get(d) or {}).get("onyomi"))),
                "type": od["type"],
                "words": [{"word": w["word"], "reading": w["reading"]}
                          for w in words_by.get(d, [])[:2]],
            })
        if members:
            ps["members"] = members
        else:
            e.pop("phonetic_series", None)

    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)
        f.write("\n")
    kinds = collections.Counter(e["type"] for e in entries.values())
    print("wrote %d entries to %s" % (len(entries), args.out))
    print("types:", dict(kinds))
    print("phonetic series:", sum(1 for e in entries.values() if e.get("phonetic_series")))
    print("sound claims:", sum(1 for e in entries.values() if e.get("sound")))
    print("empty components:", [c for c, e in entries.items() if not e.get("components")])
    print("empty lines:", [c for c, e in entries.items()
                           if not e.get("meaning_line") or not e.get("reading_line")])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
