#!/usr/bin/env python3
"""WaniKani subject data for the N3 kanji cards.

The site shows each kanji as a chain: the WaniKani radicals it is built from,
the kanji itself, and the WaniKani vocabulary that uses it. This module fetches
the subject list once, caches it, and derives the small per-kanji lookup the
templates need.

The API token belongs to the account, not the site. It is read from the
WANIKANI_TOKEN environment variable or from ~/.config/wanikani/token, and it is
never written into the repository or into the built pages.

Usage:
    python3 wanikani.py            # rebuild data/wanikani.json from the cache
    python3 wanikani.py --refresh  # re-download all subjects first
"""

import json
import os
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
CACHE_FILE = BASE_DIR / ".cache" / "wanikani_subjects.json"
DERIVED_FILE = DATA_DIR / "wanikani.json"
TOKEN_FILE = Path.home() / ".config" / "wanikani" / "token"

API = "https://api.wanikani.com/v2"
SUBJECT_TYPES = "radical,kanji,vocabulary"
VOCAB_PER_KANJI = 8          # keeps each flash card page small
USER_AGENT = "n3-kanji-flash/1.0 (personal study site)"


# ---------- token ----------

def get_token():
    token = os.environ.get("WANIKANI_TOKEN", "").strip()
    if not token and TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
    if not token:
        raise SystemExit(
            "No WaniKani token. Set WANIKANI_TOKEN or write it to "
            f"{TOKEN_FILE}."
        )
    return token


# ---------- fetching ----------

def api_get(url, token):
    """GET a WaniKani endpoint, waiting out the 60-requests-per-minute limit."""
    while True:
        req = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "User-Agent": USER_AGENT,
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return json.loads(resp.read().decode("utf-8")), resp.headers
        except urllib.error.HTTPError as e:
            if e.code != 429:
                raise
            retry_after = e.headers.get("Retry-After")
            time.sleep(float(retry_after) if retry_after else 10.0)


def trim_subject(subject):
    """Keep only the fields the site renders."""
    s = subject["data"]
    characters = s.get("characters")
    images = s.get("character_images") or []
    svg = next((i["url"] for i in images
                if i.get("content_type") == "image/svg+xml"), None)
    meanings = [m["meaning"] for m in (s.get("meanings") or [])]
    primary_meaning = next((m["meaning"] for m in (s.get("meanings") or [])
                            if m.get("primary")), meanings[0] if meanings else None)
    readings = s.get("readings") or []
    primary_reading = next((r["reading"] for r in readings if r.get("primary")),
                           readings[0]["reading"] if readings else None)
    return {
        "id": subject["id"],
        "type": subject["object"],
        "characters": characters,
        "slug": s.get("slug"),
        "level": s.get("level"),
        "meanings": meanings,
        "primary_meaning": primary_meaning,
        "primary_reading": primary_reading,
        "onyomi": [r["reading"] for r in readings if r.get("type") == "onyomi"],
        "kunyomi": [r["reading"] for r in readings if r.get("type") == "kunyomi"],
        "components": s.get("component_subject_ids") or [],
        "amalgamations": s.get("amalgamation_subject_ids") or [],
        "image": svg or (images[0]["url"] if images else None),
        "lesson_position": s.get("lesson_position"),
        "document_url": s.get("document_url"),
    }


def fetch_all_subjects(token):
    subjects = {}
    url = f"{API}/subjects?types={SUBJECT_TYPES}"
    page = 0
    while url:
        payload, headers = api_get(url, token)
        for item in payload["data"]:
            trimmed = trim_subject(item)
            subjects[trimmed["id"]] = trimmed
        page += 1
        print(f"  page {page}: {len(subjects)} subjects", file=sys.stderr)
        url = payload["pages"].get("next_url")
        remaining = headers.get("RateLimit-Remaining")
        if remaining is not None and int(remaining) <= 1 and url:
            time.sleep(2.0)
    CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    CACHE_FILE.write_text(
        json.dumps({"fetched_at": datetime.now(timezone.utc).isoformat(),
                    "subjects": list(subjects.values())},
                   ensure_ascii=False),
        encoding="utf-8",
    )
    return subjects


def load_cache():
    if not CACHE_FILE.exists():
        raise SystemExit(
            f"No WaniKani cache at {CACHE_FILE}. Run: python3 wanikani.py --refresh"
        )
    payload = json.loads(CACHE_FILE.read_text(encoding="utf-8"))
    return {s["id"]: s for s in payload["subjects"]}


# ---------- deriving the radical → kanji → vocabulary chain ----------

def site_kanji_chars():
    chars = []
    seen = set()
    for week in range(1, 7):
        path = DATA_DIR / f"week_{week}.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        for lesson in data.get("lessons", []):
            for k in lesson.get("kanji", []):
                char = k.get("char")
                if char and char not in seen:
                    seen.add(char)
                    chars.append(char)
    return chars


def radical_entry(subject):
    return {
        "char": subject["characters"],
        "slug": subject["slug"],
        "meaning": subject["primary_meaning"],
        "image": subject["image"] if not subject["characters"] else None,
        "url": subject["document_url"],
    }


def vocab_entry(subject):
    return {
        "char": subject["characters"],
        "reading": subject["primary_reading"],
        "meaning": subject["primary_meaning"],
        "level": subject["level"],
        "url": subject["document_url"],
    }


def build_derived(subjects):
    by_char = {s["characters"]: s for s in subjects.values()
               if s["type"] == "kanji" and s["characters"]}
    derived = {}
    matched = 0
    for char in site_kanji_chars():
        kanji = by_char.get(char)
        if not kanji:
            continue
        matched += 1
        radicals = []
        for cid in kanji["components"]:
            comp = subjects.get(cid)
            if comp and comp["type"] == "radical":
                radicals.append(radical_entry(comp))
        vocab = []
        for vid in kanji["amalgamations"]:
            subj = subjects.get(vid)
            if subj and subj["type"] == "vocabulary":
                vocab.append(vocab_entry(subj))
        vocab.sort(key=lambda v: (v["level"] or 99, len(v["char"]) if v["char"] else 0))
        derived[char] = {
            "level": kanji["level"],
            "url": kanji["document_url"],
            "meanings": kanji["meanings"],
            "onyomi": kanji["onyomi"],
            "kunyomi": kanji["kunyomi"],
            "radicals": radicals,
            "vocab": vocab[:VOCAB_PER_KANJI],
            "vocab_total": len(vocab),
        }
    DERIVED_FILE.write_text(
        json.dumps({"source": "WaniKani API v2",
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                    "kanji": derived},
                   ensure_ascii=False, indent=1, sort_keys=True),
        encoding="utf-8",
    )
    return matched, len(derived), sum(len(v["vocab"]) for v in derived.values())


# ---------- runtime lookup used by build.py and app.py ----------

_LOOKUP = None


def get_lookup():
    global _LOOKUP
    if _LOOKUP is None:
        if DERIVED_FILE.exists():
            _LOOKUP = json.loads(DERIVED_FILE.read_text(encoding="utf-8"))["kanji"]
        else:
            _LOOKUP = {}
    return _LOOKUP


def attach_week(data):
    """Add a `wanikani` block to every kanji in a week's data (in place)."""
    lookup = get_lookup()
    if not lookup:
        return data
    for lesson in data.get("lessons", []):
        for k in lesson.get("kanji", []):
            k["wanikani"] = lookup.get(k.get("char"))
    return data


# ---------- CLI ----------

def main(argv):
    if "--refresh" in argv:
        token = get_token()
        print("Fetching WaniKani subjects…", file=sys.stderr)
        subjects = fetch_all_subjects(token)
    else:
        subjects = load_cache()
    matched, total, vocab = build_derived(subjects)
    print(f"{matched} site kanji matched, {total} entries, "
          f"{vocab} vocabulary links → {DERIVED_FILE}")


if __name__ == "__main__":
    main(sys.argv[1:])
