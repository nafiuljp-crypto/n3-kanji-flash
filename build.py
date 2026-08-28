#!/usr/bin/env python3
"""
Build a fully static site for GitHub Pages from the same templates/data
the Flask app uses. No server-side routes — every URL is pre-rendered.

Output: ./dist/
  - index.html               (redirect to /ja/)
  - 404.html
  - .nojekyll
  - static/                 (app.js, style.css, i18n.json — shared assets)
  - ja/...                  (Japanese pages)
  - en/...                  (English pages)

Usage:
    python3 build.py
"""

import json
import os
import shutil
import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

BASE_DIR = Path(__file__).resolve().parent
TEMPLATE_DIR = BASE_DIR / "templates"
STATIC_SRC = BASE_DIR / "static"
DATA_DIR = BASE_DIR / "data"
DIST = BASE_DIR / "dist"

# GitHub Pages serves the project at https://<owner>.github.io/<repo>/.
# All asset / page URLs in the built HTML must be absolute so they resolve
# correctly from any nested page (GH Pages does NOT collapse "../" segments).
# Override with SITE_BASE=/your-repo/ python3 build.py
SITE_BASE = os.environ.get("SITE_BASE", "/n3-kanji-flash/")

LANGS = ("ja", "en")          # ja first so default redirect lands here
DEFAULT_LANG = "ja"


# ---------- helpers ----------

def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_all_weeks():
    weeks = {}
    for w in range(1, 7):
        f = DATA_DIR / f"week_{w}.json"
        if f.exists():
            weeks[w] = load_json(f)
    return weeks


def get_chapters(weeks):
    chapters = []
    for w in range(1, 7):
        if w not in weeks:
            continue
        data = weeks[w]
        kanji_count = sum(len(l.get("kanji", [])) for l in data.get("lessons", []))
        practice_q = len(data.get("practice", {}).get("questions", []))
        quiz_q = len(data.get("quiz", {}).get("questions", []))
        chapters.append({
            "week": w,
            "theme_jp": data["theme"]["jp"],
            "theme_en": data["theme"]["en"],
            "theme_kr": data["theme"]["kr"],
            "lesson_count": len(data.get("lessons", [])),
            "kanji_count": kanji_count,
            "practice_q": practice_q,
            "quiz_q": quiz_q,
        })
    return chapters


def depth_to_base(depth: int) -> str:
    """For absolute paths, depth doesn't matter — base is the same for all pages."""
    return SITE_BASE


def write(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


# ---------- template environment ----------

def make_env(lang: str, base: str = None):
    """Jinja2 env with helpers that mimic the Flask app's globals.

    The `base` argument is accepted for backwards compat but ignored —
    every page gets the absolute SITE_BASE so URLs resolve on GH Pages
    (which does not collapse "../" segments).
    """
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
        trim_blocks=False,
        lstrip_blocks=False,
    )

    # i18n
    from i18n import get_translations, SUPPORTED_LANGS  # noqa
    T = get_translations(lang)
    base = SITE_BASE

    def T_get(key, **kwargs):
        val = T.get(key, key)
        if kwargs:
            return val.format(**kwargs)
        return val

    env.globals.update({
        "lang": lang,
        "T": T,
        "supported_langs": SUPPORTED_LANGS,
        "base": base,
        "default_lang": DEFAULT_LANG,
        "T_get": T_get,
    })

    # url_for replacement that respects the base prefix
    def url_for(endpoint, **kw):
        base = kw.pop("__base", env.globals["base"])
        routes = {
            "home": "",
            "chapter": f"chapter/{kw['week']}",
            "flashcard_overview": f"flashcard/{kw['week']}",
            "flashcard": f"flashcard/{kw['week']}/{kw['day']}",
            "exercise": f"exercise/{kw['week']}/{kw['mode']}",
            "static": f"static/{kw['filename']}",
            "set_lang": f"#set-lang-{kw['lang']}",
        }
        path = routes[endpoint]
        if path.startswith("#"):
            return path
        if not base:
            return f"./{path}" if path else "./"
        return base + path

    env.globals["url_for"] = url_for
    return env


# ---------- per-language renderers ----------

def render_home(env, lang, chapters):
    tmpl = env.get_template("home.html")
    return tmpl.render(chapters=chapters, lang=lang)


def render_chapter(env, week, data, lang):
    tmpl = env.get_template("chapter.html")
    return tmpl.render(week=week, data=data, lang=lang)


def render_flashcard_overview(env, week, data, lang):
    tmpl = env.get_template("flashcard_overview.html")
    return tmpl.render(week=week, data=data, lang=lang)


def render_flashcard(env, week, day, lesson, lang):
    tmpl = env.get_template("flashcard.html")
    return tmpl.render(week=week, day=day, lesson=lesson, lang=lang)


def render_exercise(env, week, mode, data, lang, title, question_count,
                    questions_for_js):
    """Render exercise page. Blob of question data goes into <script id="exercise-data">."""
    tmpl = env.get_template("exercise.html")
    return tmpl.render(
        week=week, mode=mode, data=data, lang=lang,
        title=title, question_count=question_count,
        questions_json=json.dumps(questions_for_js, ensure_ascii=False),
    )


def render_404(env, lang):
    tmpl = env.get_template("404.html")
    return tmpl.render(message="Not found", lang=lang)


# ---------- main ----------

def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    DIST.mkdir(parents=True)

    weeks = load_all_weeks()
    chapters = get_chapters(weeks)

    # Bundled i18n.json for client-side use
    from i18n import TRANSLATIONS
    (DIST / "static").mkdir(parents=True, exist_ok=True)
    (DIST / "static" / "i18n.json").write_text(
        json.dumps(TRANSLATIONS, ensure_ascii=False),
        encoding="utf-8",
    )

    # Render pages for each language
    for lang in LANGS:
        # 1) /{lang}/                      depth=1  base="../"
        env_home = make_env(lang, "../")
        home_html = render_home(env_home, lang, chapters)
        write(DIST / lang / "index.html", home_html)

        # 2) /{lang}/chapter/<w>/          depth=2  base="../../"
        for w in sorted(weeks.keys()):
            env_w = make_env(lang, "../../")
            html = render_chapter(env_w, w, weeks[w], lang)
            write(DIST / lang / "chapter" / str(w) / "index.html", html)

            # 3) /{lang}/flashcard/<w>/      depth=2  base="../../"
            html = render_flashcard_overview(env_w, w, weeks[w], lang)
            write(DIST / lang / "flashcard" / str(w) / "index.html", html)

            # 4) /{lang}/flashcard/<w>/<d>/  depth=3  base="../../../"
            env_wd = make_env(lang, "../../../")
            for lesson in weeks[w].get("lessons", []):
                html = render_flashcard(env_wd, w, lesson["day"], lesson, lang)
                write(
                    DIST / lang / "flashcard" / str(w) / str(lesson["day"]) / "index.html",
                    html,
                )

            # 5) /{lang}/exercise/<w>/<mode>/  depth=3  base="../../../"
            for mode in ("practice", "quiz"):
                if mode == "practice":
                    qs = weeks[w].get("practice", {}).get("questions", [])
                else:
                    qs = weeks[w].get("quiz", {}).get("questions", [])
                if mode == "practice":
                    title = env_wd.globals["T"]["title_exercise_practice"].format(week=w)
                else:
                    title = (weeks[w].get("quiz", {}).get("title")
                             or env_wd.globals["T"]["title_exercise_quiz_fallback"].format(week=w))
                html = render_exercise(
                    env_wd, w, mode, weeks[w], lang, title, len(qs),
                    qs,  # full data (with answers) for client-side check
                )
                write(
                    DIST / lang / "exercise" / str(w) / mode / "index.html",
                    html,
                )

        # 6) /{lang}/404/ (for unknown routes within this lang)
        env_404 = make_env(lang, "../../")
        write(DIST / lang / "404.html", render_404(env_404, lang))

        print(f"  rendered /{lang}/ pages")

    # Root /index.html — meta-refresh to /ja/
    root_redirect = """<!doctype html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta http-equiv="refresh" content="0; url=./ja/">
<title>N3 漢字フラッシュカード</title>
<link rel="canonical" href="./ja/">
<script>location.replace('./ja/');</script>
</head>
<body>
<p>Redirecting to <a href="./ja/">日本語</a>…</p>
</body>
</html>
"""
    write(DIST / "index.html", root_redirect)

    # Root 404.html — redirect to /ja/
    write(DIST / "404.html", root_redirect)

    # Copy static assets (CSS, JS, favicons, anything else)
    if STATIC_SRC.exists():
        for f in STATIC_SRC.iterdir():
            if f.is_file():
                shutil.copy2(f, DIST / "static" / f.name)

    # .nojekyll so GitHub Pages doesn't try to process us
    (DIST / ".nojekyll").write_text("")

    # Summary
    n_html = sum(1 for _ in DIST.rglob("*.html"))
    n_files = sum(1 for _ in DIST.rglob("*") if _.is_file())
    print(f"Build complete: {n_html} HTML files, {n_files} total files in {DIST}")


if __name__ == "__main__":
    main()
