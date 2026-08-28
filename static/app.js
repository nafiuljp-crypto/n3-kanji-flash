/* N3 Kanji Flash Card — Game logic
   Handles both flash card and exercise game modes.
   UI strings come from the page's i18n-strings JSON (server-rendered). */

window.N3App = window.N3App || {};

(function () {
    "use strict";

    // ---------- helpers ----------

    function $(id) { return document.getElementById(id); }
    function qs(sel, ctx) { return (ctx || document).querySelector(sel); }
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

    function getI18n() {
        const el = document.getElementById("i18n-strings");
        if (!el) return {};
        try { return JSON.parse(el.textContent); } catch (e) { return {}; }
    }

    /** Normalize answer for comparison. */
    function normalize(s) {
        if (!s) return "";
        return String(s).trim().toLowerCase()
            .replace(/\s+/g, " ")
            .replace(/[　]/g, " ")
            .replace(/[･-ﾟ]/g, ch =>
                String.fromCharCode(ch.charCodeAt(0) - 0xFF65 + 0x30A1));
    }

    function levenshtein(a, b) {
        if (a === b) return 0;
        if (!a.length) return b.length;
        if (!b.length) return a.length;
        const m = [];
        for (let i = 0; i <= b.length; i++) m[i] = [i];
        for (let j = 0; j <= a.length; j++) m[0][j] = j;
        for (let i = 1; i <= b.length; i++) {
            for (let j = 1; j <= a.length; j++) {
                if (b[i - 1] === a[j - 1]) {
                    m[i][j] = m[i - 1][j - 1];
                } else {
                    m[i][j] = Math.min(m[i - 1][j - 1] + 1, m[i][j - 1] + 1, m[i - 1][j] + 1);
                }
            }
        }
        return m[b.length][a.length];
    }

    function fuzzyMatch(user, expected) {
        const u = normalize(user);
        const e = normalize(expected);
        if (!u || !e) return false;
        if (u === e) return true;
        const alts = e.split(/\s*[|,／/、]\s*/);
        for (const alt of alts) {
            if (u === alt) return true;
            if (alt.length >= 4 && levenshtein(u, alt) <= 1) return true;
        }
        return false;
    }

    function getAcceptableAnswers(kanji, mode) {
        const out = [];
        if (mode === "reading") {
            if (kanji.onyomi) out.push(kanji.onyomi);
            if (kanji.kunyomi) out.push(kanji.kunyomi);
            (kanji.compounds || []).forEach(c => { if (c.reading) out.push(c.reading); });
        } else {
            if (kanji.meaning) out.push(kanji.meaning);
            (kanji.compounds || []).forEach(c => { if (c.meaning) out.push(c.meaning); });
        }
        return out;
    }

    // ---------- Flash card game ----------

    function initFlashcard(week, day) {
        const dataEl = $("lesson-data");
        if (!dataEl) return;
        const lesson = JSON.parse(dataEl.textContent);
        const kanjiList = lesson.kanji || [];
        if (!kanjiList.length) return;
        const T = getI18n();

        const state = {
            idx: 0,
            mode: "meaning",
            score: { correct: 0, wrong: 0 },
            answered: false,
        };

        const els = {
            kanji: $("kanji-display"),
            stroke: $("stroke-count"),
            kid: $("kanji-id"),
            input: $("answer-input"),
            submit: $("submit-btn"),
            reveal: $("reveal-btn"),
            cardBack: $("card-back"),
            card: $("flashcard"),
            progressFill: $("progress-fill"),
            progressText: $("progress-text"),
            scoreCorrect: $("score-correct"),
            scoreWrong: $("score-wrong"),
            nextBtn: $("next-btn"),
            result: $("result-banner"),
            ansReading: $("answer-reading"),
            ansMeaning: $("answer-meaning"),
            compounds: $("compounds-list"),
            exampleSection: $("example-section"),
            exampleJp: $("example-jp"),
            exampleEn: $("example-en"),
            cardQuestion: $("card-question"),
            modeLabel: $("mode-label"),
            modeMeaning: $("mode-meaning"),
            modeReading: $("mode-reading"),
            kanjiList: qsa(".kanji-list-item"),
        };

        function updateProgress() {
            const pct = ((state.idx + 1) / kanjiList.length) * 100;
            els.progressFill.style.width = pct + "%";
            els.progressText.textContent = (state.idx + 1) + " / " + kanjiList.length;
        }

        function updateScore() {
            els.scoreCorrect.textContent = state.score.correct;
            els.scoreWrong.textContent = state.score.wrong;
        }

        function updatePlaceholder() {
            els.input.placeholder = state.mode === "meaning"
                ? (T.placeholder_meaning || "Type the English meaning…")
                : (T.placeholder_reading || "Type the reading (kana)…");
        }

        function updateQuestionText() {
            const tpl = state.mode === "meaning"
                ? (T.what_is_meaning || 'What is the <span id="mode-label">meaning</span> of this kanji?')
                : (T.what_is_reading || 'What is the <span id="mode-label">reading</span> of this kanji?');
            els.cardQuestion.innerHTML = tpl;
        }

        function showCurrent() {
            const k = kanjiList[state.idx];
            els.kanji.textContent = k.char;
            els.stroke.textContent = k.stroke || "?";
            els.kid.textContent = k.id || (state.idx + 1);
            els.input.value = "";
            els.input.className = "answer-input";
            updatePlaceholder();
            els.input.disabled = false;
            els.submit.disabled = false;
            els.cardBack.classList.add("hidden");
            qs(".card-front").classList.remove("hidden");
            els.card.classList.remove("correct", "wrong");
            state.answered = false;
            els.input.focus();
            updateProgress();
            els.kanjiList.forEach((el, i) => {
                el.classList.toggle("current", i === state.idx);
            });
        }

        function buildBack(k) {
            els.ansReading.textContent = (k.onyomi || "—") + (k.kunyomi ? " / " + k.kunyomi : "");
            els.ansMeaning.textContent = k.meaning || "—";

            els.compounds.innerHTML = "";
            (k.compounds || []).forEach(c => {
                const div = document.createElement("div");
                div.className = "compound-item";
                div.innerHTML =
                    '<span class="compound-word">' + escapeHtml(c.word) + '</span>' +
                    '<span class="compound-reading">' + escapeHtml(c.reading) + '</span>' +
                    '<span class="compound-meaning">' + escapeHtml(c.meaning) + '</span>';
                els.compounds.appendChild(div);
            });

            if (k.example && (k.example.jp || k.example.furigana)) {
                els.exampleSection.classList.remove("hidden");
                const jpHtml = k.example.furigana
                    ? escapeHtml(k.example.furigana)
                    : escapeHtml(k.example.jp || "");
                els.exampleJp.innerHTML = jpHtml;
                els.exampleEn.textContent = k.example.en || "";
            } else if (k.example && k.example.jp) {
                els.exampleSection.classList.remove("hidden");
                els.exampleJp.textContent = k.example.jp;
                els.exampleEn.textContent = k.example.en || "";
            } else {
                els.exampleSection.classList.add("hidden");
            }
        }

        function submitAnswer() {
            if (state.answered) {
                next();
                return;
            }
            const k = kanjiList[state.idx];
            const userAns = els.input.value;
            const correct = fuzzyMatch(userAns, getAcceptableAnswers(k, state.mode).join("|"));

            state.answered = true;
            els.input.disabled = true;
            els.submit.disabled = true;

            if (correct) {
                state.score.correct++;
                els.result.className = "result-banner correct";
                els.result.textContent = T.result_correct || "✅ Correct!";
                els.card.classList.add("correct");
                els.input.classList.add("correct");
                els.kanjiList[state.idx].classList.add("correct");
            } else {
                state.score.wrong++;
                els.result.className = "result-banner wrong";
                els.result.textContent = T.result_wrong || "❌ Incorrect";
                els.card.classList.add("wrong");
                els.input.classList.add("wrong");
                els.kanjiList[state.idx].classList.add("wrong");
            }
            updateScore();
            buildBack(k);

            qs(".card-front").classList.add("hidden");
            els.cardBack.classList.remove("hidden");
            els.nextBtn.focus();
        }

        function next() {
            if (state.idx + 1 >= kanjiList.length) {
                showSummary();
                return;
            }
            state.idx++;
            showCurrent();
        }

        function showSummary() {
            const total = state.score.correct + state.score.wrong;
            const pct = total ? Math.round((state.score.correct / total) * 100) : 0;
            const backTo = (T.back_to_week || "Back to Week {week}").replace("{week}", week);
            els.card.innerHTML =
                '<div class="card-back">' +
                '  <h2>' + escapeHtml(T.summary_complete || "Complete!") + '</h2>' +
                '  <div class="result-stats">' +
                '    <div class="stat-card"><div class="stat-num">' + state.score.correct + '</div><div class="stat-label">' + escapeHtml(T.lbl_correct || "Correct") + '</div></div>' +
                '    <div class="stat-card"><div class="stat-num">' + state.score.wrong + '</div><div class="stat-label">' + escapeHtml(T.lbl_wrong || "Wrong") + '</div></div>' +
                '    <div class="stat-card"><div class="stat-num">' + pct + '%</div><div class="stat-label">' + escapeHtml(T.lbl_accuracy || "Accuracy") + '</div></div>' +
                '  </div>' +
                '  <div class="result-actions">' +
                '    <button id="restart-btn" class="btn btn-primary">' + escapeHtml(T.btn_try_again || "Try again") + '</button>' +
                '    <a href="/chapter/' + week + '" class="btn btn-link">' + escapeHtml(backTo) + '</a>' +
                '  </div>' +
                '</div>';
            $("restart-btn").addEventListener("click", () => location.reload());
        }

        function setMode(mode) {
            state.mode = mode;
            els.modeMeaning.classList.toggle("active", mode === "meaning");
            els.modeReading.classList.toggle("active", mode === "reading");
            updateQuestionText();
            updatePlaceholder();
        }

        // Wire up events
        els.submit.addEventListener("click", submitAnswer);
        els.input.addEventListener("keydown", e => { if (e.key === "Enter") submitAnswer(); });
        els.reveal.addEventListener("click", () => {
            els.input.value = getAcceptableAnswers(kanjiList[state.idx], state.mode)[0] || "";
            submitAnswer();
        });
        els.nextBtn.addEventListener("click", next);
        els.modeMeaning.addEventListener("click", () => setMode("meaning"));
        els.modeReading.addEventListener("click", () => setMode("reading"));

        els.kanjiList.forEach((el, i) => {
            el.addEventListener("click", () => {
                state.idx = i;
                showCurrent();
            });
        });

        showCurrent();
        updateScore();
    }

    // ---------- Exercise game ----------

    function initExercise(week, mode) {
        const T = getI18n();
        const dataEl = document.getElementById("exercise-data");
        let questions = [];
        if (dataEl) {
            try {
                questions = JSON.parse(dataEl.textContent) || [];
            } catch (e) {
                questions = [];
            }
        }

        const state = {
            idx: 0,
            score: { correct: 0, wrong: 0 },
            questions: questions,
        };

        const els = {
            area: $("question-area"),
            result: $("result-screen"),
            progressFill: $("progress-fill"),
            progressText: $("progress-text"),
            scoreCorrect: $("score-correct"),
            scoreWrong: $("score-wrong"),
        };

        function updateProgress() {
            const pct = ((state.idx + 1) / state.questions.length) * 100;
            els.progressFill.style.width = pct + "%";
            els.progressText.textContent = (state.idx + 1) + " / " + state.questions.length;
        }

        function updateScore() {
            els.scoreCorrect.textContent = state.score.correct;
            els.scoreWrong.textContent = state.score.wrong;
        }

        function renderStem(q) {
            let html = "";
            const stem = q.stem || "";
            let header = "";
            if (q.section) {
                const labels = {
                    1: T.section_1 || "Section 1 — Reading",
                    2: T.section_2 || "Section 2 — Write the kanji",
                    3: T.section_3 || "Section 3 — Fill in the kanji",
                };
                const tpl = labels[q.section] || (T.section_n || "Section {n}").replace("{n}", q.section);
                header = '<div class="q-section-label">' + escapeHtml(tpl) + '</div>';
            }
            const prefix = T.reading_hint_prefix || "(reading: ";
            if (q.options && q.options.length && q.options[0].kanji) {
                html = header + '<div class="q-stem">' + escapeHtml(stem);
                if (q.reading_hint) html += '<br><small>' + escapeHtml(prefix) + escapeHtml(q.reading_hint) + ')</small>';
                html += '</div>';
            } else {
                html = header + '<div class="q-stem">' + escapeHtml(stem) + '</div>';
            }
            return html;
        }

        function renderOptions(q) {
            const opts = q.options || [];
            const isQuiz = opts.length && opts[0].kanji;
            const out = ['<div class="q-options">'];
            opts.forEach((o, i) => {
                const labelText = o.label || String(i + 1);
                let contentHtml = "";
                if (isQuiz) {
                    contentHtml = '<span class="opt-kanji">' + escapeHtml(o.kanji) + '</span>';
                } else {
                    contentHtml = '<span class="opt-text">' + escapeHtml(o.text || "") + '</span>';
                }
                out.push(
                    '<button class="q-option" data-label="' + escapeHtml(labelText) + '">' +
                    '<span class="opt-label">' + escapeHtml(labelText) + '</span>' +
                    contentHtml +
                    '</button>'
                );
            });
            out.push('</div>');
            return out.join("");
        }

        function showCurrent() {
            const q = state.questions[state.idx];
            let html = renderStem(q);
            html += renderOptions(q);
            els.area.innerHTML = html;

            const buttons = qsa(".q-option", els.area);
            buttons.forEach(btn => {
                btn.addEventListener("click", () => handleAnswer(btn, q));
            });
            updateProgress();
        }

        function handleAnswer(btn, q) {
            const label = btn.getAttribute("data-label");
            const buttons = qsa(".q-option", els.area);
            buttons.forEach(b => b.disabled = true);

            // Look up the correct answer in the embedded data (no API call).
            const fullQ = state.questions.find(x => x.id === q.id) || q;
            const correct = String(fullQ.answer != null ? fullQ.answer : "");
            if (label === correct) {
                state.score.correct++;
                btn.classList.add("correct");
            } else {
                state.score.wrong++;
                btn.classList.add("wrong");
                buttons.forEach(b => {
                    if (b.getAttribute("data-label") === correct) b.classList.add("correct");
                });
            }
            updateScore();

            if (fullQ.explanation) {
                const expl = document.createElement("div");
                expl.className = "q-explanation";
                expl.textContent = fullQ.explanation;
                els.area.appendChild(expl);
            }

            const nextBtn = document.createElement("button");
            nextBtn.className = "btn btn-primary";
            nextBtn.textContent = state.idx + 1 >= state.questions.length
                ? (T.btn_see_results || "See results")
                : (T.btn_next_question || "Next question →");
            nextBtn.style.marginTop = "16px";
            nextBtn.addEventListener("click", () => {
                if (state.idx + 1 >= state.questions.length) {
                    showSummary();
                } else {
                    state.idx++;
                    showCurrent();
                }
            });
            els.area.appendChild(nextBtn);
            nextBtn.focus();
        }

        function showSummary() {
            els.area.classList.add("hidden");
            els.result.classList.remove("hidden");
            const total = state.score.correct + state.score.wrong;
            const pct = total ? Math.round((state.score.correct / total) * 100) : 0;
            $("final-correct").textContent = state.score.correct;
            $("final-wrong").textContent = state.score.wrong;
            $("final-pct").textContent = pct + "%";
            $("retry-btn").onclick = () => location.reload();
        }

        // Render immediately from the embedded data — no API call.
        if (!state.questions.length) {
            els.area.innerHTML = '<p class="muted">' + escapeHtml(T.no_questions || "No questions available.") + '</p>';
            return;
        }
        showCurrent();
        updateScore();
    }

    // expose
    window.N3App.initFlashcard = initFlashcard;
    window.N3App.initExercise = initExercise;
})();
