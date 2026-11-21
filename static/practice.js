/* N3 kanji site — Dec 2025 Vocab Practice (243 to-learn words).
   Vanilla JS, client-side only. Ported from the JLPT N3 past-paper site's
   practice.js; exports the generator and grading helpers so the headless
   harness can verify the question guarantees without touching the DOM. */
(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();
  } else {
    root.N3VocabPractice = factory();
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  var DATA_URL = 'data/vocab_practice_2025_12.json';
  var COUNTS = [10, 20, 50, 243];
  var ORDER_KEY = 'n3practice-order:v1';

  /* Question order is a per-browser preference, like n3mode:v1 / n3theme:v1.
     Anything other than the literal "ordered" means the default shuffle. */
  function readOrder(storage) {
    try {
      var v = storage && storage.getItem(ORDER_KEY);
      return v === 'ordered' ? 'ordered' : 'shuffle';
    } catch (e) {
      return 'shuffle';
    }
  }

  function writeOrder(storage, order) {
    try {
      if (storage) storage.setItem(ORDER_KEY, order === 'ordered' ? 'ordered' : 'shuffle');
    } catch (e) { /* private mode / storage disabled: keep the in-memory choice */ }
  }

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function shuffle(list, rng) {
    rng = rng || Math.random;
    var a = list.slice();
    for (var i = a.length - 1; i > 0; i--) {
      var j = Math.floor(rng() * (i + 1));
      var tmp = a[i];
      a[i] = a[j];
      a[j] = tmp;
    }
    return a;
  }

  /* A meaning is one or more glosses separated by ";" or ",". Matching is
     case-insensitive and trimmed so "to move homes" and "to move homes; ..."
     are recognised as the same gloss. */
  function glossParts(meaning) {
    return String(meaning || '')
      .split(/[;,]/)
      .map(function (s) { return s.trim().toLowerCase(); })
      .filter(Boolean);
  }

  function canAskReading(item) {
    return Boolean(item && item.word && item.reading && item.word !== item.reading);
  }

  function sharesGloss(aParts, bParts) {
    for (var i = 0; i < aParts.length; i++) {
      if (bParts.indexOf(aParts[i]) !== -1) return true;
    }
    return false;
  }

  /**
   * Build a 4-option multiple-choice question for `item`, drawing distractors
   * from `allWords` (the same 243-word set).
   *
   * Guarantees:
   *  - exactly 4 options
   *  - all 4 option texts are strictly distinct
   *  - exactly one option is a valid answer for `item`
   *  - meaning questions never use a distractor whose meaning shares the
   *    correct meaning's full gloss or any ";" / "," sub-gloss
   *  - reading questions never use a distractor with the correct reading
   */
  function buildQuestion(item, allWords, requestedType, rng) {
    rng = rng || Math.random;
    if (!item || !Array.isArray(allWords) || allWords.length < 4) {
      throw new Error('buildQuestion requires a target item and at least 4 words in pool');
    }

    var qType = (requestedType === 'reading' && canAskReading(item)) ? 'reading' : 'meaning';
    var correctText = qType === 'reading' ? item.reading : item.meaning;
    var usedTexts = Object.create(null);
    usedTexts[correctText] = true;

    var distractors = [];

    if (qType === 'meaning') {
      var correctParts = glossParts(correctText);
      var usedGloss = Object.create(null);
      correctParts.forEach(function (g) { usedGloss[g] = true; });

      var pool = shuffle(allWords, rng);
      // Pass 1: exclude any entry sharing the correct gloss or a gloss already
      // used by a chosen distractor. This keeps all four meanings distinct.
      for (var i = 0; i < pool.length && distractors.length < 3; i++) {
        var cand = pool[i];
        if (!cand || cand.word === item.word) continue;
        var text = cand.meaning;
        if (!text || usedTexts[text]) continue;
        var parts = glossParts(text);
        if (sharesGloss(parts, correctParts) || sharesGloss(parts, Object.keys(usedGloss))) continue;
        usedTexts[text] = true;
        parts.forEach(function (g) { usedGloss[g] = true; });
        distractors.push(text);
      }
      // Pass 2: only the correct-gloss exclusion is mandatory. If the pool
      // were ever tight, allow distractor-to-distractor overlap but still no
      // shared gloss with the correct meaning and no duplicate option text.
      for (var k = 0; k < pool.length && distractors.length < 3; k++) {
        var cand2 = pool[k];
        if (!cand2 || cand2.word === item.word) continue;
        var text2 = cand2.meaning;
        if (!text2 || usedTexts[text2]) continue;
        if (sharesGloss(glossParts(text2), correctParts)) continue;
        usedTexts[text2] = true;
        distractors.push(text2);
      }
    } else {
      // word -> reading: kana options from the kanji words in the same set.
      var kanjiPool = allWords.filter(canAskReading);
      var rPool = shuffle(kanjiPool.length >= 4 ? kanjiPool : allWords, rng);
      for (var r = 0; r < rPool.length && distractors.length < 3; r++) {
        var rCand = rPool[r];
        if (!rCand || rCand.word === item.word) continue;
        var rText = rCand.reading;
        if (!rText || usedTexts[rText]) continue;
        usedTexts[rText] = true;
        distractors.push(rText);
      }
    }

    if (distractors.length < 3) {
      throw new Error('Could not find 3 unique distractors for word: ' + item.word);
    }

    var options = shuffle([correctText, distractors[0], distractors[1], distractors[2]], rng);
    var answerIndex = options.indexOf(correctText);

    return {
      type: qType,
      typeLabel: qType === 'reading' ? 'Word → Reading' : 'Word → Meaning',
      typeJp: qType === 'reading' ? '読み' : '意味',
      prompt: item.word,
      word: item.word,
      reading: item.reading,
      meaning: item.meaning,
      questions: item.questions || [],
      options: options,
      answerIndex: answerIndex,
      answer: answerIndex + 1,
      answerText: correctText
    };
  }

  /**
   * Build a session of `count` questions (10 / 20 / 50 / 243) with mixed
   * word -> meaning and word -> reading questions.
   *
   * `order` (optional, default "shuffle"):
   *  - "shuffle": a random sample of the pool, as always.
   *  - "ordered": the first `count` words of the pool in its existing order
   *    (for subset sessions that is the order the subset was given in), so a
   *    session is deterministic and runs through the list. Question-type
   *    balancing and option shuffling are unchanged.
   */
  function buildSession(allWords, count, rng, subsetWords, order) {
    rng = rng || Math.random;
    var sourcePool = Array.isArray(subsetWords) && subsetWords.length ? subsetWords : allWords;
    var n = (count === 'all' || !count || Number(count) >= sourcePool.length)
      ? sourcePool.length
      : Math.max(1, Math.min(Number(count), sourcePool.length));

    var chosen = order === 'ordered'
      ? sourcePool.slice(0, n)
      : shuffle(sourcePool, rng).slice(0, n);

    // Balance the two question types across kanji-capable words.
    var kanjiIndices = [];
    chosen.forEach(function (w, idx) {
      if (canAskReading(w)) kanjiIndices.push(idx);
    });
    var shuffledKanjiIdx = shuffle(kanjiIndices, rng);
    var typeMap = Object.create(null);
    shuffledKanjiIdx.forEach(function (qIdx, i) {
      typeMap[qIdx] = (i % 2 === 0) ? 'meaning' : 'reading';
    });

    return chosen.map(function (w, idx) {
      var qType = canAskReading(w) ? (typeMap[idx] || 'meaning') : 'meaning';
      var q = buildQuestion(w, allWords, qType, rng);
      q.n = idx + 1;
      q.total = n;
      return q;
    });
  }

  /**
   * Grade a question against a 1-based selected option number (1..4).
   */
  function gradeAnswer(question, selectedOpt) {
    var optNum = Number(selectedOpt);
    var idx = optNum - 1;
    var chosenText = (idx >= 0 && idx < question.options.length) ? question.options[idx] : null;
    var isCorrect = (optNum === question.answer && chosenText === question.answerText);
    return {
      correct: isCorrect,
      selectedOpt: optNum,
      selectedText: chosenText,
      correctOpt: question.answer,
      correctText: question.answerText,
      word: question.word,
      reading: question.reading,
      meaning: question.meaning,
      type: question.type
    };
  }

  /* ---------- Browser UI ---------- */

  var wordsPromise = null;
  var wordsUrl = null;

  function loadWords(dataUrl) {
    dataUrl = dataUrl || DATA_URL;
    if (!wordsPromise || wordsUrl !== dataUrl) {
      wordsUrl = dataUrl;
      wordsPromise = fetch(dataUrl, { cache: 'no-store' }).then(function (r) {
        if (!r.ok) throw new Error(dataUrl + ': HTTP ' + r.status);
        return r.json();
      }).then(function (doc) {
        var list = Array.isArray(doc) ? doc : (doc && doc.words ? doc.words : []);
        if (!list.length) throw new Error('No vocabulary words found in ' + dataUrl);
        return list;
      });
    }
    return wordsPromise;
  }

  function mountPractice(container, options) {
    if (!container) return;
    options = options || {};
    var backHref = options.backHref || './';
    var dataUrl = options.dataUrl || DATA_URL;

    var orderStorage = null;
    try { orderStorage = window.localStorage; } catch (e) { /* storage disabled */ }

    var ui = {
      words: [],
      selectedCount: 10,
      order: readOrder(orderStorage),
      questions: [],
      index: 0,
      answered: 0,
      correct: 0,
      missed: [],
      result: null,
      finished: false,
      subset: null
    };

    container.innerHTML = '<p class="loading">Loading Dec 2025 vocabulary practice…</p>';

    loadWords(dataUrl).then(function (words) {
      ui.words = words;
      startSession(10, null);
    }).catch(function (err) {
      container.innerHTML =
        '<section class="practice-setup"><p class="practice-error">Could not load ' +
        'vocabulary data: ' + esc(err.message) + '</p></section>';
    });

    function startSession(count, subset) {
      ui.subset = subset || null;
      if (!subset) ui.selectedCount = count;
      ui.questions = buildSession(ui.words, count, Math.random, subset, ui.order);
      ui.index = 0;
      ui.answered = 0;
      ui.correct = 0;
      ui.missed = [];
      ui.result = null;
      ui.finished = false;
      render();
    }

    function selectOpt(optNum) {
      if (ui.finished || ui.result) return;
      var q = ui.questions[ui.index];
      if (!q) return;
      var res = gradeAnswer(q, optNum);
      ui.result = res;
      ui.answered++;
      if (res.correct) {
        ui.correct++;
      } else if (!ui.missed.some(function (m) { return m.word === q.word; })) {
        ui.missed.push({
          word: q.word,
          reading: q.reading,
          meaning: q.meaning,
          type: q.typeLabel,
          chosenText: res.selectedText,
          correctText: res.correctText
        });
      }
      render();
    }

    function nextQuestion() {
      if (!ui.result) return;
      if (ui.index + 1 < ui.questions.length) {
        ui.index++;
        ui.result = null;
        render();
      } else {
        ui.finished = true;
        render();
      }
    }

    function finishEarly() {
      ui.finished = true;
      render();
    }

    function sizeLabel(c) {
      return c === 243 ? 'All ' + ui.words.length : String(c);
    }

    function setupHTML() {
      var buttons = COUNTS.map(function (c) {
        var active = !ui.subset && ui.selectedCount === c;
        return '<button type="button" class="btn small count-btn' + (active ? ' is-active' : '') +
          '" data-count="' + c + '" aria-pressed="' + active + '">' + esc(sizeLabel(c)) + '</button>';
      }).join('');

      var orderButtons = [
        { value: 'shuffle', label: 'Shuffle' },
        { value: 'ordered', label: 'In order' }
      ].map(function (o) {
        var active = ui.order === o.value;
        return '<button type="button" class="btn small order-btn' + (active ? ' is-active' : '') +
          '" data-order="' + o.value + '" aria-pressed="' + active + '">' + o.label + '</button>';
      }).join('');

      var ordered = ui.order === 'ordered';
      var subText = ordered
        ? 'Questions (in list order, mixed meaning &amp; reading · no timer)'
        : 'Questions (shuffled, mixed meaning &amp; reading · no timer)';
      var restartLabel = ordered ? 'Restart ↻' : 'Shuffle ↻';
      var restartTitle = ordered ? 'Restart this ordered session' : 'Start a newly shuffled session';

      return '' +
        '<section class="practice-setup" aria-label="Session setup">' +
          '<div class="ps-copy">' +
            '<span class="ps-title">Session setup</span>' +
            '<span class="ps-sub">' + subText + '</span>' +
          '</div>' +
          '<div class="ps-controls">' +
            '<div class="ps-group" role="group" aria-label="Number of questions">' + buttons + '</div>' +
            '<div class="ps-group ps-order" role="group" aria-label="Question order">' + orderButtons + '</div>' +
            '<button type="button" class="btn small ghost" data-act="reshuffle" title="' + restartTitle + '">' +
              restartLabel + '</button>' +
          '</div>' +
        '</section>';
    }

    function questionHTML() {
      var q = ui.questions[ui.index];
      var res = ui.result;
      var total = ui.questions.length;
      var pct = Math.round(((ui.index + (res ? 1 : 0)) / total) * 100);
      var hint = q.type === 'reading'
        ? 'Choose the correct kana reading · 正しい読み方を選んでください'
        : 'Choose the correct English meaning · 正しい英語の意味を選んでください';
      var isLast = (ui.index + 1 >= total);

      var optsHTML = q.options.map(function (optText, idx) {
        var optNum = idx + 1;
        var cls = 'practice-opt' + (q.type === 'reading' ? ' jp' : '');
        var disabled = '';
        if (res) {
          disabled = ' disabled';
          if (optNum === res.correctOpt) cls += ' is-answer';
          if (optNum === res.selectedOpt) {
            cls += ' selected';
            if (!res.correct) cls += ' is-wrong';
          }
        }
        return '' +
          '<button type="button" class="' + cls + '" data-opt="' + optNum + '"' + disabled + '>' +
            '<span class="opt-no" aria-hidden="true">' + optNum + '</span>' +
            '<span class="opt-text">' + esc(optText) + '</span>' +
          '</button>';
      }).join('');

      var feedbackHTML = '';
      if (res) {
        var verdict = res.correct
          ? 'Correct!'
          : 'Incorrect — correct answer: ' + res.correctOpt + '. ' + res.correctText;
        feedbackHTML = '' +
          '<div class="practice-feedback ' + (res.correct ? 'is-ok' : 'is-bad') + '" role="status" aria-live="polite">' +
            '<div class="pf-main">' +
              '<p class="pf-verdict">' + esc(verdict) + '</p>' +
              '<p class="pf-word"><strong class="jp">' + esc(q.word) + '</strong> ' +
                '<span class="pf-reading jp" lang="ja">（' + esc(q.reading) + '）</span> — ' +
                '<span class="pf-meaning">' + esc(q.meaning) + '</span></p>' +
            '</div>' +
            '<button type="button" class="btn btn-primary pf-next" data-act="next">' +
              (isLast ? 'See final score →' : 'Next question →') +
            '</button>' +
          '</div>';
      }

      return '' +
        '<article class="practice-card' + (res ? (' graded ' + (res.correct ? 'ok' : 'bad')) : '') + '">' +
          '<header class="practice-status">' +
            '<div class="ps-left">' +
              '<span class="q-no">' + q.n + ' / ' + q.total + '</span>' +
              '<span class="practice-type-badge">' + esc(q.typeLabel) +
                ' · <span class="jp">' + esc(q.typeJp) + '</span></span>' +
            '</div>' +
            '<div class="ps-right" aria-live="polite">' +
              '<span class="running-score">Score: <strong>' + ui.correct + ' / ' + ui.answered + '</strong></span>' +
              (ui.missed.length ? '<span class="missed-pill">' + ui.missed.length + ' missed</span>' : '') +
              (ui.answered > 0 && !res
                ? '<button type="button" class="btn small ghost" data-act="finish-early">End &amp; review</button>'
                : '') +
            '</div>' +
          '</header>' +
          '<div class="practice-progress" aria-hidden="true"><div class="practice-progress-bar" style="width:' + pct + '%"></div></div>' +
          '<div class="practice-body">' +
            '<p class="practice-direction">' + esc(hint) + '</p>' +
            '<div class="practice-prompt jp" lang="ja">' + esc(q.prompt) + '</div>' +
            '<div class="practice-opts" role="group" aria-label="Answer options">' + optsHTML + '</div>' +
            feedbackHTML +
          '</div>' +
        '</article>';
    }

    function endHTML() {
      var total = ui.answered;
      var score = ui.correct;
      var pct = total > 0 ? Math.round((score / total) * 100) : 0;
      var missed = ui.missed;

      var reviewHTML;
      if (!missed.length) {
        reviewHTML = '<div class="practice-empty-review"><p><strong>No missed words!</strong> ' +
          'Every answered question in this session was correct.</p></div>';
      } else {
        reviewHTML = '' +
          '<div class="missed-section">' +
            '<h3>Missed words for review (' + missed.length + ') <span class="jp">復習リスト</span></h3>' +
            '<div class="missed-list" role="list">' +
              missed.map(function (m) {
                return '' +
                  '<div class="missed-item" role="listitem">' +
                    '<div class="mi-word jp" lang="ja">' + esc(m.word) + '</div>' +
                    '<div class="mi-reading jp" lang="ja">' + esc(m.reading) + '</div>' +
                    '<div class="mi-meaning">' + esc(m.meaning) + '</div>' +
                    '<div class="mi-meta">Your answer: <span class="mi-wrong">' + esc(m.chosenText) +
                      '</span> · Correct: <span class="mi-ok">' + esc(m.correctText) + '</span></div>' +
                  '</div>';
              }).join('') +
            '</div>' +
          '</div>';
      }

      return '' +
        '<article class="practice-end" aria-live="polite">' +
          '<div class="pe-summary">' +
            '<p class="pe-eyebrow">Session complete · 練習完了</p>' +
            '<h2>Final Score: ' + score + ' / ' + total + ' <span class="pe-pct">(' + pct + '%)</span></h2>' +
            '<p class="pe-stats">' + score + ' correct · ' + missed.length +
              ' missed out of ' + total + ' answered</p>' +
            '<div class="pe-actions">' +
              '<button type="button" class="btn btn-primary" data-act="restart">Practice again (' +
                esc(ui.selectedCount === 243 ? 'All ' + ui.words.length : ui.selectedCount) + ')</button>' +
              (missed.length
                ? '<button type="button" class="btn btn-secondary" data-act="retry-missed">Retry ' +
                  missed.length + ' missed word' + (missed.length === 1 ? '' : 's') + '</button>'
                : '') +
            '</div>' +
          '</div>' +
          reviewHTML +
        '</article>';
    }

    function render() {
      container.innerHTML = setupHTML() +
        (ui.finished ? endHTML() : questionHTML());
    }

    container.addEventListener('click', function (e) {
      var t = e.target;
      if (!t || !t.closest) return;

      var countBtn = t.closest('[data-count]');
      if (countBtn) {
        var c = parseInt(countBtn.getAttribute('data-count'), 10);
        if (c) startSession(c, null);
        return;
      }

      var orderBtn = t.closest('[data-order]');
      if (orderBtn) {
        var nextOrder = orderBtn.getAttribute('data-order') === 'ordered' ? 'ordered' : 'shuffle';
        if (nextOrder !== ui.order) {
          ui.order = nextOrder;
          writeOrder(orderStorage, nextOrder);
          /* Restart so the questions on screen match the chosen order. */
          startSession(ui.selectedCount, null);
        }
        return;
      }

      var optBtn = t.closest('.practice-opt[data-opt]');
      if (optBtn && !optBtn.disabled) {
        selectOpt(parseInt(optBtn.getAttribute('data-opt'), 10));
        return;
      }

      var actBtn = t.closest('[data-act]');
      if (!actBtn) return;
      var act = actBtn.getAttribute('data-act');
      if (act === 'next') {
        nextQuestion();
      } else if (act === 'reshuffle' || act === 'restart') {
        startSession(ui.selectedCount, null);
      } else if (act === 'finish-early') {
        finishEarly();
      } else if (act === 'retry-missed' && ui.missed.length) {
        /* Keep the misses in the order they were made, not data-file order,
           so an in-order retry follows the session's own miss sequence. */
        var wordByWord = Object.create(null);
        ui.words.forEach(function (w) { wordByWord[w.word] = w; });
        var seen = Object.create(null);
        var sub = [];
        ui.missed.forEach(function (m) {
          var w = wordByWord[m.word];
          if (w && !seen[m.word]) {
            seen[m.word] = true;
            sub.push(w);
          }
        });
        startSession(sub.length, sub);
      }
    });
  }

  return {
    DATA_URL: DATA_URL,
    COUNTS: COUNTS,
    ORDER_KEY: ORDER_KEY,
    readOrder: readOrder,
    writeOrder: writeOrder,
    shuffle: shuffle,
    glossParts: glossParts,
    canAskReading: canAskReading,
    buildQuestion: buildQuestion,
    buildSession: buildSession,
    gradeAnswer: gradeAnswer,
    mountPractice: mountPractice
  };
});
