/* N3 Kanji study app — lesson player and repeatable tests.
   Page data arrives as JSON in <script id="page-data">; UI strings in
   <script id="i18n-strings">. Progress and scores live in localStorage. */

window.N3App = window.N3App || {};

(function () {
    "use strict";

    const LESSON_KEY = "n3lesson:v1";
    const TEST_KEY = "n3test:v1";

    // ---------- helpers ----------

    function $(id) { return document.getElementById(id); }
    function qsa(sel, ctx) { return Array.from((ctx || document).querySelectorAll(sel)); }

    function escapeHtml(s) {
        if (s === undefined || s === null) return "";
        return String(s)
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#39;");
    }

    function readJson(id) {
        const el = $(id);
        if (!el) return {};
        try { return JSON.parse(el.textContent); } catch (e) { return {}; }
    }

    function pageData() { return readJson("page-data"); }
    function uiStrings() { return readJson("i18n-strings"); }

    function storeGet(key, fallback) {
        try {
            const raw = localStorage.getItem(key);
            return raw ? JSON.parse(raw) : fallback;
        } catch (e) {
            return fallback;
        }
    }

    function storeSet(key, value) {
        try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* private mode */ }
    }

    function shuffle(list) {
        const a = list.slice();
        for (let i = a.length - 1; i > 0; i--) {
            const j = Math.floor(Math.random() * (i + 1));
            const t = a[i]; a[i] = a[j]; a[j] = t;
        }
        return a;
    }

    function toHiragana(s) {
        return String(s).replace(/[ァ-ヶ]/g, function (ch) {
            return String.fromCharCode(ch.charCodeAt(0) - 0x60);
        });
    }

    function normalize(s) {
        if (!s) return "";
        return toHiragana(String(s).trim().toLowerCase())
            .replace(/\s+/g, " ")
            .replace(/[　]/g, " ")
            .replace(/[.,!?！？。、・…]/g, "")
            .trim();
    }

    function levenshtein(a, b) {
        if (a === b) return 0;
        if (!a.length) return b.length;
        if (!b.length) return a.length;
        let prev = [];
        for (let j = 0; j <= a.length; j++) prev[j] = j;
        for (let i = 1; i <= b.length; i++) {
            const cur = [i];
            for (let j = 1; j <= a.length; j++) {
                cur[j] = Math.min(
                    prev[j] + 1,
                    cur[j - 1] + 1,
                    prev[j - 1] + (a[j - 1] === b[i - 1] ? 0 : 1)
                );
            }
            prev = cur;
        }
        return prev[a.length];
    }

    function matches(user, answers) {
        const u = normalize(user);
        if (!u) return false;
        for (const answer of answers) {
            const e = normalize(answer);
            if (!e) continue;
            if (u === e) return true;
            // WaniKani lists alternatives separated by commas or slashes.
            for (const alt of e.split(/\s*[,/、]\s*/)) {
                if (!alt) continue;
                if (u === alt) return true;
                if (alt.length >= 4 && levenshtein(u, alt) <= 1) return true;
            }
        }
        return false;
    }

    function glyphHtml(char, image, cls) {
        if (image) {
            return '<img class="' + (cls || "item-glyph-img") + '" src="' +
                escapeHtml(image) + '" alt="' + escapeHtml(char || "") + '">';
        }
        return escapeHtml(char || "—");
    }

    // ---------- progress ----------

    function lessonStore() { return storeGet(LESSON_KEY, {}); }

    function learnedSet(week, type) {
        const all = lessonStore();
        return new Set(all[week + ":" + type] || []);
    }

    function markLearned(week, type, id) {
        const all = lessonStore();
        const key = week + ":" + type;
        const set = new Set(all[key] || []);
        if (set.has(id)) return;
        set.add(id);
        all[key] = Array.from(set);
        storeSet(LESSON_KEY, all);
    }

    function testStore() { return storeGet(TEST_KEY, {}); }

    function saveTestScore(scope, type, correct, total) {
        const all = testStore();
        const key = scope + ":" + type;
        const entry = all[key] || { best: 0, last: 0, runs: 0 };
        const pct = total ? Math.round((correct / total) * 100) : 0;
        entry.last = pct;
        entry.best = Math.max(entry.best || 0, pct);
        entry.runs = (entry.runs || 0) + 1;
        all[key] = entry;
        storeSet(TEST_KEY, all);
    }

    function pctText(learned, total) {
        return total ? Math.round((learned / total) * 100) + "%" : "0%";
    }

    // ---------- home ----------

    function initHome() {
        const learned = lessonStore();
        const perType = { radicals: 0, kanji: 0, vocab: 0 };
        Object.keys(learned).forEach(function (key) {
            const type = key.split(":")[1];
            if (perType[type] !== undefined) perType[type] += (learned[key] || []).length;
        });

        const totalsEl = $("overall-bars");
        const totals = totalsEl ? JSON.parse(totalsEl.getAttribute("data-totals")) : {};
        Object.keys(perType).forEach(function (type) {
            const fill = document.querySelector('[data-fill="' + type + '"]');
            const count = document.querySelector('[data-count="' + type + '"]');
            const total = totals[type] || 0;
            const done = Math.min(perType[type], total);
            if (fill) fill.style.width = pctText(done, total);
            if (count) count.textContent = done + " / " + total;
        });

        qsa(".week-progress").forEach(function (el) {
            const week = el.getAttribute("data-week");
            let done = 0;
            let total = 0;
            ["radicals", "kanji", "vocab"].forEach(function (type) {
                const learnedCount = (learned[week + ":" + type] || []).length;
                const typeTotal = Number(el.getAttribute("data-" + type) || 0);
                done += Math.min(learnedCount, typeTotal);
                total += typeTotal;
            });
            const fill = el.querySelector('[data-fill="overall"]');
            const text = el.querySelector("[data-text]");
            const pct = total ? Math.round((done / total) * 100) : 0;
            if (fill) fill.style.width = pct + "%";
            if (text) text.textContent = pct + "%";
        });
    }

    // ---------- week ----------

    function initWeek(week) {
        qsa("[data-progress-type]").forEach(function (card) {
            const type = card.getAttribute("data-progress-type");
            const total = Number(card.getAttribute("data-total") || 0);
            const done = Math.min(learnedSet(week, type).size, total);
            const fill = card.querySelector('[data-fill="lesson"]');
            const state = card.querySelector("[data-state]");
            if (fill) fill.style.width = pctText(done, total);
            if (state) {
                state.textContent = done >= total && total > 0
                    ? done + " / " + total
                    : done + " / " + total;
                if (done >= total && total > 0) state.classList.add("complete");
            }
        });

        const tests = testStore();
        qsa("[data-test-type]").forEach(function (card) {
            const type = card.getAttribute("data-test-type");
            const entry = tests[week + ":" + type];
            const el = card.querySelector("[data-score]");
            if (el && entry) el.textContent = "★ " + entry.best + "% · " + entry.runs + "×";
        });
    }

    // ---------- lesson player ----------

    function initLesson() {
        const data = pageData();
        const T = uiStrings();
        const items = data.items || [];
        if (!items.length) {
            $("lesson-card").innerHTML = '<p class="muted">' + escapeHtml(T.no_items || "") + "</p>";
            return;
        }

        let idx = 0;

        function renderItem() {
            const item = items[idx];
            const glyph = $("item-glyph");
            glyph.innerHTML = glyphHtml(item.char, item.image, "item-glyph-img");
            $("item-meaning").textContent = item.meaning || "";
            $("item-readings").textContent = item.reading_display || "";

            const radicals = $("item-radicals");
            radicals.innerHTML = (item.radicals || []).map(function (r) {
                return '<span class="mini-chip"><span class="mini-glyph">' +
                    glyphHtml(r.char, r.image, "mini-glyph-img") + "</span>" +
                    '<span class="mini-name">' + escapeHtml(r.meaning) + "</span></span>";
            }).join("");
            radicals.classList.toggle("hidden", !(item.radicals || []).length);

            const kanjiBox = $("item-kanji");
            kanjiBox.innerHTML = (item.kanji || []).map(function (c) {
                return '<span class="mini-chip"><span class="mini-glyph">' +
                    escapeHtml(c) + "</span></span>";
            }).join("");
            kanjiBox.classList.toggle("hidden", !(item.kanji || []).length);

            const extra = $("item-extra");
            let extraHtml = "";
            if (item.example && item.example.jp) {
                extraHtml += '<div class="example-jp">' + escapeHtml(item.example.jp) + "</div>" +
                    '<div class="example-en">' + escapeHtml(item.example.en || "") + "</div>";
            }
            if ((item.compounds || []).length) {
                extraHtml += '<div class="compound-list">' + item.compounds.map(function (c) {
                    return '<span class="compound-item"><strong>' + escapeHtml(c.word) +
                        "</strong> " + escapeHtml(c.reading) + " · " + escapeHtml(c.meaning) + "</span>";
                }).join("") + "</div>";
            }
            extra.innerHTML = extraHtml;

            const links = $("item-links");
            links.innerHTML = item.url
                ? '<a class="ext-link" href="' + escapeHtml(item.url) +
                  '" target="_blank" rel="noopener">↗ ' + escapeHtml(T.wani_open || "WaniKani") + "</a>"
                : "";

            $("lesson-progress-text").textContent =
                (T.lesson_progress || "{pos} / {total}")
                    .replace("{pos}", idx + 1).replace("{total}", items.length);
            $("lesson-progress-fill").style.width = ((idx + 1) / items.length * 100) + "%";
            $("prev-btn").disabled = idx === 0;
            $("next-btn").textContent = idx === items.length - 1
                ? (T.lesson_done || "Done") : (T.btn_next || "Next →");

            markLearned(data.week, data.type, item.id);
        }

        $("prev-btn").addEventListener("click", function () {
            if (idx > 0) { idx--; renderItem(); }
        });

        $("next-btn").addEventListener("click", function () {
            if (idx < items.length - 1) {
                idx++;
                renderItem();
            } else {
                $("lesson-shell").classList.add("hidden");
                $("lesson-done").classList.remove("hidden");
            }
        });

        $("go-test-link").setAttribute("href", data.test_url || "#");
        renderItem();
    }

    // ---------- tests ----------

    function initTest() {
        const data = pageData();
        const T = uiStrings();
        const items = data.items || [];

        if (!items.length) {
            $("question-card").innerHTML = '<p class="muted">' + escapeHtml(T.no_items || "") + "</p>";
            return;
        }

        function buildQuestions() {
            const qs = [];
            items.forEach(function (item) {
                qs.push({
                    kind: "meaning",
                    char: item.char,
                    image: item.image,
                    answers: item.meanings || [],
                    shown: (item.meanings || [])[0] || "",
                });
                if ((item.readings || []).length) {
                    qs.push({
                        kind: "reading",
                        char: item.char,
                        image: item.image,
                        answers: item.readings,
                        shown: item.readings[0],
                    });
                }
            });
            return qs;
        }

        let state = null;

        function start(questions) {
            state = {
                queue: shuffle(questions),
                idx: 0,
                correct: 0,
                wrong: 0,
                wrongItems: [],
                answered: false,
            };
            $("test-result").classList.add("hidden");
            $("test-shell").classList.remove("hidden");
            updateScores();
            showQuestion();
        }

        function updateScores() {
            $("score-correct").textContent = state.correct;
            $("score-wrong").textContent = state.wrong;
        }

        function currentQuestion() { return state.queue[state.idx]; }

        function showQuestion() {
            const q = currentQuestion();
            state.answered = false;
            const askKey = (q.kind === "meaning" ? "q_meaning_" : "q_reading_") + data.type;
            $("question-label").textContent = T[askKey] ||
                (q.kind === "meaning" ? "Meaning?" : "Reading?");
            $("question-glyph").innerHTML = glyphHtml(q.char, q.image, "item-glyph-img");
            const input = $("answer-input");
            input.value = "";
            input.disabled = false;
            input.placeholder = q.kind === "meaning"
                ? (T.placeholder_meaning || "meaning…")
                : (T.placeholder_reading || "reading…");
            input.focus();
            $("question-feedback").classList.add("hidden");
            $("question-feedback").textContent = "";
            $("check-btn").classList.remove("hidden");
            $("show-btn").classList.remove("hidden");
            $("continue-btn").classList.add("hidden");
            $("test-progress-text").textContent =
                (T.question_of || "{pos} / {total}")
                    .replace("{pos}", state.idx + 1).replace("{total}", state.queue.length);
            $("test-progress-fill").style.width =
                ((state.idx) / state.queue.length * 100) + "%";
        }

        function settle(correct) {
            const q = currentQuestion();
            state.answered = true;
            $("answer-input").disabled = true;
            $("check-btn").classList.add("hidden");
            $("show-btn").classList.add("hidden");
            $("continue-btn").classList.remove("hidden");
            $("continue-btn").focus();

            const fb = $("question-feedback");
            fb.classList.remove("hidden", "correct", "wrong");
            if (correct) {
                state.correct++;
                fb.classList.add("correct");
                fb.innerHTML = "✅ " + escapeHtml(T.correct || "Correct");
            } else {
                state.wrong++;
                state.wrongItems.push(q);
                fb.classList.add("wrong");
                fb.innerHTML = "❌ " + escapeHtml(T.incorrect || "Incorrect") +
                    '<div class="answer-was">' + escapeHtml(T.answer_was || "Answer") +
                    ": " + escapeHtml(q.shown) + "</div>";
            }
            updateScores();
        }

        function check() {
            if (state.answered) { next(); return; }
            const q = currentQuestion();
            settle(matches($("answer-input").value, q.answers));
        }

        function next() {
            if (!state.answered) return;
            if (state.idx + 1 >= state.queue.length) {
                finish();
                return;
            }
            state.idx++;
            showQuestion();
        }

        function finish() {
            $("test-progress-fill").style.width = "100%";
            $("test-shell").classList.add("hidden");
            $("test-result").classList.remove("hidden");

            const total = state.correct + state.wrong;
            const pct = total ? Math.round((state.correct / total) * 100) : 0;
            $("final-correct").textContent = state.correct;
            $("final-wrong").textContent = state.wrong;
            $("final-pct").textContent = pct + "%";

            const review = $("wrong-review");
            const list = $("wrong-list");
            if (state.wrongItems.length) {
                review.classList.remove("hidden");
                list.innerHTML = state.wrongItems.map(function (q) {
                    return '<div class="wrong-item"><span class="wrong-glyph">' +
                        escapeHtml(q.char) + "</span><span>" + escapeHtml(q.shown) + "</span></div>";
                }).join("");
            } else {
                review.classList.add("hidden");
            }
            $("retry-wrong-btn").classList.toggle("hidden", !state.wrongItems.length);

            saveTestScore(data.scope, data.type, state.correct, total);
        }

        $("check-btn").addEventListener("click", check);
        $("continue-btn").addEventListener("click", next);
        $("show-btn").addEventListener("click", function () {
            if (state.answered) return;
            const q = currentQuestion();
            $("answer-input").value = q.shown;
            settle(false);
        });
        $("answer-input").addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                if (state.answered) next(); else check();
            }
        });
        $("retake-btn").addEventListener("click", function () {
            start(buildQuestions());
        });
        $("retry-wrong-btn").addEventListener("click", function () {
            const retry = state.wrongItems.slice();
            start(retry);
        });

        start(buildQuestions());
    }

    window.N3App.initHome = initHome;
    window.N3App.initWeek = initWeek;
    window.N3App.initLesson = initLesson;
    window.N3App.initTest = initTest;
})();
