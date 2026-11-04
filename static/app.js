/* N3 Kanji study app — lesson player and repeatable tests.
   Page data arrives as JSON in <script id="page-data">; UI strings in
   <script id="i18n-strings">. Progress and scores live in localStorage. */

window.N3App = window.N3App || {};

(function () {
    "use strict";

    const LESSON_KEY = "n3lesson:v1";
    const TEST_KEY = "n3test:v1";
    const RANGE_KEY = "n3range:v1";

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

    // ---------- grading ----------

    /* Leading "to "/article is optional on both sides ("To Turn Toward" =
       "turn toward"). Runs twice so "to the park" loses both. */
    function stripLead(s) {
        let prev;
        let out = s;
        do {
            prev = out;
            out = out.replace(/^(?:to|a|an|the)\s+/, "");
        } while (out !== prev);
        return out;
    }

    function splitAlternatives(s) {
        return String(s || "").split(/\s*[,/;、；]\s*/);
    }

    /* F4: typo tolerance only for long alternatives, and only for a
       same-length substitution — so "residents"/"residentt" stay wrong for
       "resident" while "restaraunt" still passes for "restaurant". */
    function nearMiss(user, alt) {
        return alt.length >= 8 && user.length === alt.length && levenshtein(user, alt) <= 1;
    }

    function matchesMeaning(user, answers) {
        const u = normalize(user);
        if (!u) return false;
        const uForms = [u, stripLead(u)];
        for (const answer of answers || []) {
            for (const part of splitAlternatives(answer)) {
                const alt = normalize(part);
                if (!alt) continue;
                const aForms = [alt, stripLead(alt)];
                for (const a of uForms) {
                    for (const b of aForms) {
                        if (a === b) return true;
                        if (nearMiss(a, b)) return true;
                    }
                }
            }
        }
        return false;
    }

    /* Readings accept kana (hiragana or katakana) and romaji, Hepburn or
       kunrei, with long-vowel variants. */
    function matchesReading(user, answers) {
        const raw = String(user || "").trim();
        if (!raw) return false;
        const converter = window.N3Romaji;
        const candidates = converter ? converter.candidates(raw) : [normalize(raw)];
        for (const cand of candidates) {
            if (!cand) continue;
            for (const answer of answers || []) {
                for (const part of splitAlternatives(answer)) {
                    const alt = normalize(part);
                    if (!alt) continue;
                    if (cand === alt) return true;
                    if (nearMiss(cand, alt)) return true;
                }
            }
        }
        return false;
    }

    function matches(user, question) {
        // B9: an empty box is never a submission.
        if (!String(user === undefined || user === null ? "" : user).trim()) return false;
        if (question.kind === "reading") return matchesReading(user, question.answers);
        return matchesMeaning(user, question.answers);
    }

    function glyphHtml(char, image, cls, alt) {
        if (image) {
            return '<img class="' + (cls || "item-glyph-img") + '" src="' +
                escapeHtml(image) + '" alt="' + escapeHtml(alt || char || "") + '">';
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

    /* One key scheme, shared with initWeek: "<scope>:<type>", scope being
       "week4" or "all". Retries are counted separately and never touch
       best/last (B7). */
    function saveTestScore(scope, type, correct, total) {
        const all = testStore();
        const key = scope + ":" + type;
        const entry = all[key] || { best: 0, last: 0, runs: 0, retries: 0 };
        const pct = total ? Math.round((correct / total) * 100) : 0;
        entry.last = pct;
        entry.best = Math.max(entry.best || 0, pct);
        entry.runs = (entry.runs || 0) + 1;
        all[key] = entry;
        storeSet(TEST_KEY, all);
    }

    function recordRetry(scope, type) {
        const all = testStore();
        const key = scope + ":" + type;
        const entry = all[key] || { best: 0, last: 0, runs: 0, retries: 0 };
        entry.retries = (entry.retries || 0) + 1;
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
                state.textContent = done + " / " + total;
                state.classList.toggle("complete", done >= total && total > 0);
            }
        });

        const tests = testStore();
        qsa("[data-test-type]").forEach(function (card) {
            const type = card.getAttribute("data-test-type");
            const entry = tests["week" + week + ":" + type];
            const el = card.querySelector("[data-score]");
            if (el && entry && entry.runs) {
                el.textContent = "★ " + entry.best + "% · " + entry.runs + "×";
            }
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
            glyph.innerHTML = glyphHtml(item.char, item.image, "item-glyph-img", item.alt);
            $("item-meaning").textContent = item.meaning || "";
            $("item-readings").textContent = item.reading_display || "";

            const radicals = $("item-radicals");
            radicals.innerHTML = (item.radicals || []).map(function (r) {
                return '<span class="mini-chip"><span class="mini-glyph">' +
                    glyphHtml(r.char, r.image, "mini-glyph-img", r.meaning) + "</span>" +
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
        const allItems = data.items || [];
        const scopeKey = data.scope + ":" + data.type;

        const panel = $("range-panel");
        const fromInput = $("range-from");
        const toInput = $("range-to");
        const startBtn = $("start-btn");
        const ofLabel = $("range-of");
        const hint = $("range-hint");

        if (!allItems.length) {
            if (panel) panel.classList.add("hidden");
            $("test-top").classList.add("hidden");
            $("question-card").classList.remove("hidden");
            $("question-card").innerHTML = '<p class="muted">' + escapeHtml(T.no_items || "") + "</p>";
            return;
        }

        // ----- range (items 1..N, inclusive) -----

        function storedRange() {
            const all = storeGet(RANGE_KEY, {});
            return all[scopeKey] || null;
        }

        function saveRange(range) {
            const all = storeGet(RANGE_KEY, {});
            all[scopeKey] = range;
            storeSet(RANGE_KEY, all);
        }

        function urlRange() {
            if (!window.location || !window.location.search) return null;
            const params = new URLSearchParams(window.location.search);
            const from = parseInt(params.get("from"), 10);
            const to = parseInt(params.get("to"), 10);
            if (!isFinite(from) && !isFinite(to)) return null;
            return { from: isFinite(from) ? from : null, to: isFinite(to) ? to : null };
        }

        function clampRange(range) {
            const max = allItems.length;
            let from = Math.round(Number(range.from));
            let to = Math.round(Number(range.to));
            if (!isFinite(from)) from = 1;
            if (!isFinite(to)) to = max;
            from = Math.min(Math.max(from, 1), max);
            to = Math.min(Math.max(to, 1), max);
            if (from > to) { const swap = from; from = to; to = swap; }
            return { from: from, to: to };
        }

        function selectedItems(range) {
            return allItems.slice(range.from - 1, range.to);
        }

        function questionsFor(items) {
            let count = 0;
            items.forEach(function (item) {
                count += 1;                                    // meaning
                if ((item.readings || []).length) count += 1;  // reading
            });
            return count;
        }

        function initialRange() {
            const url = urlRange();
            const saved = storedRange();
            return clampRange({
                from: (url && url.from) || (saved && saved.from) || 1,
                to: (url && url.to) || (saved && saved.to) || allItems.length,
            });
        }

        function readInputs() {
            return clampRange({ from: fromInput.value, to: toInput.value });
        }

        function updatePreview() {
            const range = readInputs();
            const items = selectedItems(range);
            const count = questionsFor(items);
            ofLabel.textContent = (T.range_of || "{count} items")
                .replace("{count}", allItems.length);
            hint.textContent = (T.range_questions || "= {count} questions")
                .replace("{count}", count);
            hint.classList.toggle("invalid", !items.length);
            startBtn.disabled = !items.length;
        }

        const range0 = initialRange();
        fromInput.value = range0.from;
        toInput.value = range0.to;
        fromInput.max = allItems.length;
        toInput.max = allItems.length;
        updatePreview();

        fromInput.addEventListener("input", updatePreview);
        toInput.addEventListener("input", updatePreview);
        fromInput.addEventListener("change", function () {
            const range = readInputs();
            fromInput.value = range.from;
            toInput.value = range.to;
            updatePreview();
        });
        toInput.addEventListener("change", function () {
            const range = readInputs();
            fromInput.value = range.from;
            toInput.value = range.to;
            updatePreview();
        });

        function buildQuestions(items) {
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

        function start(questions, isRetry) {
            state = {
                queue: shuffle(questions),
                idx: 0,
                correct: 0,
                wrong: 0,
                wrongItems: [],
                answered: false,
                isRetry: !!isRetry,
            };
            if (panel) panel.classList.add("hidden");
            $("test-result").classList.add("hidden");
            $("test-shell").classList.remove("hidden");
            $("test-top").classList.remove("hidden");
            $("question-card").classList.remove("hidden");
            updateScores();
            showQuestion();
        }

        function updateScores() {
            $("score-correct").textContent = state.correct;
            $("score-wrong").textContent = state.wrong;
        }

        function currentQuestion() { return state.queue[state.idx]; }

        function showRangePanel() {
            $("test-shell").classList.remove("hidden");
            if (panel) panel.classList.remove("hidden");
            $("test-top").classList.add("hidden");
            $("question-card").classList.add("hidden");
            $("test-result").classList.add("hidden");
            updatePreview();
        }

        function showQuestion() {
            const q = currentQuestion();
            state.answered = false;
            const askKey = (q.kind === "meaning" ? "q_meaning_" : "q_reading_") + data.type;
            const label = T[askKey] || (q.kind === "meaning" ? "Meaning?" : "Reading?");
            $("question-label").textContent = label;
            $("question-glyph").innerHTML = glyphHtml(q.char, q.image, "item-glyph-img");
            const input = $("answer-input");
            input.value = "";
            input.disabled = false;
            input.classList.remove("correct", "wrong");
            input.setAttribute("aria-label", label);
            input.placeholder = q.kind === "meaning"
                ? (T.placeholder_meaning || "meaning…")
                : (T.placeholder_reading || "romaji or kana…");
            input.focus();
            $("kana-preview").classList.add("hidden");
            $("kana-preview").textContent = "";
            $("question-feedback").classList.add("hidden");
            $("question-feedback").textContent = "";
            $("check-btn").disabled = true;
            $("check-btn").classList.remove("hidden");
            $("show-btn").classList.remove("hidden");
            $("continue-btn").classList.add("hidden");
            $("test-progress-text").textContent =
                (T.question_of || "{pos} / {total}")
                    .replace("{pos}", state.idx + 1).replace("{total}", state.queue.length);
            $("test-progress-fill").style.width =
                ((state.idx + 1) / state.queue.length * 100) + "%";
        }

        function settle(correct) {
            const q = currentQuestion();
            state.answered = true;
            const input = $("answer-input");
            input.disabled = true;
            input.classList.remove("correct", "wrong");
            input.classList.add(correct ? "correct" : "wrong");
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
            if (!state || state.answered) return;
            const value = $("answer-input").value;
            if (!value || !value.trim()) return;   // B9: nothing typed, nothing submitted
            settle(matches(value, currentQuestion()));
        }

        function next() {
            if (!state || !state.answered) return;
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
                    const glyph = q.image
                        ? '<img class="wrong-glyph-img" src="' + escapeHtml(q.image) +
                          '" alt="' + escapeHtml(q.char || "") + '">'
                        : '<span class="wrong-glyph">' + escapeHtml(q.char) + "</span>";
                    return '<div class="wrong-item">' + glyph +
                        "<span>" + escapeHtml(q.shown) + "</span></div>";
                }).join("");
            } else {
                review.classList.add("hidden");
            }
            $("retry-wrong-btn").classList.toggle("hidden", !state.wrongItems.length);

            // A retry of the wrong answers is not a run of the whole test:
            // it is counted, but best/last must not move (B7).
            if (state.isRetry) {
                recordRetry(data.scope, data.type);
            } else {
                saveTestScore(data.scope, data.type, state.correct, total);
            }
        }

        function updateKanaPreview() {
            const el = $("kana-preview");
            const q = state ? currentQuestion() : null;
            const value = $("answer-input").value;
            const wantsRomaji = q && q.kind === "reading" &&
                /[A-Za-z]/.test(value) && window.N3Romaji;
            if (!wantsRomaji) {
                el.classList.add("hidden");
                el.textContent = "";
                return;
            }
            el.textContent = "→ " + window.N3Romaji.toKana(value);
            el.classList.remove("hidden");
        }

        startBtn.addEventListener("click", function () {
            const range = readInputs();
            fromInput.value = range.from;
            toInput.value = range.to;
            saveRange(range);
            start(buildQuestions(selectedItems(range)), false);
        });

        $("check-btn").addEventListener("click", check);
        $("continue-btn").addEventListener("click", next);
        $("show-btn").addEventListener("click", function () {
            if (!state || state.answered) return;
            const q = currentQuestion();
            $("answer-input").value = q.shown;
            settle(false);
        });
        $("answer-input").addEventListener("input", function () {
            $("check-btn").disabled = !this.value.trim();
            updateKanaPreview();
        });
        $("answer-input").addEventListener("keydown", function (e) {
            if (e.key === "Enter") {
                if (state && state.answered) next(); else check();
            }
        });
        $("retake-btn").addEventListener("click", function () {
            state = null;
            showRangePanel();
        });
        $("retry-wrong-btn").addEventListener("click", function () {
            if (!state) return;
            const retry = state.wrongItems.slice();
            start(retry, true);
        });

        showRangePanel();
    }

    window.N3App.initHome = initHome;
    window.N3App.initWeek = initWeek;
    window.N3App.initLesson = initLesson;
    window.N3App.initTest = initTest;
})();
