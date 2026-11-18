#!/usr/bin/env python3
"""Data-level checks for data/kanji_logic.json (etymology schema).

What is checked
  * one entry for every distinct kanji part in vocab_learn_2025_12.json
  * type / type_label agreement and the component-role rules for each type
  * both prose lines present, free of wiki markup and of WaniKani wording
  * every phono-semantic entry has exactly one sound component, and the
    component's reading equals the verified sound claim
  * sound claims against Kanjium: the displayed reading must be one of the
    phonetic's established series readings; "exact" requires the kanji's own
    on'yomi to intersect those readings; "family" requires no intersection
    plus an explicit relation phrase
  * phonetic_series members belong to the 251-kanji set, share the phonetic,
    and quote words that really occur in the vocab set
  * component labels are traceable to KanjiVG / KRADFILE / Wiktionary
    decompositions (or carry an explicit historical note)

The corpus checks need the source files. Pass them explicitly, or set
KANJIVG_DIR, KANJIUM_DB, KRADFILE and WIKT_CACHE. Without them the structural
checks still run and the corpus checks are reported as skipped.

Usage:
    python3 -I tools/check_kanji_logic.py \
        --kanjivg ~/src/kanjivg --kanjium ~/src/kanjium/data/kanjidb.sqlite \
        --kradfile ~/src/kradfile-u.gz --wikt-cache ~/src/wikt
"""

import argparse
import collections
import json
import os
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE / "tools"))
import gen_kanji_logic as G  # noqa: E402

TYPES = {"phono-semantic", "compound", "pictograph", "ideograph", "opaque"}
ROLES = {"meaning", "sound", "part"}
SOURCES = {"KanjiVG", "Kanjium", "KRADFILE", "Wiktionary"}
TYPE_LABEL = G.TYPE_LABEL

# Glyph variants that stand for the same component in different fonts/forms.
FOLD = {
    "⺅": "亻", "氵": "水", "扌": "手", "忄": "心", "礻": "示", "衤": "衣",
    "刂": "刀", "⻏": "邑", "⻖": "阜", "艹": "艸", "⺾": "艸", "⺹": "艸",
    "⻌": "辶", "辶": "辶", "灬": "火", "罒": "网", "⺌": "小", "⺮": "竹",
    "耂": "老", "犭": "犬", "爫": "爪", "飠": "食", "釒": "金", "訁": "言",
    "糹": "糸", "王": "玉", "㚔": "幸", "冖": "宀",
}


def fold(label):
    return FOLD.get(label, label)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--logic", default=str(BASE / "data" / "kanji_logic.json"))
    ap.add_argument("--words", default=str(BASE / "data" / "vocab_learn_2025_12.json"))
    ap.add_argument("--kanjivg", default=os.environ.get("KANJIVG_DIR"))
    ap.add_argument("--kanjium", default=os.environ.get("KANJIUM_DB"))
    ap.add_argument("--kradfile", default=os.environ.get("KRADFILE"))
    ap.add_argument("--wikt-cache", default=os.environ.get("WIKT_CACHE"))
    args = ap.parse_args()

    logic = json.loads(Path(args.logic).read_text(encoding="utf-8"))
    words = json.loads(Path(args.words).read_text(encoding="utf-8"))

    chars = []
    for w in words:
        for p in w["parts"]:
            if p.get("type") == "kanji" and p["char"] not in chars:
                chars.append(p["char"])
    word_pairs = {(w["word"], w["reading"]) for w in words}

    fails = []
    checks = [0]

    def check(ok, msg):
        checks[0] += 1
        if not ok:
            fails.append(msg)

    check(isinstance(logic, dict), "logic is not a JSON object")
    check(set(logic) == set(chars),
          "coverage mismatch: missing=%r extra=%r" % (
              sorted(set(chars) - set(logic)), sorted(set(logic) - set(chars))))

    have_corpus = all([args.kanjivg, args.kanjium, args.kradfile, args.wikt_cache])
    src = None
    if have_corpus:
        src = G.Sources(args.kanjivg, args.kanjium, args.kradfile, args.wikt_cache)
    else:
        print("WARNING: source paths incomplete — skipping sound and "
              "traceability checks (need --kanjivg, --kanjium, --kradfile, "
              "--wikt-cache).")

    types = collections.Counter()
    sound_claims = 0
    exact = 0
    family = 0
    series_entries = 0
    series_members = 0
    trace = collections.Counter()

    for c in chars:
        e = logic.get(c)
        if not isinstance(e, dict):
            check(False, "%s: missing or not an object" % c)
            continue
        tag = c
        t = e.get("type")
        check(t in TYPES, "%s: bad type %r" % (tag, t))
        types[t] += 1
        check(e.get("type_label") == TYPE_LABEL.get(t),
              "%s: type_label %r does not match type %r" %
              (tag, e.get("type_label"), t))
        check(e.get("kind") == t, "%s: kind %r does not match type %r" %
              (tag, e.get("kind"), t))
        check(bool(e.get("sources")) and set(e["sources"]) <= SOURCES,
              "%s: bad sources %r" % (tag, e.get("sources")))
        if t == "opaque":
            check(c == "々", "%s: opaque is only expected for the iteration mark" % tag)
        else:
            check(bool(str(e.get("meaning") or "").strip()),
                  "%s: empty meaning" % tag)

        ml = str(e.get("meaning_line") or "")
        rl = str(e.get("reading_line") or "")
        check(bool(ml.strip()), "%s: empty meaning_line" % tag)
        check(bool(rl.strip()), "%s: empty reading_line" % tag)
        check("\n" not in ml and "\n" not in rl, "%s: line break in a line" % tag)
        for bad in ("{{", "}}", "[[", "]]", "WaniKani", "WaniKati"):
            check(bad not in ml + rl, "%s: %r leaked into a line" % (tag, bad))

        comps = e.get("components")
        check(isinstance(comps, list) and len(comps) >= 1,
              "%s: no components" % tag)
        comps = comps if isinstance(comps, list) else []
        role_counts = collections.Counter()
        for comp in comps:
            label = comp.get("label")
            meaning = comp.get("meaning")
            role = comp.get("role")
            check(bool(str(label or "").strip()), "%s: empty component label" % tag)
            check(bool(str(meaning or "").strip()), "%s: empty component meaning" % tag)
            check(role in ROLES, "%s: bad role %r on %r" % (tag, role, label))
            role_counts[role] += 1
            if role == "meaning":
                check(label in ml, "%s: meaning component %r missing from "
                      "meaning_line" % (tag, label))

        if t == "phono-semantic":
            check(role_counts["sound"] == 1,
                  "%s: phono-semantic needs one sound component, has %d" %
                  (tag, role_counts["sound"]))
            s = e.get("sound")
            check(isinstance(s, dict), "%s: phono-semantic without sound block" % tag)
        else:
            check(role_counts["sound"] == 0,
                  "%s: %s must not have sound components" % (tag, t))
            check("sound" not in e, "%s: %s must not have a sound block" % (tag, t))

        if t == "phono-semantic" and isinstance(e.get("sound"), dict):
            s = e["sound"]
            sound_claims += 1
            status = s.get("status")
            check(status in ("exact", "family"),
                  "%s: bad sound status %r" % (tag, status))
            check(bool(s.get("label")), "%s: sound block has no label" % tag)
            check(bool(s.get("reading")), "%s: sound block has no reading" % tag)
            check(bool(s.get("relation")), "%s: sound block has no relation" % tag)
            check(isinstance(s.get("phonetic_onyomi"), list)
                  and bool(s["phonetic_onyomi"]),
                  "%s: sound block has no phonetic_onyomi" % tag)
            comp = next((x for x in comps if x.get("role") == "sound"), {})
            check(s.get("label") == comp.get("label"),
                  "%s: sound label %r != component label %r" %
                  (tag, s.get("label"), comp.get("label")))
            check(s.get("reading") == comp.get("reading"),
                  "%s: sound reading %r != component reading %r" %
                  (tag, s.get("reading"), comp.get("reading")))
            check(s.get("reading") in (s.get("phonetic_onyomi") or []),
                  "%s: displayed reading not in phonetic_onyomi" % tag)
            check("← phonetic" in rl and str(s.get("label")) in rl,
                  "%s: reading_line does not name the phonetic" % tag)

            if src:
                preads = src.phonetic_readings(s.get("label"))
                preads_n = {G.norm_reading(x) for x in preads}
                check(G.norm_reading(s.get("reading")) in preads_n,
                      "%s: sound reading %r not an established series reading %r" %
                      (tag, s.get("reading"), preads))
                kanji_on = G.onyomi_list((src.kd.get(c) or {}).get("onyomi"))
                overlap = {G.norm_reading(x) for x in kanji_on} & preads_n
                if status == "exact":
                    exact += 1
                    check(bool(overlap),
                          "%s: claimed exact but %r has no reading in %r" %
                          (tag, kanji_on, preads))
                    check(s.get("relation") == "exact match in the series",
                          "%s: exact relation should be the standard phrase" % tag)
                elif status == "family":
                    family += 1
                    check(not overlap,
                          "%s: claimed family but exact overlap exists" % tag)
                    check("exact" not in str(s.get("relation")),
                          "%s: family relation claims an exact match" % tag)
                    check(any(w in str(s.get("relation")) for w in
                              ("series", "family", "voicing", "shortened",
                               "extended", "diverged")),
                          "%s: family relation is not described" % tag)

        ser = e.get("phonetic_series")
        if ser:
            series_entries += 1
            s = e.get("sound") or {}
            check(ser.get("label") == s.get("label"),
                  "%s: series label %r != sound label %r" %
                  (tag, ser.get("label"), s.get("label")))
            check(ser.get("reading") == s.get("reading"),
                  "%s: series reading %r != sound reading %r" %
                  (tag, ser.get("reading"), s.get("reading")))
            members = ser.get("members") or []
            check(bool(members), "%s: empty phonetic_series" % tag)
            seen = set()
            for m in members:
                series_members += 1
                other = m.get("kanji")
                check(other in logic, "%s: series member %r not in logic" %
                      (tag, other))
                check(other != c, "%s: series lists itself" % tag)
                check(other not in seen, "%s: duplicate series member %r" %
                      (tag, other))
                seen.add(other)
                os_ = (logic.get(other) or {}).get("sound") or {}
                check(os_.get("label") == ser.get("label"),
                      "%s: member %r does not use phonetic %r" %
                      (tag, other, ser.get("label")))
                check(isinstance(m.get("onyomi"), list) and bool(m["onyomi"]),
                      "%s: member %r has no on'yomi" % (tag, other))
                check(m.get("type") in TYPES, "%s: member %r has bad type" %
                      (tag, other))
                for w in m.get("words") or []:
                    check((w.get("word"), w.get("reading")) in word_pairs,
                          "%s: member word %r/%r is not in the vocab set" %
                          (tag, w.get("word"), w.get("reading")))

        if src:
            pool = set()
            trad = G.TRAD.get(c, c)
            for form in (c, trad):
                pool |= set(src.krad.get(form, []))
                pool |= {x["element"] for x in src.kanjivg_top(form)}
                comp = src.wikt_compound(form)
                if comp:
                    for i, a in enumerate(comp.get("args", []), 1):
                        pool.add(a)
                        alt = comp.get("alt%d" % i)
                        if alt:
                            pool.add(alt)
            pool = {fold(x) for x in pool} | {c, trad, "々"}
            wikt_text = src.wikt.get(trad, "") + src.wikt.get(c, "")
            for comp in comps:
                label = comp.get("label") or ""
                if fold(label) in pool:
                    trace["structure"] += 1
                elif label in wikt_text:
                    trace["wiktionary"] += 1
                elif comp.get("note"):
                    trace["noted"] += 1
                else:
                    trace["unresolved"] += 1
                    check(False, "%s: component %r has no KanjiVG/KRADFILE/"
                          "Wiktionary decomposition or note" % (tag, label))

    extra = sorted(set(logic) - set(chars))
    check(not extra, "extra entries not in the word set: %r" % extra)

    opaque = [(c, e.get("meaning_line", "")) for c, e in logic.items()
              if e.get("type") == "opaque"]

    print("coverage: %d/%d distinct kanji" % (len(set(chars) & set(logic)), len(chars)))
    print("types:", dict(types))
    print("sound claims: %d (%d exact, %d family)" % (sound_claims, exact, family))
    print("phonetic series: %d entries, %d member links" %
          (series_entries, series_members))
    if src:
        print("component traceability:", dict(trace))
    print("opaque: %d" % len(opaque))
    for c, reason in opaque:
        print("  opaque %s: %s" % (c, reason))
    print("checks: %d; failures: %d" % (checks[0], len(fails)))
    for msg in fails[:50]:
        print("FAIL:", msg)
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
