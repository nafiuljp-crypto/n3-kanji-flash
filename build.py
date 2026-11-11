#!/usr/bin/env python3
"""Build the static N3 kanji study site for GitHub Pages.

Reads data/curriculum.json (produced by curriculum.py from the WaniKani cache
plus the Sou Matome week lists) and pre-renders every page for /ja/ and /en/:

  /                       week list + overall progress
  /week/<n>/              one week: three lessons, three tests
  /week/<n>/learn/<type>/ lesson player
  /week/<n>/test/<type>/  repeatable test, one week
  /test/                  test picker
  /test/<type>/           repeatable test, all weeks

Usage:
    python3 build.py
"""

import json
import os
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_SRC = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DIST = BASE_DIR / "dist"

# Bangla overlays, keyed by WaniKani subject id. They are deliberately
# separate from the WaniKani cache so a cache rebuild never drops the
# translations.
MNEMONICS_BN_FILE = DATA_DIR / "mnemonics_bn.json"
MEANINGS_BN_FILE = DATA_DIR / "meanings_bn.json"

# GitHub Pages serves this project under /<repo>/. Absolute URLs keep nested
# pages working, because GH Pages does not collapse "../" segments.
SITE_BASE = os.environ.get("SITE_BASE", "/n3-kanji-flash/")

LANGS = ("ja", "en")
DEFAULT_LANG = "ja"
TYPES = ("radicals", "kanji", "vocab")

from i18n import TRANSLATIONS, get_translations, format_string  # noqa: E402


# ---------- data ----------

def load_curriculum():
    path = DATA_DIR / "curriculum.json"
    if not path.exists():
        raise SystemExit("data/curriculum.json missing — run `python3 curriculum.py` first.")
    return json.loads(path.read_text(encoding="utf-8"))


def load_mnemonics_bn():
    """Bangla overlay: {"<subject_id>": {"meaning": ..., "reading": ...}}.

    Optional: a checkout without the overlay builds exactly as before, with
    every *_mnemonic_bn field null. Keyed by subject id, not by curriculum
    order, so it survives WaniKani cache rebuilds.
    """
    if not MNEMONICS_BN_FILE.exists():
        return {}
    try:
        data = json.loads(MNEMONICS_BN_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"{MNEMONICS_BN_FILE} is not valid JSON: {e}")
    if not isinstance(data, dict):
        raise SystemExit(f"{MNEMONICS_BN_FILE} must contain a JSON object.")
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def load_meaning_bn():
    """Bangla meaning glosses: {"<subject_id>": {"meaning_bn": ...}}.

    Optional like the mnemonic overlay: without the file every kanji's
    meaning_bn field is null. Keyed by subject id, not curriculum order.
    """
    if not MEANINGS_BN_FILE.exists():
        return {}
    try:
        data = json.loads(MEANINGS_BN_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"{MEANINGS_BN_FILE} is not valid JSON: {e}")
    if not isinstance(data, dict):
        raise SystemExit(f"{MEANINGS_BN_FILE} must contain a JSON object.")
    return {str(k): v for k, v in data.items() if isinstance(v, dict)}


def bn_field(overlay, subject_id, key):
    entry = overlay.get(str(subject_id)) or {}
    value = entry.get(key)
    return value if isinstance(value, str) and value.strip() else None


def lesson_items(week, type_, mnemonics_bn=None, meanings_bn=None):
    """Display records for the lesson player."""
    mnemonics_bn = mnemonics_bn or {}
    meanings_bn = meanings_bn or {}
    items = []
    if type_ == "radicals":
        for r in week["radicals"]:
            items.append({
                "id": r["id"],
                "char": r["char"],
                "image": r["image"],
                # Image-only radicals have no char: label the image with the
                # meaning so the alt text is never empty (B14).
                "alt": r["char"] or r["meaning"] or r.get("slug") or "",
                "meaning": r["meaning"],
                "reading_display": "",
                "radicals": [],
                "kanji": [],
                "url": r["url"],
                # Radicals have a meaning mnemonic only.
                "meaning_mnemonic": r.get("meaning_mnemonic"),
                "reading_mnemonic": None,
                "meaning_mnemonic_bn": bn_field(mnemonics_bn, r["id"], "meaning"),
                "reading_mnemonic_bn": None,
            })
    elif type_ == "kanji":
        for k in week["kanji"]:
            readings = [x for x in (k.get("onyomi_all") or []) + (k.get("kunyomi_all") or [])]
            if not readings:
                readings = [x for x in (k.get("readings") or [])]
            items.append({
                "id": k["char"],
                "char": k["char"],
                "image": None,
                "meaning": k.get("meaning") or (k.get("meanings") or [""])[0],
                "reading_display": " · ".join(readings),
                "radicals": k.get("radicals", []),
                "kanji": [],
                "stroke": k.get("stroke"),
                "example": k.get("example"),
                "compounds": k.get("compounds", []),
                "url": k.get("url"),
                "meaning_mnemonic": k.get("meaning_mnemonic"),
                "reading_mnemonic": k.get("reading_mnemonic"),
                "meaning_mnemonic_bn": bn_field(mnemonics_bn, k["id"], "meaning"),
                "reading_mnemonic_bn": bn_field(mnemonics_bn, k["id"], "reading"),
                # Kanji only: the Bangla gloss of the meanings line.
                "meaning_bn": bn_field(meanings_bn, k["id"], "meaning_bn"),
            })
    else:
        for v in week["vocab"]:
            items.append({
                "id": v["id"],
                "char": v["char"],
                "image": None,
                "meaning": v["meaning"],
                "reading_display": v["reading"],
                "radicals": [],
                "kanji": v.get("kanji", []),
                "url": v["url"],
                "meaning_mnemonic": v.get("meaning_mnemonic"),
                "reading_mnemonic": v.get("reading_mnemonic"),
                "meaning_mnemonic_bn": bn_field(mnemonics_bn, v["id"], "meaning"),
                "reading_mnemonic_bn": bn_field(mnemonics_bn, v["id"], "reading"),
            })
    return items


def test_items(weeks, type_):
    """Test records: glyph plus every answer we accept."""
    items = []
    seen = set()
    for week in weeks:
        if type_ == "radicals":
            for r in week["radicals"]:
                if r["id"] in seen:
                    continue
                seen.add(r["id"])
                items.append({
                    "char": r["char"] or r["slug"],
                    "image": r["image"],
                    "meanings": r["meanings"] or [r["meaning"]],
                    "readings": [],
                })
        elif type_ == "kanji":
            for k in week["kanji"]:
                if k["char"] in seen:
                    continue
                seen.add(k["char"])
                meanings = []
                if k.get("meaning"):
                    meanings.append(k["meaning"])
                meanings.extend(k.get("meanings") or [])
                readings = []
                readings.extend(k.get("onyomi_all") or [])
                readings.extend(k.get("kunyomi_all") or [])
                for r in (k.get("onyomi"), k.get("kunyomi")):
                    if r and r not in readings:
                        readings.append(r)
                items.append({
                    "char": k["char"],
                    "meanings": meanings or [k.get("meaning") or ""],
                    "readings": readings or k.get("readings") or [],
                })
        else:
            for v in week["vocab"]:
                if v["id"] in seen:
                    continue
                seen.add(v["id"])
                items.append({
                    "char": v["char"],
                    "meanings": v["meanings"] or [v["meaning"]],
                    "readings": v["readings"] or [v["reading"]],
                })
    return items


def week_summary(week):
    return {
        "week": week["week"],
        "theme": week["theme"],
        "radical_count": len(week["radicals"]),
        "kanji_count": len(week["kanji"]),
        "vocab_count": len(week["vocab"]),
    }


def ui_strings(lang):
    T = get_translations(lang)
    keys = [
        "no_items", "lesson_progress", "btn_next", "btn_prev", "lesson_done",
        "wani_open", "q_meaning_radicals", "q_meaning_kanji", "q_meaning_vocab",
        "q_reading_kanji", "q_reading_vocab", "placeholder_meaning",
        "placeholder_reading", "btn_check", "btn_show_answer", "btn_continue",
        "correct", "incorrect", "answer_was", "question_of", "test_complete",
        # range panel + romaji input (E.1 / E.2)
        "range_title", "range_from", "range_to", "range_of", "range_questions",
        "btn_start_session", "answer_aria",
        # JLPT option mode: the option buttons are built in app.js
        "jlpt_option_aria",
        # lesson mnemonic callout
        "mnemonic", "meaning_label", "reading_label",
    ]
    return {k: T[k] for k in keys}


def lesson_ui_strings(lang):
    """Test pages + lesson pages share the base set; the slide/gallery
    toggle exists only on learn pages, so its labels stay out of test pages
    (their markup must not change for a learn-page feature)."""
    strings = ui_strings(lang)
    T = get_translations(lang)
    for key in ("view_slide", "view_gallery", "view_switch_aria"):
        strings[key] = T[key]
    return strings


# ---------- rendering ----------

def make_env(lang):
    env = Environment(loader=FileSystemLoader(str(TEMPLATE_DIR)),
                      autoescape=True, trim_blocks=False, lstrip_blocks=False)
    env.globals.update({
        "lang": lang,
        "T": get_translations(lang),
        "supported_langs": ("en", "ja"),
        "base": SITE_BASE,
        "default_lang": DEFAULT_LANG,
    })
    return env


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_page(env, lang, type_, weeks, scope, week_label, back_path, back_label):
    T = env.globals["T"]
    title = T["test_" + type_]
    html = env.get_template("test.html").render(
        title=title,
        scope_label=week_label,
        back_path=back_path,
        back_label=back_label,
        page_data={
            "type": type_,
            "scope": scope,
            "items": test_items(weeks, type_),
        },
        ui_strings=ui_strings(lang),
    )
    return html


def main():
    curriculum = load_curriculum()
    weeks = curriculum["weeks"]
    by_week = {w["week"]: w for w in weeks}
    mnemonics_bn = load_mnemonics_bn()
    meanings_bn = load_meaning_bn()

    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)
    (DIST / "static").mkdir(parents=True, exist_ok=True)

    # NOTE: no i18n.json is generated any more. Nothing loaded it, and the
    # static/ copy silently overwrote the generated one (B18). UI strings
    # travel in each page's <script id="i18n-strings"> block.

    totals = {
        "radicals": sum(len(w["radicals"]) for w in weeks),
        "kanji": sum(len(w["kanji"]) for w in weeks),
        "vocab": sum(len(w["vocab"]) for w in weeks),
    }
    summaries = [week_summary(w) for w in weeks]

    for lang in LANGS:
        env = make_env(lang)
        T = env.globals["T"]

        # home
        write(DIST / lang / "index.html", env.get_template("home.html").render(
            weeks=summaries, totals=totals))

        # test picker
        write(DIST / lang / "test" / "index.html",
              env.get_template("test_overview.html").render(weeks=summaries))

        # all-weeks tests
        for type_ in TYPES:
            write(
                DIST / lang / "test" / type_ / "index.html",
                test_page(env, lang, type_, weeks, "all",
                          T["all_weeks"], f"{lang}/test/", T["nav_tests"]),
            )

        for week in weeks:
            n = week["week"]
            week_dir = DIST / lang / "week" / str(n)

            write(week_dir / "index.html", env.get_template("week.html").render(
                week={**week_summary(week), "theme": week["theme"]}))

            for type_ in TYPES:
                items = lesson_items(week, type_, mnemonics_bn, meanings_bn)
                write(
                    week_dir / "learn" / type_ / "index.html",
                    env.get_template("lesson.html").render(
                        week=n,
                        title=T["learn_" + type_],
                        subtitle=T["learn_" + type_ + "_sub"],
                        theme=week["theme"],
                        page_data={
                            "type": type_,
                            "week": n,
                            "items": items,
                            "test_url": f"{SITE_BASE}{lang}/week/{n}/test/{type_}/",
                        },
                        ui_strings=lesson_ui_strings(lang),
                    ),
                )

                write(
                    week_dir / "test" / type_ / "index.html",
                    test_page(env, lang, type_, [week], f"week{n}",
                              format_string(T["week_n"], week=n),
                              f"{lang}/week/{n}/", format_string(T["back_to_week"], week=n)),
                )

        write(DIST / lang / "404.html", env.get_template("404.html").render())
        print(f"  rendered /{lang}/ pages")

    # Root and 404 both redirect to a real page. The URL is absolute: a
    # relative redirect from /week/9/ resolves inside the missing path and
    # loops forever (B8). The saved language cookie is honoured (B15/F12).
    root_redirect = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>N3 漢字学習</title>
<link rel="icon" type="image/svg+xml" href="{base}static/favicon.svg">
<link rel="icon" type="image/png" sizes="32x32" href="{base}static/favicon-32.png">
<link rel="apple-touch-icon" sizes="180x180" href="{base}static/apple-touch-icon.png">
<link rel="canonical" href="{base}ja/">
<script>
(function () {{
    var m = document.cookie.match(/(?:^|;\\s*)lang=(en|ja)(?:;|$)/);
    var lang = m ? m[1] : '{default_lang}';
    location.replace('{base}' + lang + '/');
}})();
</script>
<noscript><meta http-equiv="refresh" content="0; url={base}{default_lang}/"></noscript>
</head>
<body><p><a href="{base}ja/">日本語</a> · <a href="{base}en/">English</a></p></body>
</html>
""".format(base=SITE_BASE, default_lang=DEFAULT_LANG)
    write(DIST / "index.html", root_redirect)
    write(DIST / "404.html", root_redirect)

    for f in STATIC_SRC.iterdir():
        if f.is_file():
            shutil.copy2(f, DIST / "static" / f.name)

    (DIST / ".nojekyll").write_text("")

    n_html = sum(1 for _ in DIST.rglob("*.html"))
    print(f"Build complete: {n_html} HTML files → {DIST}")


if __name__ == "__main__":
    main()
