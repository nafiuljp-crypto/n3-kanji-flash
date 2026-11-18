#!/usr/bin/env python3
"""Generate data/kanji_logic.json — one structural-logic entry per kanji in
the Dec 2025 Learn Vocab set.

Data sources:
  data/vocab_learn_2025_12.json          the 243 words and their kanji parts
  data/curriculum.json                   site radical names
  <WaniKani subjects.json>               full API subject dump (kanji/radicals)

The committed data/kanji_logic.json is the source of truth for the site; this
script is the maintenance tool that rebuilds it. It needs the full WaniKani
subject dump (the repo's .cache file is a reduced slice).

Usage:
    python3 tools/gen_kanji_logic.py [--subjects PATH] [--out PATH]
"""
import argparse, collections, json, os, sys

BASE = os.environ.get('KLOGIC_BASE') or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SUBJECTS = os.path.expanduser('~/workspace/wanikani-clone/data/subjects.json')

# ---------------------------------------------------------------------------
# Curated structural facts.
#
# WaniKani's component list is the default decomposition. Where it splits a
# real sound component into strokes (e.g. 校 = 木 + 亠 + 父), the TRUE component
# is listed in PHONO and the WaniKani split is noted in the reading line.
# Ideographs/pictographs are curated because WaniKani often teaches them as a
# single radical.
# ---------------------------------------------------------------------------

# char -> (sound component char, sound's on reading used, meaning component
#          char or None, meaning-component family phrase, specific gloss)
PHONO = {
    '洋': ('羊', 'よう', '氵', 'water', 'So 洋 means "Western style; ocean" — the water radical places it in the sea/ocean field.'),
    '惜': ('昔', 'せき', '忄', 'feeling', 'So 惜しい means "precious; regrettable" — a feeling held about something.'),
    '紙': ('氏', 'し', '糸', 'thread/paper', '糸 is the material; the result is "paper".'),
    '担': ('旦', 'たん', '扌', 'hand/action', 'So 担 means "carry on the shoulder".'),
    '頭': ('豆', 'とう', '頁', 'head', 'So 頭 means "head".'),
    '電': ('田', 'でん', '雨', 'weather', 'So 電 means "electricity" — lightning is weather.'),
    '聞': ('門', 'もん', '耳', 'ear', 'So 聞 means "hear".'),
    '時': ('寺', 'じ', '日', 'sun/time', 'So 時 means "time".'),
    '速': ('束', 'そく', '⻌', 'movement/path', 'So 速 means "fast".'),
    '証': ('正', 'しょう', '言', 'speech/words', 'So 証 means "evidence" — words that prove.'),
    '彼': ('皮', 'ひ', '彳', 'walking person', 'So 彼 means "he; that one".'),
    '荷': ('可', 'か', '艹', 'plants', 'So 荷 means "luggage" — a load of plants/goods.'),
    '泊': ('白', 'はく', '氵', 'water', 'So 泊 means "overnight stay" — mooring by water.'),
    '滞': ('帯', 'たい', '氵', 'water', 'So 滞 means "stagnate" — water held back.'),
    '案': ('安', 'あん', '木', 'wood', 'So 案 means "plan" — originally a wooden tablet/desk.'),
    '懸': ('県', 'けん', '心', 'heart/mind', 'So 懸 means "suspend" — suspense in the heart.'),
    '政': ('正', 'せい', '夂', 'action', 'So 政 means "government" — correction carried out. (WaniKani names 夂 "Winter".)'),
    '飯': ('反', 'はん', '食', 'food/eating', 'So 飯 means "meal".'),
    '清': ('青', 'せい', '氵', 'water', 'So 清 means "pure; clear".'),
    '廊': ('郎', 'ろう', '广', 'building', 'So 廊 means "corridor".'),
    '導': ('道', 'どう', '寸', 'hand/measure', 'So 導 means "guide" — a hand leading the way.'),
    '何': ('可', 'か', 'ｲ', 'person', 'So 何 means "what".'),
    '迷': ('米', 'まい', '⻌', 'movement/path', 'So 迷 means "go astray".'),
    '理': ('里', 'り', '王', 'jade/king', 'So 理 means "reason" — the veins of jade.'),
    '仲': ('中', 'ちゅう', 'ｲ', 'person', 'So 仲 means "relationship" — the person in the middle.'),
    '買': ('貝', 'ばい', '罒', 'net', 'So 買 means "buy".'),
    '週': ('周', 'しゅう', '⻌', 'movement/path', 'So 週 means "week" — a cycle gone round.'),
    '張': ('長', 'ちょう', '弓', 'bow', 'So 張 means "stretch" — a bow drawn long.'),
    '忙': ('亡', 'ぼう', '忄', 'feeling', 'So 忙 means "busy" — the heart is occupied.'),
    '究': ('九', 'きゅう', '穴', 'hole', 'So 究 means "research" — digging into a hole.'),
    '効': ('交', 'こう', '力', 'power', 'So 効 means "effect".'),
    '持': ('寺', 'じ', '扌', 'hand/action', 'So 持 means "hold".'),
    '登': ('豆', 'とう', '癶', 'feet', 'So 登 means "climb".'),
    '議': ('義', 'ぎ', '言', 'speech/words', 'So 議 means "deliberation" — words about what is right.'),
    # Restored true sound components (WaniKani splits these into strokes).
    '優': ('憂', 'ゆう', 'ｲ', 'person', 'So 優 means "superior; gentle" — the sense is lexical.'),
    '校': ('交', 'こう', '木', 'wood', 'So 校 means "school" — a wooden building/frame.'),
    '働': ('動', 'どう', 'ｲ', 'person', 'So 働 means "work"; 働 is a Japanese-made kanji.'),
    '襟': ('禁', 'きん', '衤', 'clothing', 'So 襟 means "collar".'),
    '機': ('幾', 'き', '木', 'wood', 'So 機 means "machine" — a wooden frame/loom.'),
    '指': ('旨', 'し', '扌', 'hand/action', 'So 指 means "finger; point".'),
    '帽': ('冒', 'ぼう', '巾', 'cloth', 'So 帽 means "hat".'),
    '側': ('則', 'そく', 'ｲ', 'person', 'So 側 means "side".'),
    '悪': ('亜', 'あ', '心', 'heart/mind', 'So 悪 means "bad".'),
}

# True decomposition for restored cases; other phono entries use WaniKani's.
PHONO_COMPS = {
    '優': ['ｲ', '憂'],
    '校': ['木', '交'],
    '働': ['ｲ', '動'],
    '襟': ['衤', '禁'],
    '機': ['木', '幾'],
    '指': ['扌', '旨'],
    '帽': ['巾', '冒'],
    '側': ['ｲ', '則'],
    '悪': ['亜', '心'],
}
RESTORED_NOTE = {
    '優': 'WaniKani splits 憂 into 百+冖+心+夂; the sound component is the whole 憂 (ゆう).',
    '校': 'WaniKani splits 交 into 亠+父; the sound component is 交 (こう).',
    '働': 'WaniKani splits 動 into 重+力; the sound component is the whole 動 (どう).',
    '襟': 'WaniKani splits 禁 into 木+示; the sound component is the whole 禁 (きん).',
    '機': 'WaniKani splits 幾 into 幺+戈+人; the sound component is the whole 幾 (き).',
    '指': 'WaniKani splits 旨 into 匕+日; the sound component is the whole 旨 (し).',
    '帽': 'WaniKani splits 冒 into 日+目; the sound component is the whole 冒 (ぼう).',
    '側': 'WaniKani splits 則 into 貝+刂; the sound component is the whole 則 (そく).',
}

# Ideographs: components compose the meaning directly. All parts are "part".
IDEO = {
    '休': (['ｲ', '木'], 'a person (ｲ) resting at a tree (木) → rest'),
    '国': (['口', '王', '丶'], 'the outer 口 is the enclosure 囗 (not "mouth"); 王 + 丶 = 玉 (jade) inside → a bordered treasure land → country'),
    '回': (['口', '口'], 'a vessel/mouth inside an enclosure → go around; a turn; a time'),
    '合': (['亼', '口'], 'a lid (亼) over a mouth or vessel (口) → things fitting together → suit; match'),
    '句': (['勹', '口'], 'a mouth (口) inside a hook/wrap (勹) → a phrase; clause'),
    '外': (['夕', 'ト'], 'evening (夕) + divination (卜) → what lies outside; outside'),
    '見': (['目', '儿'], 'an eye (目) on legs (儿) → see'),
    '明': (['日', '月'], 'sun (日) + moon (月) → the two lights → bright'),
    '品': (['口', '口', '口'], 'three mouths (口) → many items → products'),
    '果': (['田', '木'], 'fruit on a tree (木) above a field (田) → fruit; result'),
    '束': (['木', '口'], 'a tree (木) tied with a loop (口) → bundle'),
    '家': (['宀', '豕'], 'a pig (豕) under a roof (宀) → house'),
    '赤': (['大', '火'], 'big (大) fire (火) → red'),
    '多': (['夕', '夕'], 'evening (夕) after evening (夕) → many'),
    '間': (['門', '日'], 'sun (日) seen through a gate (門) → interval; space'),
    '思': (['田', '心'], 'head/field (田) + heart (心) → think'),
    '音': (['言', '一'], 'speech (言) with one (一) tone → sound'),
    '買': (['罒', '貝'], 'a net (罒) + shell money (貝) → buy; 貝 also gives ばい'),
    '取': (['耳', '又'], 'a hand (又) taking an ear (耳) → take'),
    '友': (['ナ', '又'], 'two hands (ナ/又) joined → friend'),
    '体': (['ｲ', '本'], 'a person (ｲ) + root (本) → body'),
    '住': (['ｲ', '主'], 'a person (ｲ) settled with a master (主) → dwell'),
    '字': (['宀', '子'], 'a child (子) under a roof (宀) → character; learning'),
    '屈': (['尸', '出'], 'a body (尸) bent out (出) → yield; bend'),
    '少': (['小', '丿'], 'small (小) with a stroke removed (丿) → few'),
    '歩': (['止', '少'], 'stop (止) + few (少) → stepping → walk'),
    '道': (['⻌', '首'], 'movement (⻌) + head (首) → the road one heads along'),
    '打': (['扌', '丁'], 'hand (扌) + nail (丁) → strike'),
    '私': (['禾', '厶'], 'grain (禾) kept private (厶) → I; private'),
    '反': (['厂', '又'], 'a cliff (厂) + hand (又) → turn over → anti'),
    '転': (['車', '云'], 'a cart (車) rolling (云) → revolve'),
    '命': (['令', '口'], 'an order (令) spoken (口) → fate; command'),
    '意': (['音', '心'], 'sound (音) + heart (心) → intention'),
    '会': (['人', '云'], 'people (人) gathering (云) → meet'),
    '社': (['ネ', '土'], 'an earth (土) altar (ネ) → shrine; company'),
    '正': (['一', '止'], 'a foot (止) stopped at one line (一) → correct'),
    '付': (['ｲ', '寸'], 'a person (ｲ) with a hand (寸) → attach'),
    '上': (['ト', '一'], 'a mark above a line → above'),
    '下': (['一', 'ト'], 'a mark below a line → below'),
    '引': (['弓', '丨'], 'a bow (弓) with a string (丨) → pull'),
    '受': (['⺤', '冖', '又'], 'a hand (又) receiving under a cover (冖) → accept'),
    '濡': (['氵', '雨', '而'], 'water (氵) + rain (雨) → wet'),
    '祭': (['月', '又', '示'], 'meat (月) offered by hand (又) at an altar (示) → festival'),
    '早': (['日', '十'], 'the sun (日) on a line (十) → early'),
    '知': (['矢', '口'], 'words (口) straight as an arrow (矢) → know'),
    '答': (['竹', '合'], 'bamboo (竹) slips that fit (合) → answer'),
    '新': (['立', '木', '斤'], 'a tree (木) cut with an axe (斤) → new'),
    '薬': (['艹', '楽'], 'plants (艹) + comfort (楽) → medicine'),
    '店': (['广', '占'], 'a building (广) occupied (占) → shop'),
    '都': (['者', '阝'], 'people (者) + place (阝) → metropolis'),
    '約': (['糸', '勺'], 'thread (糸) bound → promise'),
    '置': (['罒', '直'], 'a net (罒) set straight (直) → place; put'),
    '帰': (['刂', '帚'], 'a broom (帚) and a knife (刂) → put things away → return home'),
    '勝': (['月', '卷'], 'meat (月) + strength (卷) → win'),
}
# Drop the placeholder that is not in the set (no harm if absent).
IDEO.pop('勝', None)

PICTO = {
    '西': 'Single-shape pictograph: the whole glyph is "west"; no component logic.',
    '言': 'Pictograph of a mouth (口) with breath/sound lines above it → speech; words.',
    '目': 'Pictograph of an eye, drawn upright → eye.',
    '手': 'Single-shape pictograph of a hand: the whole glyph is the meaning.',
    '人': 'Single-shape pictograph of a person\'s side profile.',
    '日': 'Single-shape pictograph of the sun.',
    '糸': 'Single-shape pictograph of twisted silk threads.',
    '母': 'Single-shape pictograph of a woman with emphasized breasts → mother.',
    '金': 'Single-shape pictograph of metal/gold in the ground.',
    '車': 'Single-shape pictograph of a cart with axle and wheels.',
    '自': 'Single-shape pictograph of a nose; used for "self".',
    '生': 'Single-shape pictograph of a plant sprouting from the ground → life.',
    '心': 'Single-shape pictograph of a heart.',
    '面': 'Single-shape pictograph of a face.',
    '白': 'Single-shape pictograph: the whole glyph is "white".',
    '文': 'Single-shape pictograph of a patterned/tattooed chest → writing.',
    '入': 'Single-shape pictograph of an entrance → enter.',
    '飛': 'Single-shape pictograph of a bird in flight.',
    '行': 'Single-shape pictograph of a crossroads → go.',
    '中': 'A pole through the middle of a box → middle.',
    '一': 'One horizontal stroke = one.',
    '立': 'A person standing on the ground → stand.',
    '力': 'Single-shape pictograph of a plough/muscle → power.',
    '足': 'Single-shape pictograph of a foot and leg.',
    '工': 'Single-shape pictograph of a carpenter\'s tool → construction.',
    '子': 'Single-shape pictograph of a baby with outstretched arms.',
    '大': 'A person with arms spread wide → big.',
    '不': 'Single-shape kanji: the whole glyph is "not"; no component logic.',
    '今': 'Single-shape kanji: the whole glyph is "now"; no component logic.',
    '夜': 'Single-shape kanji: the whole glyph is "night"; no component logic.',
    '重': 'Single-shape kanji: the whole glyph is "heavy"; no component logic.',
    '呂': 'Single-shape kanji: "bath" is a later use of the glyph; no component logic.',
    '高': 'Pictograph of a tall building; the modern strokes (亠, 口, 冋) are one picture, not a sound-meaning compound.',
    '来': 'Pictograph of a wheat plant, borrowed for "come"; the modern strokes (一, 米) are not a sound-meaning compound.',
    '年': 'Pictograph of a person carrying grain → year; the modern strokes (𠂉, 牛) are not a sound-meaning compound.',
    '食': 'Pictograph of a covered food vessel → eat.',
    '走': 'Pictograph of a person running → run.',
    '出': 'Pictograph of a footstep emerging from a mountain/cave → exit.',
    '弟': 'Pictograph of a younger brother; the modern strokes are not a sound-meaning compound.',
}

# Honest sound-family notes for near-misses (component sound differs exactly).
NEAR = {
    '試': '式 (しき) is the historical sound source, but しき is not し — no exact key.',
    '苦': '古 (こ) is the historical sound source; こ is not く — no exact key.',
    '悔': '毎 (まい) is close to かい but not exact.',
    '詳': '羊 (よう) is the historical sound source; よう is not しょう — no exact key.',
    '情': '青 (せい/しょう) is the voiced source of じょう, but not exact.',
    '物': '勿 (もち) is close to ぶつ/もつ but not exact.',
    '昨': '乍 has the sound さく, but WaniKani gives 乍 no kanji reading — unverified.',
    '壁': '辟 has the sound へき, but WaniKani gives 辟 no kanji reading — unverified.',
    '違': '韋 has the sound い, but WaniKani gives 韋 no kanji reading — unverified.',
    '空': '工 (く) is the historical sound source; く is not くう.',
    '海': '毎 (まい) is close to かい but not exact.',
    '痛': '用 (よう) is part of the sound source 甬 (つう), but 用 reads よう — no exact key.',
    '終': '冬 (とう) is close to しゅう but not exact.',
    '写': '写 is a simplified form of 寫; no sound component survives.',
    '声': '声 is a simplified form of 聲; no sound component survives.',
    '駅': 'The right side is a simplified phonetic, not 尺 — no exact key for えき.',
    '学': '学 is a simplified form of 學; no exact sound component survives.',
    '図': '図 is a simplified form of 圖; no sound component survives.',
    '売': '売 is a simplified form of 賣; no sound component survives.',
    '発': '発 is a simplified form of 發; no sound component survives.',
    '当': '当 is a simplified form of 當; no sound component survives.',
    '実': '実 is a simplified form of 實; no sound component survives.',
    '医': '医 is a simplified form of 醫; no sound component survives.',
    '気': '気 is a simplified form of 氣; 气 is the meaning side, not the sound (き).',
    '研': '开 (けん) is the historical sound source, but it is not a kanji in WaniKani — unverified.',
    '場': '昜 (よう) is the historical sound source; よう is not じょう — no exact key.',
    '教': '孝 (こう) is the historical sound source; こう is not きょう — no exact key.',
    '漢': '堇 (きん) is the historical sound source; きん is not かん — no exact key.',
    '達': '羍 (たつ) is the historical sound source, but WaniKani splits it into 土+羊 — unverified.',
    '修': '攸 (ゆう) is the historical sound source; ゆう is not しゅう — no exact key.',
    '治': '台 (たい) is the historical sound source; たい is not じ — no exact key.',
}

# Component char -> semantic field phrase, used when the composition is opaque.
FIELD = {
    '氵': 'water/liquid', '忄': 'heart/feeling', '心': 'heart/mind', '言': 'speech/words',
    '糸': 'thread/textile', '疒': 'illness', '艹': 'plants', '日': 'sun/time',
    '月': 'body/moon', '石': 'stone', '木': 'wood/trees', '扌': 'hand/action',
    '⻌': 'movement/path', '口': 'mouth/speech', '土': 'earth', '金': 'metal',
    '女': 'woman', '馬': 'horse', '山': 'mountain', '火': 'fire', 'ｲ': 'person',
    '人': 'person', '子': 'child', '宀': 'roof/building', '广': 'building',
    '門': 'gate', '尸': 'building/body', '阝': 'place', '頁': 'head',
    '食': 'food/eating', '衤': 'clothing', 'ネ': 'ritual/altar', '示': 'ritual/altar',
    '刂': 'cutting', '刀': 'cutting', '力': 'power', '弓': 'bow', '車': 'vehicle',
    '貝': 'money/shell', '王': 'jewel', '玉': 'jewel', '目': 'eye', '耳': 'ear',
    '足': 'foot', '米': 'rice', '雨': 'weather', '气': 'air', '欠': 'breath',
    '首': 'neck', '竹': 'bamboo', '巾': 'cloth', '斤': 'axe', '彳': 'walking',
    '穴': 'hole', '户': 'door', '犬': 'dog', '牛': 'cow', '禾': 'grain',
    '虫': 'insect', '魚': 'fish', '鳥': 'bird', '骨': 'bone', '血': 'blood',
    '色': 'color', '青': 'blue/green', '赤': 'red', '白': 'white', '黒': 'black',
    '厂': 'cliff', '疋': 'cloth', '缶': 'jar', '皿': 'dish', '矢': 'arrow',
    '戈': 'weapon', '攵': 'action', '頁': 'head', '隹': 'bird', '冖': 'cover',
}

ALIAS = {'囗': '口', '亻': 'ｲ', '辶': '⻌', '攵': '夂', '龰': '止', '厶': 'ム'}


def primary(e):
    for m in e['data'].get('meanings') or []:
        if m.get('primary'):
            return m['meaning']
    mm = e['data'].get('meanings') or []
    return mm[0]['meaning'] if mm else ''


class Data:
    def __init__(self, subjects_path):
        raw = json.load(open(subjects_path, encoding='utf-8'))
        subs = raw['data'] if isinstance(raw, dict) else raw
        self.byid = {e['id']: e for e in subs}
        self.K = {e['data']['characters']: e for e in subs
                  if e['object'] == 'kanji' and e['data'].get('characters')}
        self.R = {e['data']['characters']: e for e in subs
                  if e['object'] == 'radical' and e['data'].get('characters')}
        cur = json.load(open(os.path.join(BASE, 'data', 'curriculum.json'),
                             encoding='utf-8'))
        self.CURR = {}
        for w in cur['weeks']:
            for r in w['radicals']:
                if r.get('char') and r['char'] not in self.CURR:
                    self.CURR[r['char']] = r['meaning']

    def comp_info(self, cid):
        s = self.byid[cid]
        d = s['data']
        return {'obj': s['object'], 'char': d.get('characters'),
                'meaning': primary(s), 'id': cid}

    def meaning(self, ch):
        ch = ALIAS.get(ch, ch)
        if ch in self.CURR:
            return self.CURR[ch]
        if ch in self.R:
            return primary(self.R[ch])
        if ch in self.K:
            return primary(self.K[ch])
        return None

    def onyomi(self, ch):
        ch = ALIAS.get(ch, ch)
        e = self.K.get(ch)
        if not e:
            return []
        return [r['reading'] for r in (e['data'].get('readings') or [])
                if r.get('type') == 'onyomi']

    def kunyomi(self, ch):
        ch = ALIAS.get(ch, ch)
        e = self.K.get(ch)
        if not e:
            return []
        return [r['reading'] for r in (e['data'].get('readings') or [])
                if r.get('type') == 'kunyomi']

    def wk_comps(self, ch):
        e = self.K.get(ch)
        if not e:
            return []
        return [self.comp_info(cid)
                for cid in e['data'].get('component_subject_ids') or []]

    def subject_for(self, ch):
        ch = ALIAS.get(ch, ch)
        if ch in self.K:
            return self.K[ch]
        if ch in self.R:
            return self.R[ch]
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--subjects', default=DEFAULT_SUBJECTS)
    ap.add_argument('--out', default=os.path.join(BASE, 'data', 'kanji_logic.json'))
    args = ap.parse_args()
    D = Data(args.subjects)

    words = json.load(open(os.path.join(BASE, 'data', 'vocab_learn_2025_12.json'),
                           encoding='utf-8'))
    chars = []
    used_on = collections.defaultdict(set)
    used_kun = collections.defaultdict(set)
    words_by = collections.defaultdict(list)
    standalone = {}
    part_meaning = {}
    for w in words:
        ks = [p for p in w['parts'] if p.get('type') == 'kanji']
        for p in ks:
            c = p['char']
            if c not in chars:
                chars.append(c)
                part_meaning[c] = p.get('meaning') or ''
            words_by[c].append(w)
            if p.get('used_type') == 'onyomi' and p.get('used_reading'):
                used_on[c].add(p['used_reading'])
            if p.get('used_type') == 'kunyomi' and p.get('used_reading'):
                used_kun[c].add(p['used_reading'])
            if len(ks) == 1:
                standalone[c] = (w['word'], w['reading'])

    entries = {}

    def label_meaning(ch):
        """Component label + WaniKani/site meaning, with alias handling."""
        lab = ch
        m = D.meaning(ch)
        if m is None:
            raise SystemExit(f'No traceable meaning for component {ch!r}')
        return lab, m

    def add_comp(ch, role, reading=None, note=None):
        lab, m = label_meaning(ch)
        c = {'label': lab, 'meaning': m, 'role': role}
        if reading:
            c['reading'] = reading
        if note:
            c['note'] = note
        return c

    def kun_phrase(kun_list):
        ks = kun_list[:2]
        if not ks:
            return ''
        if len(ks) == 1:
            return f"The native kun reading is {ks[0]}."
        return f"The native kun readings are {', '.join(ks)}."

    def wcomp_entry(ci, role='part', note=None):
        lab = ci['char'] if ci['char'] else ci['meaning']
        c = {'label': lab, 'meaning': ci['meaning'], 'role': role}
        if note:
            c['note'] = note
        return c

    for c in chars:
        e = D.K.get(c)
        meaning = primary(e) if e else part_meaning.get(c) or ''
        comps = D.wk_comps(c) if e else []
        on_all = D.onyomi(c)
        kun_all = D.kunyomi(c)
        on_used = sorted(used_on[c])
        kun_used = sorted(used_kun[c])
        word = words_by[c][0]
        word_pair = f"{word['word']} ({word['reading']})"
        kun_word = next((w for w in words_by[c]
                         if any(p.get('char') == c and p.get('used_type') == 'kunyomi'
                                for p in w['parts'])), None)
        on_word = next((w for w in words_by[c]
                        if any(p.get('char') == c and p.get('used_type') == 'onyomi'
                               for p in w['parts'])), None)

        entry = {'kind': 'opaque', 'meaning': meaning, 'components': [],
                 'meaning_line': '', 'reading_line': ''}

        # ---- phono-semantic ----
        if c in PHONO:
            snd, snd_reading, mcomp, family, specific = PHONO[c]
            # Components: true decomposition where curated, else WaniKani.
            if c in PHONO_COMPS:
                comp_list = PHONO_COMPS[c]
            elif comps:
                comp_list = [x['char'] if x['char'] else x['meaning'] for x in comps]
            else:
                comp_list = [mcomp, snd]
            for ch in comp_list:
                if ch == snd:
                    role = 'both' if c in ('買', '働') else 'sound'
                    note = 'also the meaning side' if role == 'both' else None
                    entry['components'].append(
                        add_comp(ch, role, snd_reading, note))
                elif ch == mcomp:
                    entry['components'].append(add_comp(ch, 'meaning'))
                else:
                    entry['components'].append(add_comp(ch, 'part'))
            # Ensure both key components are present even for odd WaniKani lists.
            labs = [x['label'] for x in entry['components']]
            if snd not in labs:
                entry['components'].insert(0, add_comp(
                    snd, 'both' if c in ('買', '働') else 'sound', snd_reading))
            if mcomp and mcomp not in labs:
                entry['components'].insert(0, add_comp(mcomp, 'meaning'))
            entry['kind'] = 'ideograph' if c == '買' else 'phono-semantic'
            if c == '買':
                for comp in entry['components']:
                    if comp['label'] == '罒':
                        comp['role'] = 'part'
                    if comp['label'] == '貝':
                        comp['role'] = 'both'
                        comp['note'] = 'also shell money'
                entry['meaning_line'] = (
                    '罒 (Net) + 貝 (Shellfish; also shell money) → buy; 貝 also '
                    'supplies ばい.'
                )
            elif c == '働':
                entry['meaning_line'] = (
                    'ｲ (Leader) is the person side; 動 (Move) supplies both "move" '
                    'and the sound どう → a person moving → work; 働 is a '
                    'Japanese-made kanji.'
                )
            else:
                entry['meaning_line'] = (
                    f"{label_meaning(mcomp)[0]} ({label_meaning(mcomp)[1]}) is the "
                    f"meaning side ({family}); {label_meaning(snd)[0]} "
                    f"({label_meaning(snd)[1]}) is the sound component, giving "
                    f"{snd_reading}. {specific}"
                ).replace('  ', ' ')
            # reading line
            parts = [f"The on reading {snd_reading} comes from the sound component "
                     f"{snd}."]
            if on_used and on_used[0] != snd_reading:
                ow = on_word or word
                parts.append(f"{ow['word']} ({ow['reading']}) uses {on_used[0]}, a "
                             f"shift from {snd_reading}.")
            elif not on_used and on_all and snd_reading not in on_all:
                parts.append(f"The kanji's on reading is {on_all[0]}.")
            if c == '迷':
                parts.append("The standard on is めい; まい survives in 迷子.")
            if c in RESTORED_NOTE:
                parts.append(RESTORED_NOTE[c])
            if kun_used and kun_word:
                parts.append(f"{kun_word['word']} ({kun_word['reading']}) uses the "
                             f"native kun reading, tied to the meaning.")
            if kun_all and not kun_used:
                parts.append(kun_phrase(kun_all))
            entry['reading_line'] = ' '.join(parts)
            entry['_sound'] = snd
            entries[c] = entry
            continue

        # ---- ideograph ----
        if c in IDEO:
            comp_chars, gloss = IDEO[c]
            entry['kind'] = 'ideograph'
            for i, ch in enumerate(comp_chars):
                note = None
                if c == '国' and ch == '口' and i == 0:
                    note = 'here = enclosure 囗, not "mouth"'
                elif c == '回' and i == 0:
                    note = 'outer 口 is the enclosure 囗, not "mouth"'
                elif c == '句' and ch == '勹':
                    note = 'here = wrap, not "prison"'
                elif c == '外' and ch == 'ト':
                    note = 'here = divination 卜, not "toe"'
                elif c == '屈' and ch == '尸':
                    note = 'here = body, not "flag"'
                elif c in ('上', '下') and ch == 'ト':
                    note = 'here = mark, not "toe"'
                elif c == '体' and ch == '本':
                    note = 'here = root, not "book"'
                elif c == '打' and ch == '丁':
                    note = 'here = nail, not "street"'
                elif c == '友' and ch == 'ナ':
                    note = 'here = hand'
                elif c == '国' and ch == '王':
                    note = 'with 丶 this is 玉 (jade)'
                elif c == '祭' and ch == '示':
                    note = 'here = altar, not "jackhammer"'
                entry['components'].append(add_comp(ch, 'part', note=note))
            entry['meaning_line'] = (
                ' + '.join(f"{ch} ({label_meaning(ch)[1]})" for ch in comp_chars)
                + f" → {gloss}."
            )
            if c == '回':
                entry['meaning_line'] = (
                    'An inner 口 (mouth/vessel) inside an enclosure 囗 → go around; '
                    'a turn; a time.'
                )
            on_txt = on_used[0] if on_used else (on_all[0] if on_all else '')
            bits = []
            if on_txt:
                bits.append(f"On {on_txt} is learned with the kanji; the parts give "
                            f"the meaning, not the sound.")
            if kun_used and kun_word:
                bits.append(f"{kun_word['word']} ({kun_word['reading']}) uses the "
                            f"native kun reading, tied to the meaning.")
            if kun_all and not kun_used:
                bits.append(kun_phrase(kun_all))
            if not bits:
                bits.append("The reading is learned with the kanji; kun readings are "
                            "tied to the meaning, not derived from the parts.")
            entry['reading_line'] = ' '.join(bits)
            entries[c] = entry
            continue

        # ---- pictograph ----
        if c in PICTO:
            entry['kind'] = 'pictograph'
            if comps:
                for ci in comps:
                    entry['components'].append(wcomp_entry(ci))
            else:
                entry['components'].append(add_comp(c, 'part'))
            entry['meaning_line'] = PICTO[c]
            on_txt = on_used[0] if on_used else (on_all[0] if on_all else '')
            bits = []
            if on_txt:
                bits.append(f"On {on_txt} is learned with the kanji — the shape gives "
                            f"the meaning, not the sound.")
            if kun_used and kun_word:
                bits.append(f"{kun_word['word']} ({kun_word['reading']}) uses the "
                            f"native kun reading, tied to the meaning.")
            if kun_all and not kun_used:
                bits.append(kun_phrase(kun_all))
            if not bits:
                bits.append("The reading is learned with the kanji; the shape gives the "
                            "meaning, not the sound.")
            entry['reading_line'] = ' '.join(bits)
            entries[c] = entry
            continue

        # ---- 々 ----
        if c == '々':
            entry['kind'] = 'opaque'
            entry['components'] = [{'label': '々', 'meaning': 'Repeater', 'role': 'part'}]
            entry['meaning_line'] = (
                '々 is not a kanji with a meaning of its own: it repeats the preceding '
                'kanji (人々 = ひとびと).'
            )
            entry['reading_line'] = (
                'No reading of its own — it repeats the preceding kanji\'s reading.'
            )
            entries[c] = entry
            continue

        # ---- opaque (generic) ----
        entry['kind'] = 'opaque'
        # 填 has no WaniKani kanji subject; its true parts are 土 + 真.
        if c == '填':
            for ch in ('土', '真'):
                entry['components'].append(add_comp(ch, 'meaning' if ch == '土' else 'part'))
        else:
            for ci in comps:
                entry['components'].append(wcomp_entry(ci))
        if c == '充':
            entry['components'] = [add_comp('亠', 'part'), add_comp('厶', 'part'),
                                   add_comp('儿', 'part')]
        custom = CUSTOM_OPAQUE.get(c)
        if custom:
            for comp in entry['components']:
                comp['role'] = 'part'
            if custom.get('meaning_comp'):
                for comp in entry['components']:
                    if comp['label'] == custom['meaning_comp']:
                        comp['role'] = 'meaning'
            entry['meaning_line'] = custom['line']
        else:
            # Pick a semantic radical for the hook.
            radical = None
            for comp in entry['components']:
                ch = comp['label']
                key = ch if ch in FIELD else ALIAS.get(ch, ch)
                if key in FIELD:
                    radical = comp
                    break
            if radical is not None:
                radical['role'] = 'meaning'
                rl = radical['label']
                rm = radical['meaning']
                field = FIELD.get(rl, FIELD.get(ALIAS.get(rl, rl), 'meaning field'))
                entry['meaning_line'] = (
                    f"{rl} ({rm}) is the semantic side ({field}); the rest of the modern "
                    f"shape does not compose \"{meaning}\" — learn it with {word_pair}."
                )
            else:
                labs = ', '.join(x['label'] for x in entry['components'][:3])
                entry['meaning_line'] = (
                    f"The modern parts ({labs}) do not compose \"{meaning}\" — learn "
                    f"{c} as a whole with {word_pair}."
                )
        # reading line
        near = NEAR.get(c)
        on_txt = on_used[0] if on_used else (on_all[0] if on_all else '')
        bits = []
        if custom and custom.get('reading'):
            bits.append(custom['reading'])
        elif near:
            bits.append(near)
        elif on_txt:
            bits.append(f"On {on_txt}: no component here carries it exactly; the on is "
                        f"learned with the kanji.")
        if kun_used and kun_word:
            bits.append(f"{kun_word['word']} ({kun_word['reading']}) uses the native "
                        f"kun reading, tied to the meaning.")
        if kun_all and not kun_used:
            bits.append(kun_phrase(kun_all))
        if not bits:
            bits.append('The reading is learned with the kanji; no component carries it.')
        entry['reading_line'] = ' '.join(bits)
        entries[c] = entry

    # ---- cross references for sound components ----
    for c, entry in entries.items():
        snd = entry.get('_sound')
        if not snd:
            continue
        same = []
        for d, other in entries.items():
            if d == c:
                continue
            labs = [x['label'] for x in other['components']]
            if snd not in labs:
                continue
            exact = other.get('_sound') == snd
            near = (not exact) and NEAR.get(d, '').startswith(snd)
            if not (exact or near):
                continue
            reading = ''
            if exact:
                for x in other['components']:
                    if x['label'] == snd and x.get('reading'):
                        reading = x['reading']
            if not reading:
                # Give the other kanji's first on reading as context.
                oo = sorted(used_on[d]) or D.onyomi(d)
                reading = oo[0] if oo else ''
            same.append({'kanji': d, 'reading': reading, 'exact': exact,
                         'words': [{'word': w['word'], 'reading': w['reading']}
                                   for w in words_by[d][:3]]})
        if same:
            entry['sound'] = {'label': snd,
                              'reading': next((x.get('reading') for x in entry['components']
                                               if x['label'] == snd), ''),
                              'same': same}

    # ---- write ----
    for entry in entries.values():
        entry.pop('_sound', None)
    with open(args.out, 'w', encoding='utf-8') as f:
        json.dump(entries, f, ensure_ascii=False, indent=1)
        f.write('\n')

    # ---- checks ----
    kinds = collections.Counter(e['kind'] for e in entries.values())
    print(f'wrote {len(entries)} entries to {args.out}')
    print('kinds:', dict(kinds))
    missing = [c for c in chars if c not in entries]
    print('missing:', missing)
    bad = []
    for c, e in entries.items():
        if not e['components'] or not e['meaning_line'] or not e['reading_line']:
            bad.append(c)
    print('empty fields:', bad)
    # sound verification
    errs = []
    for c, e in entries.items():
        for comp in e['components']:
            if comp['role'] in ('sound', 'both'):
                claimed = comp.get('reading')
                ons = D.onyomi(comp['label'])
                if not claimed or claimed not in ons:
                    errs.append((c, comp['label'], claimed, ons))
    print('sound verification errors:', errs)
    # traceability
    terr = []
    for c, e in entries.items():
        for comp in e['components']:
            if D.meaning(comp['label']) is None:
                # Image-only radicals have no characters field; their label is
                # the WaniKani meaning name itself, which is the source.
                if comp['label'] == comp['meaning'] or comp['label'] == '々':
                    continue
                terr.append((c, comp['label'], comp['meaning']))
            elif D.meaning(comp['label']) != comp['meaning'] and comp['label'] != '々':
                # curriculum name can differ from WaniKani; report for review
                terr.append((c, comp['label'], comp['meaning'], D.meaning(comp['label'])))
    print('traceability mismatches:', terr)



# ---------------------------------------------------------------------------
# Opaque entries whose WaniKani component list would otherwise suggest a false
# semantic radical. Each line says plainly what the parts do and do not do.
# `meaning_comp` names the component (if any) that really is the semantic side.
# `reading` overrides the generated reading line.
# ---------------------------------------------------------------------------
CUSTOM_OPAQUE = {
    '声': {'line': '声 is a simplified form of 聲; the modern parts (士, 尸, 丨) do not compose "voice" — learn 声 with 声優 (せいゆう).'},
    '充': {'line': '亠 + 厶 + 儿 are the modern strokes of 充; they do not compose "allocate" — learn 充 as a whole with 充電 (じゅうでん).'},
    '者': {'line': '者 is learned as a whole; its old form is 耂 + 日, but the modern parts do not spell "someone" — learn 者 with 医者 (いしゃ).'},
    '真': {'line': '真 is a simplified 眞; the modern parts do not compose "reality" — learn it with 写真 (しゃしん).'},
    '点': {'line': '点 is a simplified 點; 灬 (fire) is the semantic side, 占 the sound source (せん) — てん is not an exact key.', 'meaning_comp': '灬', 'reading': 'On てん: 占 (せん) is the historical sound source, not exact.'},
    '驚': {'line': '馬 (horse) is the meaning side — a horse shying; 敬 is the historical sound source (けい), not exact for きょう.', 'meaning_comp': '馬', 'reading': 'On きょう: 敬 (けい) is the historical sound source, not exact.'},
    '着': {'line': '着 is a simplified variant of 著; the modern parts (丷, 王, 丿, 目) do not compose "wear" — learn it with 着物 (きもの).'},
    '写': {'line': '写 is a simplified form of 寫; 冖 (cover) is the modern radical, but the parts do not compose "copy" — learn 写 with 写真 (しゃしん).'},
    '図': {'line': '図 is a simplified 圖; the outer 口 is the enclosure 囗, the inside is a reduced 冬 — no component spells "diagram".', 'reading': 'On ず: 図 is a simplified 圖; no sound component survives. 図 (ず) is the word here.'},
    '期': {'line': '月 (month) is the meaning side — a period of time; 其 (き) is the sound source, but WaniKani gives 其 no kanji reading — unverified.', 'meaning_comp': '月', 'reading': 'On き: 其 (き) is the sound source, but WaniKani gives 其 no kanji reading — unverified.'},
    '病': {'line': '疒 (sick) is the meaning side; 丙 (へい) matches one on reading, but WaniKani gives 丙 no kanji reading — unverified, and the words here use びょう.', 'meaning_comp': '疒', 'reading': 'On びょう: 丙 (へい) is a historical sound source, but へい is not びょう — no exact key.'},
    '医': {'line': '匚 (box) holds 矢 (arrow) — a medicine case; 医 is a simplified 醫, no exact sound key for い.', 'meaning_comp': '匚'},
    '笑': {'line': '竹 (bamboo) + 天/夭 — the parts do not compose "laugh"; the old form is unclear — learn 笑う (わらう).'},
    '冗': {'line': 'The modern parts (冖, 几) do not compose "superfluous" — learn 冗談 (じょうだん).'},
    '慢': {'line': '忄 (heart) is the meaning side; 曼 has the sound まん, but WaniKani splits it and gives no kanji reading — unverified.', 'meaning_comp': '忄', 'reading': 'On まん: 曼 is the sound source, but WaniKani gives 曼 no kanji reading — unverified.'},
    '到': {'line': '至 (arrive) is the meaning side; 刂 is the right-hand part — 到 means "arrive"; no exact sound key for とう.', 'meaning_comp': '至'},
    '努': {'line': '力 (power) is the meaning side — effort; 奴 gives the sense of forced toil; no exact sound key for ど.', 'meaning_comp': '力'},
    '常': {'line': '巾 (cloth) is the meaning side — 常 originally a skirt; 尚 is the sound source (しょう), not exact for じょう.', 'meaning_comp': '巾', 'reading': 'On じょう: 尚 (しょう) is the historical sound source, not exact; 常 means "normal".'},
    '事': {'line': 'The modern parts (十, 口, ヨ) do not compose "occurrence" — learn it with 工事 (こうじ).'},
    '前': {'line': '前 is 丷 + 一 + 月 (a reduced 舟, boat) + 刂; the modern parts do not compose "front" — learn 前 (まえ).'},
    '台': {'line': '台 = ム + 口; the modern parts do not compose "stand/machine" — learn 台所 (だいどころ).'},
    '所': {'line': '戸 (door) + 斤 (axe) — the modern parts do not compose "place"; learn 台所 (だいどころ).'},
    '風': {'line': '風 = 几 + 丿 + 虫; the modern parts do not compose "wind" — learn 風呂 (ふろ).'},
    '越': {'line': '走 (run) is the meaning side; 成 is the phonetic remnant, not exact for えつ.', 'meaning_comp': '走'},
    '具': {'line': '具 = 目 + 一 + ハ (hands holding a vessel); the modern parts do not compose "tool" — learn 家具 (かぐ).'},
    '親': {'line': '見 (see) is the meaning side; 亲 (しん) is the sound source, but WaniKani splits it into 立+木; 親 means "parent".', 'meaning_comp': '見', 'reading': 'On しん: 亲 (しん) is the sound source, but WaniKani splits it and gives no kanji subject — unverified.'},
    '先': {'line': '先 = 丿 + 土 + 儿; the modern parts do not compose "previous" — learn 先生 (せんせい).'},
    '的': {'line': '白 (white/bright) is the meaning side — a bright target; 勺 gives しゃく, not exact for てき.', 'meaning_comp': '白', 'reading': 'On てき: 勺 (しゃく) is the historical sound source, not exact; 的 means "target".'},
    '売': {'line': '売 is a simplified 賣; the modern parts do not compose "sell" — learn 売れる (うれる).'},
    '超': {'line': '走 (run) is the meaning side; 召 (しょう) is the sound source, not exact for ちょう.', 'meaning_comp': '走', 'reading': 'On ちょう: 召 (しょう) is the historical sound source, not exact.'},
    '建': {'line': '建 = 廴 (the long-stride radical) + 聿 (brush); the parts suggest setting something up, but no exact sound key for けん.', 'meaning_comp': '廴'},
    '決': {'line': '氵 (water) is the meaning side; the right side is 夬 (not 人+ユ) — 夬 has the sound けつ, but WaniKani gives it no kanji reading — unverified.', 'meaning_comp': '氵', 'reading': 'On けつ: 夬 is the sound source, but WaniKani gives 夬 no kanji reading — unverified.'},
    '柔': {'line': '木 (wood) is the material side — soft wood; 矛 (spear) gives the shape; 柔 means "gentle".', 'meaning_comp': '木'},
    '居': {'line': '尸 (building/body) + 古 (old) — the modern parts do not compose "reside"; learn 居間 (いま).', 'meaning_comp': '尸'},
    '院': {'line': '阝 (place) is the meaning side; 完 (かん) is the historical sound source, not exact for いん — 院 means "institution".', 'meaning_comp': '阝'},
}


if __name__ == '__main__':
    main()
