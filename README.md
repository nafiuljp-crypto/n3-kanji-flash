# N3 漢字フラッシュカード (N3 Kanji Flash Cards)

JLPT N3 kanji study website built from 「日本語総まとめ N3 漢字」(Sou Matome N3 Kanji).

**Hosted on GitHub Pages**: <https://nafiuljp-crypto.github.io/n3-kanji-flash/>

**Two game modes**:
1. **🎴 フラッシュカード (Flash cards)** — See kanji → type reading or meaning → see correct/wrong + example sentence
2. **✏️ 演習問題 (Exercises)** — Multiple choice questions from the book's Day 7 実戦問題 (practice) and weekly クイズ (quiz)

**🌐 Bilingual interface** — Toggle between **EN** and **日本語** in the top-right corner. Choice persists in a cookie.

---

## Repo layout

This repo contains **both the source and the built site**:

```
n3-kanji-flash/
├── app.py              # Optional Flask dev server (local-only)
├── build.py            # Static site generator → dist/
├── i18n.py             # EN/JA translations
├── data/               # 6 weeks of extracted kanji + questions (JSON)
├── templates/          # Jinja2 templates
├── static/             # app.js, style.css (source for the build)
├── dist/               # Build output (gitignored)
│
│   --- Files below are copied from dist/ at build time and committed ---
│
├── index.html          # Root redirect → /ja/
├── 404.html
├── .nojekyll           # Tells GH Pages to skip Jekyll processing
├── ja/                 # Japanese pages (default)
├── en/                 # English pages
└── static/             # Built assets (app.js, style.css, i18n.json)
```

The repo root is structured so GitHub Pages serves every URL correctly:
- `/` → redirects to `/ja/`
- `/ja/...` → Japanese pages
- `/en/...` → English pages
- `/static/...` → JS / CSS / JSON

---

## Rebuild & deploy

After editing templates, data, or static assets:

```bash
python3 build.py           # regenerates dist/
cp -r dist/. .             # copies dist/* to repo root
git add . && git commit -m "Rebuild site"
git push
```

GitHub Pages will pick up the new content within a minute.

### Optional: local Flask dev server

For quick iteration with auto-reload, you can run the original Flask app instead of rebuilding:

```bash
pip install flask --break-system-packages
python3 app.py
# → http://100.71.17.106:8080  (Tailscale-only, see app.py)
```

The Flask app and the static build share the same templates and data, so they stay in sync.

---

## Language

The UI is fully bilingual:

- Default language: **日本語** (`ja`). Override with `DEFAULT_LANG=en python3 build.py` (changes the root redirect).
- Language preference is stored in a `lang` cookie — persists across pages and visits.
- Toggle in the navbar (top right) to switch. The toggle is JS-driven and rewrites the URL prefix from `/en/...` to `/ja/...` (or vice-versa) while keeping you on the same logical page.
- All kanji and example sentences stay in Japanese regardless of UI language — the toggle only changes buttons, labels, and instructions.
- All translations live in `i18n.py`. To add a new string, add it to both the `en` and `ja` dicts and reference it in templates as `{{ T.your_key }}`.

---

## Content

Each `data/week_N.json` contains:

- **`theme`** — chapter title (JP / EN / KR)
- **`lessons[]`** — 6 days of kanji lessons, each with:
  - `kanji[]` — character, stroke count, readings (on'yomi / kun'yomi), meaning, compounds, example sentence
- **`practice`** — Day 7 実戦問題 (~20 multiple choice questions)
- **`quiz`** — End-of-week クイズ (5-7 questions)

**Coverage**: 6 chapters, 36 lesson days, ~290 kanji, ~140 multiple choice questions.

---

## WaniKani enrichment

Every flash card also shows the WaniKani chain for its kanji:

```
radicals  →  kanji  →  vocabulary
```

- **Radicals** — the WaniKani radical subjects the kanji is built from, with their meanings.
- **Kanji** — the WaniKani kanji subject, its primary meaning, and its level.
- **Vocabulary** — up to 8 WaniKani vocabulary items that use the kanji, sorted by level, with reading and meaning. A `+N more` chip appears when more exist.

All entries link to the corresponding WaniKani page.

### How the data is produced

`wanikani.py` downloads all 9,392 WaniKani subjects, caches them under `.cache/`
(gitignored), and writes the small derived file `data/wanikani.json` — one entry
per character used in the six weeks. `build.py` and `app.py` call
`wanikani.attach_week()` so the templates receive the chain with the lesson data.

```bash
# one-time / occasional: re-download subjects and rebuild data/wanikani.json
python3 wanikani.py --refresh

# after changing week data: rebuild the derived file from the cache
python3 wanikani.py
```

### API token

The token is personal and must never be committed — the site is public.

```bash
mkdir -p ~/.config/wanikani
printf '%s\n' '<your-token>' > ~/.config/wanikani/token
chmod 600 ~/.config/wanikani/token
```

`WANIKANI_TOKEN` in the environment takes precedence over that file. Nothing
under `.cache/` or `~/.config/wanikani/` is tracked by git, and the built pages
contain only subject data, never the token.

---

## Source

- PDF: `Sou Matome N3 Kanji.pdf` (ASK Publishing, 2010, ISBN 978-4-87217-730-5)
- Authors: 佐々木仁子, 松本紀子
