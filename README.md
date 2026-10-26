# N3 漢字学習 (N3 Kanji Study)

A WaniKani-style study site for JLPT N3 kanji: learn the **radicals**, then the
**kanji**, then the **vocabulary** — and take repeatable tests on each.

**Live site**: <https://nafiuljp-crypto.github.io/n3-kanji-flash/>

---

## What the site does

The kanji list comes from 「日本語総まとめ N3 漢字」(Sou Matome N3 Kanji) and is
arranged in its six weekly chapters. The language data — radicals, kanji
readings, and vocabulary — comes from the WaniKani API.

Each week contains:

| Lesson | Contents |
| --- | --- |
| **Radicals** | Every radical this week's kanji are built from. A radical is taught in the week where it first appears and reused afterwards. |
| **Kanji** | Meaning, readings, the radicals it is built from, stroke count, compounds, and an example sentence. |
| **Vocabulary** | WaniKani vocabulary written only with kanji in the N3 set, filed under the latest week among the kanji it uses. |

Each week also contains three tests:

- **Radical test** — radical → meaning
- **Kanji test** — kanji → meaning, and kanji → reading
- **Vocabulary test** — word → meaning, and word → reading

Tests are **repeatable**. There is no SRS scheduling and nothing is locked:
retake any test as often as you like, retry only the items you got wrong, or
run a test across all six weeks. Scores and lesson progress are stored in the
browser (`localStorage`), so they are per device and never leave the browser.

Totals: **263 radicals, 293 kanji, 571 vocabulary items.**

---

## Repo layout

```
n3-kanji-flash/
├── app.py              # Optional Flask dev server (local only)
├── build.py            # Static site generator → dist/
├── curriculum.py       # data/curriculum.json: weeks → radicals/kanji/vocab
├── wanikani.py         # WaniKani client, cache, and data/wanikani.json
├── i18n.py             # EN / JA strings
├── data/
│   ├── week_1..6.json  # Kanji lists and example sentences from the book
│   ├── wanikani.json   # Derived WaniKani data per kanji (committed)
│   └── curriculum.json # Derived curriculum (committed)
├── templates/          # Jinja2: home, week, lesson, test, test picker
├── static/             # app.js, style.css (source)
├── dist/               # Build output (gitignored)
│
│   --- copied from dist/ at deploy time and committed ---
├── index.html          # Root redirect → /ja/
├── 404.html
├── .nojekyll
├── ja/  en/            # Pre-rendered pages per language
└── static/             # Built assets
```

GitHub Pages serves the project under `/n3-kanji-flash/`, so every link in the
built HTML is absolute (GH Pages does not collapse `../` segments).

---

## Build and deploy

```bash
python3 curriculum.py      # regenerate data/curriculum.json from the cache
python3 build.py           # regenerate dist/
rm -rf en ja static index.html 404.html .nojekyll
cp -r dist/. .
git add -A && git commit -m "Rebuild site" && git push
```

Refreshing the WaniKani data itself (only needed when you want newer subject
data):

```bash
python3 wanikani.py --refresh   # re-downloads all subjects into .cache/
python3 curriculum.py
python3 build.py
```

---

## WaniKani API token

The token is personal and must never be committed — the site is public.

```bash
mkdir -p ~/.config/wanikani
printf '%s\n' '<your-token>' > ~/.config/wanikani/token
chmod 600 ~/.config/wanikani/token
```

`WANIKANI_TOKEN` in the environment takes precedence. `.cache/` (the raw subject
dump) and `~/.config/wanikani/` are never tracked by git, and the built pages
contain subject data only — never the token.

---

## Optional: local Flask dev server

```bash
pip install flask --break-system-packages
python3 app.py            # http://127.0.0.1:8080
```

Same templates and data as the static build.

---

## Language

The UI is bilingual. Default is **日本語**; the toggle in the navbar rewrites the
`/en/` or `/ja/` prefix in the current URL and stores the choice in a cookie.
Kanji, readings, and vocabulary are always shown in Japanese.

All strings live in `i18n.py`. Add a key to both the `en` and `ja` dicts.

---

## Source

- Kanji list and examples: 「日本語総まとめ N3 漢字」 (ASK Publishing, 2010,
  ISBN 978-4-87217-730-5) by 佐々木仁子, 松本紀子.
- Radicals, readings, vocabulary, levels: WaniKani API v2.
