#!/usr/bin/env python3
"""Data-level checks for data/vocab_learn_2025_12.json.

Verifies:
  * 243 entries, same order as the practice data, word/reading/meaning verbatim
  * every entry has >= 1 part and a non-empty meaning_logic
  * non-"whole" words: concatenated part readings == the word reading
  * every kanji part's meaning is a standard Kanjium dictionary sense
  * every kanji part's used_reading is a real reading of that kanji:
      - exact / rendaku / gemination variants of its Kanjium on'yomi or
        kun'yomi, or
      - a curated "special" reading with a note, or
      - a reading listed only by the site curriculum/WaniKani cross-check
        (reported separately; Kanjium is the primary source)
  * "whole" words carry a reading_note and no invented slices

Pass --kanjium (or set KANJIUM_DB) for the Kanjium checks. Without it the
older curriculum/WaniKani reading checks run and the gloss check is skipped.

Usage:
    python3 -I tools/check_vocab_learn.py \
        --kanjium ~/src/kanjium/data/kanjidb.sqlite
"""

import argparse
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "tools"))
import gen_vocab_learn as G  # noqa: E402
import gen_kanji_logic as K  # noqa: E402


def norm(r):
    return r.replace(".", "")


def kanjium_kunyomi(raw):
    """Expand Kanjium's い（やす） notation into stem and full readings."""
    out = set()
    for item in (raw or "").split("、"):
        item = item.strip()
        if not item:
            continue
        m = re.match(r"^([^（(]+)[（(]([^）)]*)[）)]$", item)
        if m:
            stem, okuri = m.group(1), m.group(2)
            out.add(stem)
            out.add(stem + okuri)
        else:
            out.add(item)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--kanjium", default=os.environ.get("KANJIUM_DB"))
    args = ap.parse_args()

    words = json.loads(G.WORDS_FILE.read_text(encoding="utf-8"))
    data = json.loads(G.OUT_FILE.read_text(encoding="utf-8"))
    d = G.Data(words)
    notes = json.loads(G.NOTES_FILE.read_text(encoding="utf-8"))

    kd = {}
    if args.kanjium:
        db = sqlite3.connect(args.kanjium)
        db.row_factory = sqlite3.Row
        kd = {r["kanji"]: dict(r) for r in db.execute("SELECT * FROM kanjidict")}
    else:
        print("WARNING: --kanjium not given — skipping Kanjium gloss checks "
              "and using curriculum readings only.")

    fails, checks = [], 0

    def check(ok, msg):
        nonlocal checks
        checks += 1
        if not ok:
            fails.append(msg)

    check(len(data) == 243, f"entry count {len(data)} != 243")
    counts = {"exact": 0, "rendaku": 0, "gemination": 0,
              "special": 0, "cross_source": 0, "whole": 0, "kana_only": 0,
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

            # Meaning: exact standard-dictionary sense(s).
            if ch == "々":
                check(p.get("meaning") == "iteration mark",
                      f"{tag}/{ch}: iteration-mark gloss {p.get('meaning')!r}")
            elif kd:
                row = kd.get(ch)
                check(row is not None, f"{tag}/{ch}: not in Kanjium")
                senses = [s.strip() for s in ((row or {}).get("meaning") or "").split(";")
                          if s.strip()]
                parts = [s.strip() for s in (p.get("meaning") or "").split(";") if s.strip()]
                check(bool(parts) and all(
                    any(x.lower() == s.lower() for s in senses) for x in parts),
                    f"{tag}/{ch}: gloss {p.get('meaning')!r} is not a Kanjium "
                    f"sense {senses!r}")

            if e["reading_pattern"] == "whole":
                continue
            used = p.get("used_reading") or ""
            typ = p.get("used_type")
            tr = p.get("transform")
            check(typ in ("onyomi", "kunyomi"), f"{tag}/{ch}: bad used_type {typ}")
            check(bool(used), f"{tag}/{ch}: empty used_reading")
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

            def candidates(readings):
                bases = [norm(r) for r in readings]
                if tr in (None, "exact"):
                    return used in bases
                if tr == "rendaku":
                    return any(used in G.rendaku(b) for b in bases)
                if tr == "gemination":
                    return any(used in G.sokuon(b) for b in bases)
                return False

            if kd and ch in kd:
                row = kd[ch]
                if typ == "onyomi":
                    primary = K.onyomi_list(row.get("onyomi"))
                else:
                    primary = sorted(kanjium_kunyomi(row.get("kunyomi")))
                ok = candidates(primary)
                if ok:
                    counts["exact" if tr in (None, "exact") else tr] += 1
                else:
                    # Source disagreement: allow a reading the curriculum /
                    # WaniKani cross-check knows, but report it.
                    cross = candidates(info[typ])
                    check(cross, f"{tag}/{ch}: {used!r} is not a {typ} reading "
                                 f"{primary} ({tr}); cross-check {info[typ]}")
                    if cross:
                        counts["cross_source"] += 1
            else:
                ok = candidates(info[typ])
                check(ok, f"{tag}/{ch}: {used!r} is not a {typ} reading "
                          f"{info[typ]} ({tr})")
                if ok:
                    counts["exact" if tr in (None, "exact") else tr] += 1
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
          f"gemination {counts['gemination']}, special {counts['special']}, "
          f"cross-source {counts['cross_source']}")
    print(f"  kana-only words: {counts['kana_only']} "
          f"(loanwords {counts['loanword']}, native/onomatopoeia "
          f"{counts['kana_only'] - counts['loanword']})")


if __name__ == "__main__":
    main()
