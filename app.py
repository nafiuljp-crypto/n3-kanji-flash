"""Optional Flask dev server for the N3 kanji study site.

The public site is the static build (build.py → GitHub Pages). This server
renders the same templates from the same data so you can iterate locally.

    python3 app.py            # http://127.0.0.1:8080 (or TAILSCALE_IP)
"""

import json
import os
import secrets
from pathlib import Path

from flask import Flask, abort, g, jsonify, redirect, render_template, request, session, url_for

from build import lesson_items, test_items, ui_strings, week_summary
from i18n import get_translations, format_string

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

HOST = os.environ.get("TAILSCALE_IP", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8080"))
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "ja")
TYPES = ("radicals", "kanji", "vocab")

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))


def load_curriculum():
    path = DATA_DIR / "curriculum.json"
    if not path.exists():
        raise SystemExit("data/curriculum.json missing — run `python3 curriculum.py` first.")
    return json.loads(path.read_text(encoding="utf-8"))


CURRICULUM = load_curriculum()
WEEKS = CURRICULUM["weeks"]
BY_WEEK = {w["week"]: w for w in WEEKS}


@app.before_request
def resolve_lang():
    lang = request.args.get("lang") or session.get("lang") or DEFAULT_LANG
    if lang not in ("en", "ja"):
        lang = DEFAULT_LANG
    session["lang"] = lang
    g.lang = lang
    g.T = get_translations(lang)


@app.context_processor
def inject_globals():
    return {
        "lang": getattr(g, "lang", DEFAULT_LANG),
        "T": getattr(g, "T", get_translations(DEFAULT_LANG)),
        "supported_langs": ("en", "ja"),
        "base": "",
        "default_lang": DEFAULT_LANG,
    }


@app.route("/lang/<lang>")
def set_lang(lang):
    if lang not in ("en", "ja"):
        abort(404)
    session["lang"] = lang
    return redirect(request.referrer or url_for("home"))


@app.route("/")
def home():
    summaries = [week_summary(w) for w in WEEKS]
    totals = {t: sum(len(w[t]) for w in WEEKS) for t in TYPES}
    return render_template("home.html", weeks=summaries, totals=totals)


@app.route("/week/<int:week>/")
def week(week):
    data = BY_WEEK.get(week)
    if not data:
        abort(404)
    return render_template("week.html", week={**week_summary(data), "theme": data["theme"]})


@app.route("/week/<int:week>/learn/<type_>/")
def lesson(week, type_):
    data = BY_WEEK.get(week)
    if not data or type_ not in TYPES:
        abort(404)
    T = g.T
    return render_template(
        "lesson.html",
        week=week,
        title=T["learn_" + type_],
        subtitle=T["learn_" + type_ + "_sub"],
        theme=data["theme"],
        page_data={
            "type": type_,
            "week": week,
            "items": lesson_items(data, type_),
            "test_url": f"/week/{week}/test/{type_}/",
        },
        ui_strings=ui_strings(g.lang),
    )


@app.route("/test/")
def tests():
    return render_template("test_overview.html", weeks=[week_summary(w) for w in WEEKS])


def render_test(type_, weeks, scope, scope_label, back_path, back_label):
    T = g.T
    return render_template(
        "test.html",
        title=T["test_" + type_],
        scope_label=scope_label,
        back_path=back_path,
        back_label=back_label,
        page_data={"type": type_, "scope": scope, "items": test_items(weeks, type_)},
        ui_strings=ui_strings(g.lang),
    )


@app.route("/week/<int:week>/test/<type_>/")
def week_test(week, type_):
    data = BY_WEEK.get(week)
    if not data or type_ not in TYPES:
        abort(404)
    return render_test(type_, [data], f"week{week}",
                       format_string(g.T["week_n"], week=week),
                       f"/week/{week}/", format_string(g.T["back_to_week"], week=week))


@app.route("/test/<type_>/")
def all_test(type_):
    if type_ not in TYPES:
        abort(404)
    return render_test(type_, WEEKS, "all", g.T["all_weeks"], "/test/", g.T["nav_tests"])


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html"), 404


if __name__ == "__main__":
    print(f"N3 kanji study site on http://{HOST}:{PORT}")
    app.run(host=HOST, port=PORT, debug=False)
