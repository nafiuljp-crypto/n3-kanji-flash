#!/usr/bin/env python3
"""Generate Bangladeshi Bangla mnemonics for the N3 Kanji study site.

The item set comes from the site's own build path (build.load_curriculum +
build.lesson_items), so subject ids, characters, meanings, readings and the
English WaniKani mnemonics are exactly what the pages render. Each result is
appended to data/mnemonics_bn.json under its WaniKani subject id:

    {"<subject_id>": {"meaning": "...", "reading": "..."}}

Radicals get "reading": null. The file is keyed by subject id, never by
curriculum order, so it survives WaniKani cache rebuilds.

Only the local Ollama daemon is used (http://127.0.0.1:11434 by default).

Usage:
    python3 tools/gen_mnemonics_bn.py           # every missing subject
    python3 tools/gen_mnemonics_bn.py --week 1  # one week only
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

from build import lesson_items, load_curriculum  # noqa: E402
from wanikani import load_cache  # noqa: E402

OUT_FILE = BASE_DIR / "data" / "mnemonics_bn.json"
FAIL_LOG = BASE_DIR / "tools" / "gen_bn_failures.log"

OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
MODEL = "deepseek-v4.1-flash:cloud"
MAX_IN_FLIGHT = 3
ATTEMPTS = 3          # the first call plus two retries
REQUEST_TIMEOUT = 300

TYPES = ("radicals", "kanji", "vocab")

# WaniKani inline markup and other tags must never reach the Bangla text.
TAG = re.compile(r"</?(?:radical|kanji|vocabulary|reading|ja|em|i|b|strong|u)>", re.I)
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

SYSTEM = """You write short Bangla mnemonics for a Japanese kanji study site used by learners in Bangladesh.

Non-negotiable rules:
- Retell the SAME story and image as the English mnemonic you are given. It must be a faithful retelling, not a new invention, and not word-for-word translationese.
- Address the reader as তুমি (tumi), never আপনি (apni). Keep the whole mnemonic in the তুমি register, including its possessive and object forms (তোমার, তোমাকে, তোকে). The words আপনি, আপনার and আপনাকে must never appear.
- Use Bangladeshi Bangla only (Dhaka standard চলিত). Use everyday Bangladeshi vocabulary: পানি for water in daily contexts (never জল), ভাইয়া / আপা for elder brother / elder sister. Remember that দাদা means grandfather in Bangladesh — never use it for an elder brother. Avoid Kolkata-style tatsama-heavy diction and West-Bengal-only words.
- Bangla script only. Every letter in both fields must be Bengali script (U+0980–U+09FF). Never write Latin, Devanagari, Hebrew, kanji or kana; if you need to name the Japanese character, describe it in Bangla instead.
- Very simple, short sentences. One vivid image per mnemonic, easy to memorise at a glance.
- The meaning mnemonic retells the English meaning mnemonic.
- The reading mnemonic must make the Japanese reading's sound stick: use a similar-sounding Bangla word when a natural one exists; otherwise keep the English story's sound hook. It must always point at the Japanese reading.
- Proper nouns from the English story (for example Chewbacca) become Bangla-script transliterations.
- Plain text only: no HTML, no tags, no bullet points, no markdown. At most two short paragraphs separated by one blank line.
- Reply with strict JSON only, exactly this shape:
  {"meaning": "...", "reading": "..."}
  For a radical there is no reading: send "reading": null."""


def build_prompt(item):
    if item["type"] == "radicals":
        reading_note = (
            "RADICAL: radicals have no reading. The \"reading\" value must be null."
        )
    else:
        reading_note = (
            "The reading mnemonic must remind the learner of the Japanese "
            "reading(s) above."
        )
    components = ", ".join(item["components"]) if item["components"] else "—"
    readings = item["readings"] or "—"
    lines = [
        f"TYPE: {item['type'][:-1] if item['type'].endswith('s') else item['type']}",
        f"CHARACTER: {item['char'] or '(image-only)'}",
        f"PRIMARY MEANING: {item['meaning'] or '—'}",
        f"JAPANESE READING(S): {readings}",
        f"COMPONENTS: {components}",
        "",
        "ENGLISH MEANING MNEMONIC:",
        item["en_meaning"] or "—",
        "",
        "ENGLISH READING MNEMONIC:",
        item["en_reading"] or "—",
        "",
        f"ENGLISH SOUND HOOK: {item['hook'] or '—'}",
        "",
        reading_note,
    ]
    return "\n".join(lines)


def item_record(type_, source, display, kanji_meaning):
    """One generation unit: site fields plus component/reading context."""
    if type_ == "kanji":
        components = [
            "%s (%s)" % (r.get("char") or r.get("meaning"), r.get("meaning"))
            for r in display.get("radicals") or []
        ]
        readings = display.get("reading_display") or ""
    elif type_ == "vocab":
        components = ["%s (%s)" % (c, kanji_meaning.get(c) or "kanji")
                      for c in display.get("kanji") or []]
        readings = display.get("reading_display") or ""
    else:
        components = []
        readings = ""

    en_reading = display.get("reading_mnemonic") or ""
    hooks = []
    for h in re.findall(r"<reading>(.*?)</reading>", en_reading, re.I | re.S):
        h = h.strip()
        if h and h not in hooks:
            hooks.append(h)

    return {
        "id": str(source["id"]),
        "type": type_,
        "char": display.get("char") or source.get("slug") or "",
        "meaning": display.get("meaning") or "",
        "readings": readings,
        "components": components,
        "en_meaning": display.get("meaning_mnemonic") or "",
        "en_reading": en_reading,
        "hook": ", ".join(hooks),
    }


def collect_items(curriculum, week, kanji_meaning):
    """Walk the same records build.py renders; keep source ids in step."""
    items = []
    seen = set()
    for wk in curriculum["weeks"]:
        if week is not None and wk["week"] != week:
            continue
        for type_ in TYPES:
            source = wk[type_]
            display = lesson_items(wk, type_)
            if len(source) != len(display):
                raise SystemExit(
                    "curriculum record mismatch for week %s/%s" % (wk["week"], type_)
                )
            for src, disp in zip(source, display):
                record = item_record(type_, src, disp, kanji_meaning)
                if record["id"] in seen:
                    continue
                seen.add(record["id"])
                items.append(record)
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
    text = TAG.sub("", text)
    for old, new in WORD_FIXES:
        text = text.replace(old, new)
    lines = [line.rstrip() for line in text.split("\n")]
    text = "\n".join(lines).strip()
    return re.sub(r"\n{3,}", "\n\n", text)


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
    meaning = clean_text(payload.get("meaning"))
    if not meaning:
        raise ValueError("empty meaning")
    if ANY_TAG.search(meaning) or non_bangla_letter(meaning):
        raise ValueError("meaning is not plain Bangla-script text")
    if item["type"] == "radicals":
        return {"meaning": meaning, "reading": None}
    reading = clean_text(payload.get("reading"))
    if not reading:
        raise ValueError("empty reading")
    if ANY_TAG.search(reading) or non_bangla_letter(reading):
        raise ValueError("reading is not plain Bangla-script text")
    return {"meaning": meaning, "reading": reading}


def call_ollama(item):
    body = {
        "model": MODEL,
        "stream": False,
        "format": "json",
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": build_prompt(item)},
        ],
        "options": {"temperature": 0.5},
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
            f"{stamp} | id={item['id']} | type={item['type']} | "
            f"char={item['char']!r} | {type(exc).__name__}: {exc}\n"
        )


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Generate Bangladeshi Bangla mnemonics via local Ollama.")
    parser.add_argument("--week", type=int, default=None,
                        help="only this week's subjects (default: all missing)")
    args = parser.parse_args(argv)

    curriculum = load_curriculum()
    if args.week is not None and not any(
            w["week"] == args.week for w in curriculum["weeks"]):
        raise SystemExit(f"week {args.week} is not in data/curriculum.json")

    try:
        cache = load_cache()
    except SystemExit:
        cache = {}
    kanji_meaning = {
        s["characters"]: s.get("primary_meaning") or ""
        for s in cache.values()
        if s.get("type") == "kanji" and s.get("characters")
    }

    items = collect_items(curriculum, args.week, kanji_meaning)
    overlay = load_overlay()
    missing = [it for it in items if it["id"] not in overlay]

    scope = f"week {args.week}" if args.week is not None else "all weeks"
    print(f"{scope}: {len(items)} subjects, {len(items) - len(missing)} already done, "
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
                print(f"  FAIL {item['id']} {item['char'] or item['meaning']}: {exc}",
                      flush=True)
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
            print(f"  id={item['id']} type={item['type']} "
                  f"char={item['char'] or item['meaning']!r}: {exc}")
        print(f"details appended to {FAIL_LOG}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
