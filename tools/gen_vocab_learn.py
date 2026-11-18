#!/usr/bin/env python3
"""Generate data/vocab_learn_2025_12.json — the logical breakdowns behind the
243 Dec 2025 vocab words.

Sources:
  data/vocab_practice_2025_12.json      word / reading / meaning (verbatim)
  data/curriculum.json                  the site's 293 kanji (gloss + readings)
  wanikani-clone/data/subjects.json     WaniKani kanji subjects (gloss + readings)
  tools/vocab_learn_notes.json          curated meaning_logic / reading notes

The alignment (which slice of the word's reading each kanji contributes) is
solved here, not hand-written: a small dynamic program matches each kanji's
known readings (on'yomi / kun'yomi, plus rendaku and gemination variants)
against the word's reading, with kana chunks matched literally. Words that do
not align are flagged reading_pattern "whole" and carry a reading_note instead
of invented slices — 3 words (昨日, 今朝, 今日) in this set.

Usage:
    python3 tools/gen_vocab_learn.py
"""

import json
import re
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
WORDS_FILE = BASE_DIR / "data" / "vocab_practice_2025_12.json"
CUR_FILE = BASE_DIR / "data" / "curriculum.json"
NOTES_FILE = BASE_DIR / "tools" / "vocab_learn_notes.json"
OUT_FILE = BASE_DIR / "data" / "vocab_learn_2025_12.json"
SUBS_FILE = Path.home() / "workspace" / "wanikani-clone" / "data" / "subjects.json"


def is_kanji(c):
    return 0x4E00 <= ord(c) <= 0x9FFF


VOICE = {"か": "が", "き": "ぎ", "く": "ぐ", "け": "げ", "こ": "ご",
         "さ": "ざ", "し": "じ", "す": "ず", "せ": "ぜ", "そ": "ぞ",
         "た": "だ", "ち": "ぢ", "つ": "づ", "て": "で", "と": "ど",
         "は": "ば", "ひ": "び", "ふ": "ぶ", "へ": "べ", "ほ": "ぼ"}
SEMI = {"は": "ぱ", "ひ": "ぴ", "ふ": "ぷ", "へ": "ぺ", "ほ": "ぽ"}

# Kanji absent from WaniKani: documented dictionary facts, marked source
# "dictionary" in the output so the check can see the exception explicitly.
EXTRA_KANJI = {
    "填": {"meaning": "fill in", "onyomi": ["てん"], "kunyomi": []},
}

# Real readings that WaniKani does not list for the kanji, used by one word
# each. They are carried as used_type "special" with the fact in `note`.
SPECIAL_READINGS = {
    ("迷", "まい"): {"type": "onyomi",
                    "note": "on'yomi めい, contracted to まい in this word."},
    ("中", "じゅう"): {"type": "onyomi",
                     "note": "read じゅう here, meaning ‘throughout (the year)’ — usual readings ちゅう / なか."},
    ("側", "ぎわ"): {"type": "kunyomi",
                    "note": "compound form of かわ / がわ ‘side’ — here ぎわ."},
}

OVERRIDES = {
    "建物": {
        "pattern": "kun-kun",
        "parts": [
            {"char": "建", "used_reading": "たて", "used_type": "kunyomi",
             "note": "kun'yomi た.てる — the て stays inside the compound (たて + もの)."},
            {"char": "物", "used_reading": "もの", "used_type": "kunyomi"},
        ],
    },
    "充填": {
        "pattern": "on-on",
        "parts": [
            {"char": "充", "used_reading": "じゅう", "used_type": "onyomi"},
            {"char": "填", "used_reading": "てん", "used_type": "onyomi",
             "source": "dictionary",
             "note": "WaniKani does not teach 填; on'yomi てん, gloss ‘fill in’ (dictionary fact)."},
        ],
    },
}

KANA_CLASS = {
    "マンション": "loanword", "パソコン": "loanword", "キーボード": "loanword",
    "ホテル": "loanword", "ガイダンス": "loanword", "アナウンス": "loanword",
    "コマーシャル": "loanword", "スピーチ": "loanword", "エアコン": "loanword",
    "タオル": "loanword", "キッチン": "loanword", "ペン": "loanword",
    "インターネット": "loanword",
    "ぺらぺら": "onomatopoeia", "からから": "onomatopoeia",
    "ぺこぺこ": "onomatopoeia", "どきどき": "onomatopoeia",
}


def reading_variants(r):
    return [r.replace(".", ""), r.split(".")[0]] if "." in r else [r]


def rendaku(r):
    out = set()
    if not r:
        return out
    for table in (VOICE, SEMI):
        if r[0] in table:
            out.add(table[r[0]] + r[1:])
    return out


def sokuon(r):
    return {r[:-1] + "っ"} if r and r[-1] in "くつちき" else set()


class Data:
    def __init__(self, words):
        self.words = words
        self.cur = json.loads(CUR_FILE.read_text(encoding="utf-8"))
        self.subs = json.loads(SUBS_FILE.read_text(encoding="utf-8"))["data"]
        self.curk = {k["char"]: k for w in self.cur["weeks"] for k in w["kanji"]}
        self.wkk = {}
        self.wkv = {}
        for s in self.subs:
            if s["object"] == "kanji":
                self.wkk[s["data"]["characters"]] = s["data"]
            elif s["object"] in ("vocabulary", "kana_vocabulary"):
                self.wkv.setdefault(s["data"]["characters"], []).append(s["data"])

    def info(self, ch):
        if ch in EXTRA_KANJI:
            e = EXTRA_KANJI[ch]
            return {"meaning": e["meaning"], "onyomi": e["onyomi"],
                    "kunyomi": e["kunyomi"], "source": "dictionary"}
        c = self.curk.get(ch)
        if c:
            ms = c.get("meanings") or []
            one = c.get("meaning") or ""
            clean = bool(one) and not re.search(r"[/;,]", one)
            return {"meaning": one if clean else (ms[0] if ms else one),
                    "onyomi": list(c.get("onyomi_all") or []),
                    "kunyomi": list(c.get("kunyomi_all") or []),
                    "source": "curriculum"}
        w = self.wkk.get(ch)
        if w:
            primary = [m["meaning"] for m in w["meanings"] if m.get("primary")]
            ms = primary or [m["meaning"] for m in w["meanings"]]
            return {"meaning": ms[0] if ms else None,
                    "onyomi": [r["reading"] for r in w["readings"] if r["type"] == "onyomi"],
                    "kunyomi": [r["reading"] for r in w["readings"] if r["type"] == "kunyomi"],
                    "source": "wanikani"}
        return {"meaning": None, "onyomi": [], "kunyomi": [], "source": "missing"}

    def candidates(self, ch, with_transforms=True):
        info = self.info(ch)
        out, seen = [], set()

        def add(sl, typ, tr):
            key = (sl, typ, tr)
            if key in seen:
                return
            seen.add(key)
            out.append({"slice": sl, "type": typ, "transform": tr})

        for typ in ("onyomi", "kunyomi"):
            for r in info[typ]:
                for base in reading_variants(r):
                    add(base, typ, None)
                    if not with_transforms:
                        continue
                    for v in rendaku(base):
                        add(v, typ, "rendaku")
                    for v in sokuon(base):
                        add(v, typ, "gemination")
                    for rv in rendaku(base):
                        for v in sokuon(rv):
                            add(v, typ, "gemination+rendaku")
        for (c, sl), spec in SPECIAL_READINGS.items():
            if c == ch:
                add(sl, spec["type"], "special")
        return out

    def tokenize(self, word):
        toks, i = [], 0
        while i < len(word):
            c = word[i]
            if is_kanji(c):
                toks.append(("kanji", c))
                i += 1
            elif c == "々":
                toks.append(("iter", "々"))
                i += 1
            else:
                j = i
                while j < len(word) and not is_kanji(word[j]) and word[j] != "々":
                    j += 1
                toks.append(("kana", word[i:j]))
                i = j
        return toks

    def align(self, word, reading):
        toks = self.tokenize(word)
        cands = []
        for idx, (typ, text) in enumerate(toks):
            if typ == "kana":
                cands.append([{"slice": text, "type": "kana", "transform": None}])
            elif typ == "iter":
                prev = word[idx - 1]
                cands.append([dict(c, transform=(c["transform"] or "iteration"))
                              for c in self.candidates(prev)])
            else:
                cands.append(self.candidates(text))
        cost = {"exact": 0, "rendaku": 1, "gemination": 2,
                "gemination+rendaku": 3, "special": 1}
        best = [[None] * (len(reading) + 1) for _ in range(len(toks) + 1)]
        best[0][0] = (0, [])
        for ti, (typ, text) in enumerate(toks):
            for pos in range(len(reading) + 1):
                if best[ti][pos] is None:
                    continue
                cur_cost, path = best[ti][pos]
                for cand in cands[ti]:
                    s = cand["slice"]
                    if not reading.startswith(s, pos):
                        continue
                    np = pos + len(s)
                    nc = cur_cost + cost.get(cand["transform"] or "exact", 0)
                    if best[ti + 1][np] is None or nc < best[ti + 1][np][0]:
                        best[ti + 1][np] = (nc, path + [cand])
        return best[len(toks)][len(reading)]

    def transform_note(self, ch, cand):
        tr = cand["transform"]
        if tr in (None, "exact", "special"):
            return None
        info = self.info(ch)
        used = cand["slice"]
        for typ in ("onyomi", "kunyomi"):
            for r in info[typ]:
                for base in reading_variants(r):
                    if tr == "rendaku" and used in rendaku(base):
                        return f"rendaku: {base} → {used}"
                    if tr == "gemination" and used in sokuon(base):
                        return f"shortened from {base} (before the next sound)"
                    if tr == "gemination+rendaku":
                        for rv in rendaku(base):
                            if used in sokuon(rv):
                                return f"shortened and voiced: {base} → {used}"
        return f"sound change: {used}"


def pattern_for(parts):
    types = [p["used_type"] for p in parts if p.get("used_type") in ("onyomi", "kunyomi")]
    if not types:
        return "whole"
    if all(t == "onyomi" for t in types):
        return "on-on"
    if all(t == "kunyomi" for t in types):
        return "kun-kun"
    return "on-kun" if types[0] == "onyomi" else "kun-on"


def build():
    words = json.loads(WORDS_FILE.read_text(encoding="utf-8"))
    notes = json.loads(NOTES_FILE.read_text(encoding="utf-8"))
    d = Data(words)
    out = []
    stats = {"exact": 0, "rendaku": 0, "gemination": 0,
             "gemination+rendaku": 0, "special": 0, "whole": 0,
             "kana": 0, "loanword": 0}

    for w in words:
        word, reading, meaning = w["word"], w["reading"], w["meaning"]
        note = notes.get(word) or {}
        if not note.get("meaning_logic"):
            raise SystemExit(f"missing meaning_logic for {word}")
        entry = {"word": word, "reading": reading, "meaning": meaning}

        if not w["has_kanji"]:
            cls = KANA_CLASS.get(word, "native")
            entry["kana_class"] = cls
            entry["parts"] = [{"type": "kana", "text": word}]
            entry["meaning_logic"] = note["meaning_logic"]
            entry["reading_pattern"] = "loanword" if cls == "loanword" else "kana"
            stats[entry["reading_pattern"]] += 1
            out.append(entry)
            continue

        if word in OVERRIDES:
            spec = OVERRIDES[word]
            parts = []
            for p in spec["parts"]:
                info = d.info(p["char"])
                item = {"char": p["char"], "type": "kanji",
                        "meaning": info["meaning"],
                        "onyomi": info["onyomi"], "kunyomi": info["kunyomi"],
                        "used_reading": p["used_reading"],
                        "used_type": p["used_type"]}
                if p.get("source"):
                    item["source"] = p["source"]
                if p.get("note"):
                    item["note"] = p["note"]
                parts.append(item)
            entry["parts"] = parts
            entry["reading_pattern"] = spec["pattern"]
            stats["exact"] += len(parts)
        else:
            res = d.align(word, reading)
            if res is None:
                parts = []
                for typ, text in d.tokenize(word):
                    if typ == "kana":
                        parts.append({"type": "kana", "text": text})
                    else:
                        info = d.info(text)
                        parts.append({"char": text, "type": "kanji",
                                      "meaning": info["meaning"],
                                      "onyomi": info["onyomi"],
                                      "kunyomi": info["kunyomi"],
                                      "unsegmented": True})
                entry["parts"] = parts
                entry["reading_pattern"] = "whole"
                stats["whole"] += 1
                if not note.get("reading_note"):
                    raise SystemExit(f"whole word without reading_note: {word}")
            else:
                path = res[1]
                toks = d.tokenize(word)
                parts = []
                for (typ, text), cand in zip(toks, path):
                    if typ == "kana":
                        parts.append({"type": "kana", "text": cand["slice"]})
                        continue
                    info = d.info(text)
                    item = {"char": text, "type": "kanji",
                            "meaning": info["meaning"],
                            "onyomi": info["onyomi"], "kunyomi": info["kunyomi"],
                            "used_reading": cand["slice"],
                            "used_type": cand["type"]}
                    tr = cand["transform"]
                    if tr and tr not in ("exact", "iteration"):
                        item["transform"] = tr
                    pn = (note.get("part_notes") or {}).get(
                        str([p.get("char") for p in parts].count(text) if False else 0))
                    parts.append(item)
                # part notes are keyed by part index in the notes file
                for idx, pnote in (note.get("part_notes") or {}).items():
                    i = int(idx)
                    if 0 <= i < len(parts) and parts[i].get("type") == "kanji":
                        parts[i]["note"] = pnote
                    elif 0 <= i < len(parts):
                        parts[i]["note"] = pnote
                for item in parts:
                    if item.get("type") != "kanji":
                        continue
                    tr = item.get("transform")
                    if tr and "note" not in item:
                        ch = item["char"]
                        cand = next(c for c in d.candidates(ch)
                                    if c["slice"] == item["used_reading"]
                                    and c["transform"] == tr)
                        tn = d.transform_note(ch, cand)
                        if tn:
                            item["note"] = tn
                    stats[tr if tr in stats else "exact"] += 1
                entry["parts"] = parts
                entry["reading_pattern"] = pattern_for(parts)

        if note.get("reading_note"):
            entry["reading_note"] = note["reading_note"]
        entry["meaning_logic"] = note["meaning_logic"]
        out.append(entry)

    # ---- validation ----
    errors = []
    for e, w in zip(out, words):
        parts = e["parts"]
        if not parts:
            errors.append(f"{e['word']}: empty parts")
        if not e.get("meaning_logic"):
            errors.append(f"{e['word']}: empty meaning_logic")
        if e["reading_pattern"] not in ("on-on", "kun-kun", "on-kun", "kun-on",
                                        "whole", "kana", "loanword"):
            errors.append(f"{e['word']}: bad pattern {e['reading_pattern']}")
        if e["reading_pattern"] != "whole":
            joined = "".join(p.get("used_reading", p.get("text", "")) for p in parts)
            if joined != e["reading"]:
                errors.append(f"{e['word']}: joined readings {joined!r} != {e['reading']!r}")
        for p in parts:
            if p.get("type") == "kanji" and not p.get("unsegmented"):
                if not p.get("used_reading") or not p.get("used_type"):
                    errors.append(f"{e['word']}/{p['char']}: missing slice/type")
                if not p.get("meaning"):
                    errors.append(f"{e['word']}/{p['char']}: missing meaning")
            if p.get("type") == "kana" and not p.get("text"):
                errors.append(f"{e['word']}: empty kana part")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        raise SystemExit(f"{len(errors)} validation errors")

    OUT_FILE.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")

    # ---- cross-check against WaniKani vocabulary readings ----
    vocab_hits = vocab_miss = 0
    for e in out:
        entries = d.wkv.get(e["word"], [])
        if not entries:
            continue
        accepted = [r["reading"] for v in entries for r in (v.get("readings") or [])]
        if not accepted:
            continue
        if e["reading"] in accepted:
            vocab_hits += 1
        else:
            vocab_miss += 1
            print(f"  WK vocabulary reading mismatch: {e['word']} {e['reading']} vs {accepted}")
    print(f"Wrote {len(out)} entries -> {OUT_FILE}")
    print(f"WaniKani vocabulary cross-check: {vocab_hits} matched, {vocab_miss} mismatched")
    print("Coverage:", {k: stats[k] for k in
                        ("exact", "rendaku", "gemination", "gemination+rendaku",
                         "special", "whole", "kana", "loanword")})


if __name__ == "__main__":
    build()
