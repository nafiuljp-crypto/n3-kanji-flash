"""
N3 Kanji Flash Card Website
Tailscale-only access — bound to 100.71.17.106:8080

UI supports both English and Japanese, switched via the language toggle in the navbar.
"""

import json
import os
import secrets
from pathlib import Path

from flask import (
    Flask,
    abort,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

from i18n import TRANSLATIONS, get_translations, format_string

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

# Tailscale-only IP. Override with env var if needed.
TAILSCALE_IP = os.environ.get("TAILSCALE_IP", "100.71.17.106")
PORT = int(os.environ.get("PORT", "8080"))
DEFAULT_LANG = os.environ.get("DEFAULT_LANG", "ja")  # default to Japanese

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", secrets.token_hex(32))


# ---------- i18n helpers ----------

SUPPORTED_LANGS = ("en", "ja")


@app.before_request
def resolve_lang():
    """Resolve the active language for this request."""
    lang = request.args.get("lang") or session.get("lang") or DEFAULT_LANG
    if lang not in SUPPORTED_LANGS:
        lang = DEFAULT_LANG
    session["lang"] = lang
    g.lang = lang
    g.T = get_translations(lang)


@app.context_processor
def inject_globals():
    """Inject globals into all templates."""
    return {
        "lang": getattr(g, "lang", DEFAULT_LANG),
        "T": getattr(g, "T", get_translations(DEFAULT_LANG)),
        "supported_langs": SUPPORTED_LANGS,
    }


@app.route("/lang/<lang>")
def set_lang(lang):
    """Set the active language and redirect back to the previous page."""
    if lang not in SUPPORTED_LANGS:
        abort(404)
    session["lang"] = lang
    next_url = request.referrer or url_for("home")
    return redirect(next_url)


# ---------- data helpers ----------

def load_json(path: Path):
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def load_week(week: int):
    if not (1 <= week <= 6):
        abort(404)
    f = DATA_DIR / f"week_{week}.json"
    if not f.exists():
        abort(404, description=f"week_{week}.json not found")
    return load_json(f)


def get_practice_questions(week_data):
    return week_data.get("practice", {}).get("questions", [])


def get_quiz_questions(week_data):
    return week_data.get("quiz", {}).get("questions", [])


# ---------- pages ----------

@app.route("/")
def home():
    chapters = []
    for w in range(1, 7):
        f = DATA_DIR / f"week_{w}.json"
        if not f.exists():
            continue
        data = load_json(f)
        kanji_count = sum(len(lesson.get("kanji", [])) for lesson in data.get("lessons", []))
        chapters.append(
            {
                "week": w,
                "theme_jp": data["theme"]["jp"],
                "theme_en": data["theme"]["en"],
                "theme_kr": data["theme"]["kr"],
                "lesson_count": len(data.get("lessons", [])),
                "kanji_count": kanji_count,
                "practice_q": len(get_practice_questions(data)),
                "quiz_q": len(get_quiz_questions(data)),
            }
        )
    return render_template("home.html", chapters=chapters)


@app.route("/chapter/<int:week>")
def chapter(week):
    data = load_week(week)
    return render_template("chapter.html", week=week, data=data)


@app.route("/flashcard/<int:week>")
def flashcard_overview(week):
    data = load_week(week)
    return render_template("flashcard_overview.html", week=week, data=data)


@app.route("/flashcard/<int:week>/<int:day>")
def flashcard(week, day):
    data = load_week(week)
    lesson = next((l for l in data["lessons"] if l["day"] == day), None)
    if not lesson:
        abort(404)
    return render_template("flashcard.html", week=week, day=day, lesson=lesson)


@app.route("/api/flashcard/<int:week>/<int:day>")
def api_flashcard(week, day):
    data = load_week(week)
    lesson = next((l for l in data["lessons"] if l["day"] == day), None)
    if not lesson:
        abort(404)
    return jsonify({"week": week, "day": day, "lesson": lesson})


@app.route("/exercise/<int:week>/<mode>")
def exercise(week, mode):
    if mode not in ("practice", "quiz"):
        abort(404)
    data = load_week(week)
    title = exercise_title(week, mode, data)
    if mode == "practice":
        questions = get_practice_questions(data)
    else:
        questions = get_quiz_questions(data)
    return render_template(
        "exercise.html",
        week=week,
        mode=mode,
        title=title,
        question_count=len(questions),
    )


def exercise_title(week, mode, data=None):
    if data is None:
        data = load_week(week)
    if mode == "practice":
        return format_string(g.T["title_exercise_practice"], week=week)
    return data.get("quiz", {}).get("title") or format_string(g.T["title_exercise_quiz_fallback"], week=week)


@app.route("/api/exercise/<int:week>/<mode>")
def api_exercise(week, mode):
    if mode not in ("practice", "quiz"):
        abort(404)
    data = load_week(week)
    if mode == "practice":
        questions = get_practice_questions(data)
    else:
        questions = get_quiz_questions(data)
    sanitized = []
    for q in questions:
        q_copy = {k: v for k, v in q.items() if k != "answer"}
        sanitized.append(q_copy)
    return jsonify(
        {
            "week": week,
            "mode": mode,
            "title": exercise_title(week, mode, data),
            "questions": sanitized,
        }
    )


@app.route("/api/check_answer/<int:week>/<mode>/<int:qid>")
def api_check_answer(week, mode, qid):
    if mode not in ("practice", "quiz"):
        abort(404)
    data = load_week(week)
    if mode == "practice":
        questions = get_practice_questions(data)
    else:
        questions = get_quiz_questions(data)
    q = next((x for x in questions if x["id"] == qid), None)
    if not q:
        abort(404)
    return jsonify(
        {
            "id": qid,
            "answer": q.get("answer"),
            "explanation": q.get("explanation"),
        }
    )


@app.route("/healthz")
def healthz():
    return jsonify({"status": "ok"})


@app.errorhandler(404)
def not_found(e):
    return render_template("404.html", message=str(e.description) if hasattr(e, "description") else "Not found"), 404


if __name__ == "__main__":
    print(f"Starting N3 Kanji Flash on http://{TAILSCALE_IP}:{PORT}")
    print(f"Default language: {DEFAULT_LANG}")
    print(f"Language switcher available; supported: {SUPPORTED_LANGS}")
    print(f"Access restricted to Tailscale network.")
    app.run(host=TAILSCALE_IP, port=PORT, debug=False)
