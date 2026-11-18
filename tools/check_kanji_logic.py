#!/usr/bin/env python3
"""Data-level checks for data/kanji_logic.json.

Verifies:
  * one entry for every distinct kanji part in vocab_learn_2025_12.json
  * every entry has >= 1 component, a valid role, and non-empty lines
  * every component label/meaning is traceable to a WaniKani subject or the
    site curriculum (image-only radicals use their meaning name as the label)
  * every "sound" / "both" component's claimed reading is an exact WaniKani
    on'yomi of that component kanji
  * every sound cross-reference points at another kanji in the same 243-word
    set and at words that really occur in that set

The WaniKani checks need the full subject dump. Pass --subjects PATH, or let
the default (~/workspace/wanikani-clone/data/subjects.json) resolve. If the
dump is absent the structural checks still run and the WaniKani checks are
reported as skipped.

Usage:
    python3 tools/check_kanji_logic.py [--subjects PATH] [--logic PATH]
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

KINDS = {"phono-semantic", "ideograph", "pictograph", "opaque"}
ROLES = {"sound", "meaning", "both", "part"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--subjects", default=G.DEFAULT_SUBJECTS)
    ap.add_argument("--logic", default=str(BASE / "data" / "kanji_logic.json"))
    args = ap.parse_args()

    logic = json.loads(Path(args.logic).read_text(encoding="utf-8"))
    words = json.loads((BASE / "data" / "vocab_learn_2025_12.json")
                       .read_text(encoding="utf-8"))

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

    have_subjects = os.path.exists(args.subjects)
    D = G.Data(args.subjects) if have_subjects else None
    if not have_subjects:
        print("WARNING: %s not found — skipping WaniKani reading/traceability "
              "checks." % args.subjects)

    kinds = collections.Counter()
    sound_claims = 0
    verified = 0
    cross_exact = 0
    cross_near = 0

    for c in chars:
        e = logic.get(c)
        if not isinstance(e, dict):
            check(False, "%s: missing or not an object" % c)
            continue
        tag = c
        kind = e.get("kind")
        check(kind in KINDS, "%s: bad kind %r" % (tag, kind))
        kinds[kind] += 1
        check(bool(str(e.get("meaning") or "").strip()), "%s: empty meaning" % tag)

        ml = str(e.get("meaning_line") or "")
        rl = str(e.get("reading_line") or "")
        check(bool(ml.strip()), "%s: empty meaning_line" % tag)
        check(bool(rl.strip()), "%s: empty reading_line" % tag)
        check("\n" not in ml and "\n" not in rl, "%s: line break in a line" % tag)
        check("WaniKati" not in ml + rl and "WaniKai" not in ml + rl,
              "%s: misspelled WaniKani" % tag)

        comps = e.get("components")
        check(isinstance(comps, list) and len(comps) >= 1,
              "%s: no components" % tag)
        for comp in comps or []:
            label = comp.get("label")
            meaning = comp.get("meaning")
            role = comp.get("role")
            check(bool(str(label or "").strip()), "%s: empty component label" % tag)
            check(bool(str(meaning or "").strip()), "%s: empty component meaning" % tag)
            check(role in ROLES, "%s: bad role %r on %r" % (tag, role, label))
            if D and label:
                resolved = D.meaning(label)
                check(resolved is not None or label == meaning or label == "々",
                      "%s: untraceable component %r" % (tag, label))
            if role in ("sound", "both"):
                sound_claims += 1
                claimed = comp.get("reading")
                check(bool(claimed), "%s: sound component %r has no reading" %
                      (tag, label))
                if D and claimed:
                    ons = D.onyomi(label)
                    check(claimed in ons,
                          "%s: sound claim %r not in WaniKani on'yomi %r for %r" %
                          (tag, claimed, ons, label))
                    if claimed in ons:
                        verified += 1

        s = e.get("sound")
        if s:
            check(bool(s.get("label")), "%s: sound block has no label" % tag)
            check(bool(s.get("reading")), "%s: sound block has no reading" % tag)
            seen = set()
            for x in s.get("same") or []:
                other = x.get("kanji")
                check(other in logic, "%s: cross-ref %r not in logic" % (tag, other))
                check(other not in seen, "%s: duplicate cross-ref %r" % (tag, other))
                seen.add(other)
                exact = x.get("exact")
                check(isinstance(exact, bool), "%s: cross-ref %r exact not bool" %
                      (tag, other))
                if exact:
                    cross_exact += 1
                    osound = (logic.get(other) or {}).get("sound") or {}
                    check(osound.get("label") == s.get("label"),
                          "%s: exact cross-ref %r does not use sound %r" %
                          (tag, other, s.get("label")))
                else:
                    cross_near += 1
                for w in x.get("words") or []:
                    check((w.get("word"), w.get("reading")) in word_pairs,
                          "%s: cross-ref word %r/%r not in the 243-word set" %
                          (tag, w.get("word"), w.get("reading")))

    extra = sorted(set(logic) - set(chars))
    check(not extra, "extra entries not in the word set: %r" % extra)

    print("coverage: %d/%d distinct kanji" % (len(set(chars) & set(logic)), len(chars)))
    print("kinds:", dict(kinds))
    print("sound claims: %d; exact WaniKani matches: %d" % (sound_claims, verified))
    print("sound cross-refs: %d exact, %d near" % (cross_exact, cross_near))
    print("checks: %d; failures: %d" % (checks[0], len(fails)))
    for msg in fails[:50]:
        print("FAIL:", msg)
    if fails:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
