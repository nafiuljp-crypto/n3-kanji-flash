#!/usr/bin/env python3
"""WaniKani subject data for the N3 kanji study site.

Downloads every WaniKani subject (radicals, kanji, vocabulary) once into
.cache/, which curriculum.py then turns into data/curriculum.json.

The API token belongs to the account, not the site. It is read from the
WANIKANI_TOKEN environment variable or from ~/.config/wanikani/token, and it is
never written into the repository or into the built pages.

Usage:
    python3 wanikani.py --refresh   # re-download all subjects
    python3 wanikani.py             # report what is in the cache
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
TOKEN_FILE = Path.home() / ".config" / "wanikani" / "token"

API = "https://api.wanikani.com/v2"
SUBJECT_TYPES = "radical,kanji,vocabulary"
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


# ---------- CLI ----------

def main(argv):
    if "--refresh" in argv:
        token = get_token()
        print("Fetching WaniKani subjects…", file=sys.stderr)
        subjects = fetch_all_subjects(token)
    else:
        subjects = load_cache()
    counts = {}
    for subject in subjects.values():
        counts[subject["type"]] = counts.get(subject["type"], 0) + 1
    print(f"{len(subjects)} subjects cached: " +
          ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main(sys.argv[1:])
