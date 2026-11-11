#!/usr/bin/env python3
"""Generate one-line Bangladeshi Bangla glosses of every kanji's meanings.

The kanji set comes from the site's own curriculum (data/curriculum.json), so
subject ids, characters and the English meanings are exactly what the build
uses. Each result is appended to data/meanings_bn.json under its WaniKani
subject id:

    {"<subject_id>": {"meaning_bn": "..."}}

The meanings are taken in the same order the site displays and accepts them:
the primary gloss (split on its own "/", ";" and "," separators) followed by
the secondary WaniKani meanings, de-duplicated. One Bangla gloss per English
meaning, joined with ", ". The file is keyed by subject id, never by
curriculum order, so it survives WaniKani cache rebuilds.

Only the local Ollama daemon is used (http://127.0.0.1:11434 by default).

Usage:
    python3 tools/gen_meanings_bn.py           # every missing kanji
    python3 tools/gen_meanings_bn.py --week 1  # one week only
"""

import argparse
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from http.client import HTTPException
from pathlib import Path
from urllib import error, request

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from build import load_curriculum  # noqa: E402

OUT_FILE = BASE_DIR / "data" / "meanings_bn.json"
FAIL_LOG = BASE_DIR / "tools" / "gen_meanings_bn_failures.log"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = "deepseek-v4.1-flash:cloud"
MAX_IN_FLIGHT = 3
ATTEMPTS = 3          # the first call plus two retries
REQUEST_TIMEOUT = 300

ANY_TAG = re.compile(r"<[^>]+>")


def non_bangla_letter(text):
    """True if the text contains a letter outside the Bengali block."""
    return any(ch.isalpha() and not ("ঀ" <= ch <= "৿") for ch in text)


# The model drifts between spellings of the two loanwords the site uses
# everywhere; keep one form so a lesson never shows কানজি and কাঞ্জি together.
WORD_FIXES = (
    ("কান্জি", "কাঞ্জি"),
    ("কানজি", "কাঞ্জি"),
    ("রেডিক্যাল", "র্যাডিক্যাল"),
    ("র‍্যাডিক্যাল", "র্যাডিক্যাল"),
)

SYSTEM = """You write short Bangla meaning glosses for a Japanese kanji study site used by learners in Bangladesh.

Non-negotiable rules:
- You are given the English meanings of ONE kanji, in order. Translate EACH entry into Bangla and return the translations in the SAME order, joined with ", " (comma and space). Never add, drop, merge or reorder entries.
- Use Bangladeshi Bangla only (Dhaka standard চলিত). Use everyday Bangladeshi vocabulary: পানি for water (never জল). Avoid Kolkata-style tatsama-heavy diction and West-Bengal-only words.
- Short dictionary equivalents, not sentences. No explanations, no examples, no notes.
- For verb and adjective meanings use the natural Bangla dictionary form (e.g. "to push" → ধাক্কা দেওয়া, "dangerous" → বিপজ্জনক).
- Bangla script only (U+0980–U+09FF). Never write Latin, Devanagari, kanji or kana; if an English meaning names a Japanese thing, gloss it in Bangla instead.
- Plain text only: no HTML, no tags, no markdown, no bullet points, one single line.
- Reply with strict JSON only, exactly this shape:
  {"meaning_bn": "..."}"""


def split_top(text, separators):
    """Split on separators that sit outside parentheses."""
    out = []
    current = ""
    depth = 0
    for ch in text:
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        if depth == 0 and ch in separators:
            out.append(current)
            current = ""
        else:
            current += ch
    out.append(current)
    return out


def meaning_entries(kanji):
    """The kanji's English meanings, primary first then secondary, in order."""
    entries = []
    seen = set()

    def add(value):
        value = (value or "").strip()
        if value and value.lower() not in seen:
            seen.add(value.lower())
            entries.append(value)

    # "a / b / c" separates whole glosses; a bare slash ("made in/of",
    # "breathe/inhale") is part of one gloss and is left alone.
    primary = (kanji.get("meaning") or "").replace(" / ", ";")
    for segment in split_top(primary, ";"):
        for part in split_top(segment, ","):
            add(part)
    for secondary in kanji.get("meanings") or []:
        add(secondary)
    return entries


def build_prompt(item):
    return "\n".join([
        f"CHARACTER: {item['char']}",
        "ENGLISH MEANINGS (in order): " +
        json.dumps(item["meanings"], ensure_ascii=False),
        "",
        'For every entry above give its Bangla translation, in the same order, '
        'joined with ", ".',
    ])


def collect_items(curriculum, week):
    """Walk the kanji records build.py renders, keyed by source id."""
    items = []
    seen = set()
    for wk in curriculum["weeks"]:
        if week is not None and wk["week"] != week:
            continue
        for kanji in wk["kanji"]:
            subject_id = str(kanji["id"])
            if subject_id in seen:
                continue
            seen.add(subject_id)
            items.append({
                "id": subject_id,
                "char": kanji["char"],
                "meanings": meaning_entries(kanji),
            })
    return items


def load_overlay():
    if not OUT_FILE.exists():
        return {}
    try:
        data = json.loads(OUT_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"{OUT_FILE} is not valid JSON: {e}")
    return data if isinstance(data, dict) else {}


def save_overlay(overlay):
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = OUT_FILE.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(overlay, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    os.replace(tmp, OUT_FILE)


def clean_text(text):
    if not isinstance(text, str):
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\n", " ")
    text = ANY_TAG.sub("", text)
    for old, new in WORD_FIXES:
        text = text.replace(old, new)
    return re.sub(r"\s+", " ", text).strip()


def parse_response(content):
    text = (content or "").strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    match = re.search(r"\{.*\}", text, re.S)
    if not match:
        raise ValueError("no JSON object in reply")
    payload = json.loads(match.group(0))
    if not isinstance(payload, dict):
        raise ValueError("reply JSON is not an object")
    return payload


def validate(item, payload):
    meaning_bn = clean_text(payload.get("meaning_bn"))
    if not meaning_bn:
        raise ValueError("empty meaning_bn")
    if ANY_TAG.search(meaning_bn) or non_bangla_letter(meaning_bn):
        raise ValueError("meaning_bn is not plain Bangla-script text")
    return {"meaning_bn": meaning_bn}


def call_ollama(item):
    body = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt(item)},
        ],
        "options": {"temperature": 0.2},
    }
    req = request.Request(
        OLLAMA_URL + "/api/chat",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return (payload.get("message") or {}).get("content") or ""


def generate(item):
    last = None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return validate(item, parse_response(call_ollama(item)))
        except (error.URLError, error.HTTPError, HTTPException, TimeoutError,
                OSError, ValueError, json.JSONDecodeError) as e:
            last = e
            if attempt < ATTEMPTS:
                time.sleep(2.0 * attempt)
    raise RuntimeError(str(last))


def log_failure(item, exc):
    FAIL_LOG.parent.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with FAIL_LOG.open("a", encoding="utf-8") as fh:
        fh.write(
            f"{stamp} | id={item['id']} | char={item['char']!r} | "
            f"{type(exc).__name__}: {exc}\n"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate Bangladeshi Bangla meaning glosses via local Ollama.")
    parser.add_argument("--week", type=int, default=None,
                        help="only this week's kanji (default: all missing)")
    args = parser.parse_args(argv)

    curriculum = load_curriculum()
    if args.week is not None and not any(
            w["week"] == args.week for w in curriculum["weeks"]):
        raise SystemExit(f"week {args.week} is not in data/curriculum.json")

    items = collect_items(curriculum, args.week)
    overlay = load_overlay()
    missing = [it for it in items if it["id"] not in overlay]

    scope = f"week {args.week}" if args.week is not None else "all weeks"
    print(f"{scope}: {len(items)} kanji, {len(items) - len(missing)} already done, "
          f"{len(missing)} to generate", flush=True)

    if not missing:
        print("Nothing to do.")
        return 0

    succeeded = failed = 0
    done = 0
    failure_items = []

    with ThreadPoolExecutor(max_workers=MAX_IN_FLIGHT) as pool:
        futures = {pool.submit(generate, it): it for it in missing}
        for future in as_completed(futures):
            item = futures[future]
            try:
                entry = future.result()
            except Exception as exc:  # noqa: BLE001 — keep going on any failure
                failed += 1
                failure_items.append((item, exc))
                log_failure(item, exc)
                print(f"  FAIL {item['id']} {item['char']}: {exc}", flush=True)
                continue
            overlay[item["id"]] = entry
            save_overlay(overlay)
            succeeded += 1
            done += 1
            if done % 10 == 0 or done == len(missing):
                print(f"  {done}/{len(missing)} done "
                      f"({succeeded} ok, {failed} failed)", flush=True)

    print(f"\nattempted {len(missing)} | succeeded {succeeded} | failed {failed}")
    if failure_items:
        print("failures:")
        for item, exc in failure_items:
            print(f"  id={item['id']} char={item['char']!r}: {exc}")
        print(f"details appended to {FAIL_LOG}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
