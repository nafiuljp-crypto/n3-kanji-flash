#!/usr/bin/env python3
"""Data-level checks for data/vocab_learn_2025_12.json.

Verifies, against the local sources:
  * 243 entries, same order as the practice data, word/reading/meaning verbatim
  * every entry has >= 1 part and a non-empty meaning_logic
  * non-"whole" words: concatenated part readings == the word reading
  * every kanji part's used_reading is a real reading of that kanji:
      - exact / rendaku / gemination variants of its WaniKani or curriculum
        on'yomi / kun'yomi, or
      - a curated "special" reading with a note, or
      - a documented dictionary source (填, which WaniKani does not teach)
  * every kanji part's meaning is the primary WaniKani or curriculum gloss
  * "whole" words carry a reading_note and no invented slices

Usage:
    python3 tools/check_vocab_learn.py
"""

import json
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "tools"))
import gen_vocab_learn as G  # noqa: E402


def norm(r):
    return r.replace(".", "")


def main():
    words = json.loads(G.WORDS_FILE.read_text(encoding="utf-8"))
    data = json.loads(G.OUT_FILE.read_text(encoding="utf-8"))
    d = G.Data(words)
    notes = json.loads(G.NOTES_FILE.read_text(encoding="utf-8"))

    fails, checks = [], 0

    def check(ok, msg):
        nonlocal checks
        checks += 1
        if not ok:
            fails.append(msg)

    check(len(data) == 243, f"entry count {len(data)} != 243")
    counts = {"exact": 0, "rendaku": 0, "gemination": 0,
              "special": 0, "whole": 0, "kana_only": 0,
              "kanji_words": 0, "loanword": 0}

    for i, (e, w) in enumerate(zip(data, words)):
        tag = f"#{i+1} {e.get('word')}"
        check(e.get("word") == w["word"], f"{tag}: word mismatch")
        check(e.get("reading") == w["reading"], f"{tag}: reading mismatch")
        check(e.get("meaning") == w["meaning"], f"{tag}: meaning mismatch")
        check(bool(e.get("parts")), f"{tag}: empty parts")
        check(bool((e.get("meaning_logic") or "").strip()), f"{tag}: empty meaning_logic")
        check(e.get("reading_pattern") in ("on-on", "kun-kun", "on-kun", "kun-on",
                                           "whole", "kana", "loanword"),
              f"{tag}: bad reading_pattern {e.get('reading_pattern')}")

        if not w["has_kanji"]:
            counts["kana_only"] += 1
            if e["reading_pattern"] == "loanword":
                counts["loanword"] += 1
            check(e["reading_pattern"] in ("kana", "loanword"),
                  f"{tag}: kana word pattern {e['reading_pattern']}")
            check(len(e["parts"]) == 1 and e["parts"][0].get("type") == "kana",
                  f"{tag}: kana word parts")
            check(bool(e.get("kana_class")), f"{tag}: missing kana_class")
            continue

        counts["kanji_words"] += 1
        if e["reading_pattern"] == "whole":
            counts["whole"] += 1
            check(bool(e.get("reading_note")), f"{tag}: whole without reading_note")
            check(all("used_reading" not in p for p in e["parts"]),
                  f"{tag}: whole word has fake slices")
        else:
            joined = "".join(p.get("used_reading", p.get("text", "")) for p in e["parts"])
            check(joined == e["reading"],
                  f"{tag}: joined {joined!r} != {e['reading']!r}")

        for p in e["parts"]:
            if p.get("type") == "kana":
                check(bool(p.get("text")), f"{tag}: empty kana chunk")
                continue
            ch = p.get("char")
            check(bool(ch), f"{tag}: kanji part without char")
            if not ch:
                continue
            info = d.info(ch)
            # meaning: exact primary gloss from WaniKani / curriculum
            if ch in G.EXTRA_KANJI:
                ok = p.get("meaning") == G.EXTRA_KANJI[ch]["meaning"]
                check(ok, f"{tag}/{ch}: dictionary gloss mismatch {p.get('meaning')!r}")
            else:
                check(p.get("meaning") == info["meaning"],
                      f"{tag}/{ch}: meaning {p.get('meaning')!r} != primary {info['meaning']!r}")
            if e["reading_pattern"] == "whole":
                continue
            used = p.get("used_reading") or ""
            typ = p.get("used_type")
            tr = p.get("transform")
            check(typ in ("onyomi", "kunyomi"), f"{tag}/{ch}: bad used_type {typ}")
            check(bool(used), f"{tag}/{ch}: empty used_reading")
            if ch in G.EXTRA_KANJI:
                check(used in info[typ], f"{tag}/{ch}: dictionary reading mismatch")
                continue
            if ch == "々":
                prev = [q for q in e["parts"] if q.get("type") == "kanji"
                        and q is not p]
                prev_used = prev[-1].get("used_reading", "") if prev else ""
                ok = bool(prev_used) and (used == prev_used or
                                          used in G.rendaku(prev_used))
                check(ok, f"{tag}/{ch}: iteration reading {used!r} does not repeat "
                          f"{prev_used!r}")
                counts["rendaku"] += 1
                continue
            if ch == "建" and used == "たて":
                # kun'yomi た.てる: the okurigana て stays inside 建物
                check(bool(p.get("note")), f"{tag}/{ch}: override without note")
                counts["exact"] += 1
                continue
            spec = G.SPECIAL_READINGS.get((ch, used))
            if tr == "special":
                check(bool(spec) and spec["type"] == typ,
                      f"{tag}/{ch}: special reading not in allowlist")
                check(bool(p.get("note")), f"{tag}/{ch}: special reading without note")
                counts["special"] += 1
                continue
            bases = [norm(r) for r in info[typ]]
            if tr in (None, "exact"):
                ok = used in bases
                if ok:
                    counts["exact"] += 1
            elif tr == "rendaku":
                ok = any(used in G.rendaku(b) for b in bases)
                if ok:
                    counts["rendaku"] += 1
            elif tr == "gemination":
                ok = any(used in G.sokuon(b) for b in bases)
                if ok:
                    counts["gemination"] += 1
            else:
                ok = False
            check(ok, f"{tag}/{ch}: {used!r} is not a {typ} reading {bases} ({tr})")
            if tr in ("rendaku", "gemination"):
                check(bool(p.get("note")), f"{tag}/{ch}: {tr} without note")

    print(f"checks run: {checks}   passed: {checks - len(fails)}   failed: {len(fails)}")
    if fails:
        print("\n".join(fails[:40]))
        raise SystemExit(1)
    print("decomposition coverage:")
    print(f"  kanji words: {counts['kanji_words']} "
          f"(fully split: {counts['kanji_words'] - counts['whole']}, whole: {counts['whole']})")
    print(f"  kanji parts: exact {counts['exact']}, rendaku {counts['rendaku']}, "
          f"gemination {counts['gemination']}, special {counts['special']}")
    print(f"  kana-only words: {counts['kana_only']} "
          f"(loanwords {counts['loanword']}, native/onomatopoeia "
          f"{counts['kana_only'] - counts['loanword']})")


if __name__ == "__main__":
    main()
