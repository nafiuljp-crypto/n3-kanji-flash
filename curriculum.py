#!/usr/bin/env python3
"""Build the study curriculum: six weeks → radicals → kanji → vocabulary.

Source of the language data is the WaniKani subject cache (see wanikani.py).
The six Sou Matome weeks decide which kanji belong to which week; everything
else is derived:

  * radicals — every WaniKani radical used to build that week's kanji,
    de-duplicated, in order of first appearance.
  * vocabulary — WaniKani vocabulary whose kanji are all in the N3 set, filed
    under the latest week among the kanji it uses, so nothing is shown before
    its parts have been studied.

Output: data/curriculum.json
"""

import json

from datetime import datetime, timezone
from pathlib import Path

from wanikani import DATA_DIR, load_cache

OUT = DATA_DIR / "curriculum.json"
WEEKS = 6


def load_weeks():
    weeks = {}
    for w in range(1, WEEKS + 1):
        path = DATA_DIR / f"week_{w}.json"
        if path.exists():
            weeks[w] = json.loads(path.read_text(encoding="utf-8"))
    return weeks


def build():
    subjects = load_cache()
    by_id = subjects
    kanji_by_char = {s["characters"]: s for s in subjects.values()
                     if s["type"] == "kanji" and s["characters"]}

    weeks = load_weeks()

    # char → week, in study order within the week
    char_week = {}
    week_kanji = {}
    for w, data in weeks.items():
        entries = []
        for lesson in data.get("lessons", []):
            for k in lesson.get("kanji", []):
                char = k.get("char")
                if not char or char in char_week:
                    continue
                char_week[char] = w
                subject = kanji_by_char.get(char)
                entry = {
                    "char": char,
                    "day": lesson.get("day"),
                    "meaning": k.get("meaning"),
                    "stroke": k.get("stroke"),
                    "onyomi": k.get("onyomi"),
                    "kunyomi": k.get("kunyomi"),
                    "compounds": k.get("compounds", []),
                    "example": k.get("example"),
                }
                if subject:
                    entry.update({
                        "id": subject["id"],
                        "level": subject["level"],
                        "url": subject["document_url"],
                        "meanings": subject["meanings"],
                        "readings": subject["onyomi"] + subject["kunyomi"],
                        "onyomi_all": subject["onyomi"],
                        "kunyomi_all": subject["kunyomi"],
                        "radical_ids": subject["components"],
                    })
                entries.append(entry)
        week_kanji[w] = entries

    n3_chars = set(char_week)

    # Radicals are taught once, in the week where they first appear; later
    # weeks reuse them. Each kanji also lists the radicals it is built from.
    intro_week = {}
    radical_info = {}
    for w in sorted(week_kanji):
        for e in week_kanji[w]:
            for rid in e.get("radical_ids", []):
                subject = by_id.get(rid)
                if not subject or subject["type"] != "radical":
                    continue
                if rid not in radical_info:
                    radical_info[rid] = {
                        "id": rid,
                        "char": subject["characters"],
                        "image": subject["image"] if not subject["characters"] else None,
                        "meaning": subject["primary_meaning"],
                        "meanings": subject["meanings"],
                        "slug": subject["slug"],
                        "url": subject["document_url"],
                    }
                    intro_week[rid] = w
        week_kanji[w] = week_kanji[w]

    week_radicals = {w: [] for w in week_kanji}
    for rid, week in sorted(intro_week.items(), key=lambda kv: (kv[1], kv[0])):
        week_radicals[week].append(radical_info[rid])

    for w, entries in week_kanji.items():
        for e in entries:
            e["radicals"] = [
                {
                    "char": radical_info[rid]["char"],
                    "image": radical_info[rid]["image"],
                    "meaning": radical_info[rid]["meaning"],
                    "week": intro_week[rid],
                }
                for rid in e.get("radical_ids", [])
                if rid in radical_info
            ]
            e.pop("radical_ids", None)

    # vocabulary filed under the latest week of the kanji it uses
    vocab_by_week = {w: [] for w in week_kanji}
    vocab_ids = set()
    for subject in subjects.values():
        if subject["type"] != "vocabulary" or not subject["characters"]:
            continue
        kanji_chars = []
        skip = False
        for cid in subject["components"]:
            comp = by_id.get(cid)
            if comp and comp["type"] == "kanji":
                char = comp["characters"]
                if char not in n3_chars:
                    skip = True
                    break
                kanji_chars.append(char)
        if skip or not kanji_chars or subject["id"] in vocab_ids:
            continue
        week = max(char_week[c] for c in kanji_chars)
        vocab_ids.add(subject["id"])
        vocab_by_week[week].append({
            "id": subject["id"],
            "char": subject["characters"],
            "reading": subject["primary_reading"],
            "readings": subject["onyomi"] + subject["kunyomi"]
                        if subject["onyomi"] or subject["kunyomi"]
                        else [subject["primary_reading"]],
            "meaning": subject["primary_meaning"],
            "meanings": subject["meanings"],
            "kanji": kanji_chars,
            "level": subject["level"],
            "url": subject["document_url"],
        })

    for w in vocab_by_week:
        vocab_by_week[w].sort(key=lambda v: (v["level"] or 99, v["char"]))

    data = {
        "source": "WaniKani API v2 subjects + Sou Matome N3 kanji list",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weeks": [
            {
                "week": w,
                "theme": weeks[w]["theme"],
                "radicals": week_radicals[w],
                "kanji": week_kanji[w],
                "vocab": vocab_by_week[w],
            }
            for w in sorted(week_kanji)
        ],
    }
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    return data


def main():
    data = build()
    total_r = total_k = total_v = 0
    for wk in data["weeks"]:
        r, k, v = len(wk["radicals"]), len(wk["kanji"]), len(wk["vocab"])
        total_r, total_k, total_v = total_r + r, total_k + k, total_v + v
        print(f"  week {wk['week']}: {r:3d} radicals {k:3d} kanji {v:4d} vocab")
    print(f"total: {total_r} radicals, {total_k} kanji, {total_v} vocab → {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
