#!/usr/bin/env python3
"""Refresh vocabulary part glosses with standard dictionary senses (Kanjium).

The original vocab data carried WaniKani title-case meanings ("Western Style")
in its part list.  Each word's meaning_logic already explains which sense of a
kanji the word uses, e.g. "金 (gold, money)".  This tool maps that explanation
onto the exact Kanjium senses, stores them in the part list, and rewrites the
parenthetical to match.  Readings and reading splits are not touched.

Usage:
    python3 tools/refresh_vocab_glosses.py --kanjium PATH [--check] [--out PATH]
"""
import argparse
import json
import os
import re
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
VOCAB = BASE / "data" / "vocab_learn_2025_12.json"
LOGIC = BASE / "data" / "kanji_logic.json"
STOP = {"also", "here", "sense", "senses", "as", "in", "the", "of", "with",
        "part", "to", "a", "an", "or", "and", "its", "this", "that", "from"}


def tokens(text):
    return [w.lower() for w in re.findall(r"[A-Za-z]{3,}", text or "")
            if w.lower() not in STOP]


def match_senses(senses, hint):
    """Return up to two Kanjium senses named in the explanation."""
    toks = tokens(hint)
    picked = []
    for t in toks:
        for s in senses:
            sl = s.lower()
            if (t == sl or t in sl.split() or sl in t) and s not in picked:
                picked.append(s)
                break
        if len(picked) == 2:
            break
    return picked


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vocab", default=str(VOCAB))
    ap.add_argument("--logic", default=str(LOGIC))
    ap.add_argument("--kanjium", default=os.environ.get("KANJIUM_DB"))
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    if not args.kanjium:
        raise SystemExit("--kanjium (or KANJIUM_DB) is required")

    vocab = json.loads(Path(args.vocab).read_text(encoding="utf-8"))
    logic = json.loads(Path(args.logic).read_text(encoding="utf-8"))
    db = sqlite3.connect(args.kanjium)
    db.row_factory = sqlite3.Row
    senses = {}
    for row in db.execute("SELECT kanji, meaning FROM kanjidict"):
        senses[row["kanji"]] = [s.strip() for s in (row["meaning"] or "").split(";")
                                if s.strip()]

    changed_parts = 0
    changed_logic = 0
    for word in vocab:
        logic_text = word.get("meaning_logic", "")
        for part in word.get("parts", []):
            if part.get("type") != "kanji":
                continue
            ch = part["char"]
            if ch == "々":
                gloss = "iteration mark"
            else:
                m = re.search(re.escape(ch) + r"\s*\(([^)]*)\)", logic_text)
                hint = m.group(1) if m else ""
                picked = match_senses(senses.get(ch, []), hint)
                if picked:
                    gloss = "; ".join(picked)
                else:
                    gloss = (logic.get(ch) or {}).get("meaning") or part.get("meaning", "")
            if part.get("meaning") != gloss:
                if args.check:
                    print("%s: %s %r -> %r" % (word["word"], ch,
                                               part.get("meaning"), gloss))
                part["meaning"] = gloss
                changed_parts += 1
        new_logic = logic_text
        for part in word.get("parts", []):
            if part.get("type") != "kanji":
                continue
            ch = part["char"]
            gloss = part.get("meaning") or ""
            if not gloss:
                continue
            pat = re.compile(r"(" + re.escape(ch) + r"\s*\()([^)]*)(\))")
            new_logic, n = pat.subn(lambda m: m.group(1) + gloss + m.group(3),
                                    new_logic)
            changed_logic += n
        if new_logic != logic_text:
            word["meaning_logic"] = new_logic

    print("part glosses changed: %d" % changed_parts)
    print("meaning_logic fragments changed: %d" % changed_logic)
    if args.check:
        return 0
    out = Path(args.out) if args.out else Path(args.vocab)
    out.write_text(json.dumps(vocab, ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    print("wrote", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
