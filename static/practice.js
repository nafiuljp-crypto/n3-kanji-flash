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
  /* Word range for the session (1-based, inclusive, data-file order).
     Stored as {"from":51,"to":100}; absent / unreadable / invalid means the
     full 243-word list. */
  var RANGE_KEY = 'n3practice-range:v1';

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

  /* ---------- word range ---------- */

  /* Returns the stored {from, to} (unvalidated against the word count, which
     is unknown here) or null. Anything unreadable or non-numeric means "no
     range": the caller falls back to the full list. */
  function readRange(storage) {
    try {
      var raw = storage && storage.getItem(RANGE_KEY);
      if (!raw) return null;
      var obj = JSON.parse(raw);
      if (!obj || typeof obj !== 'object') return null;
      var from = Math.round(Number(obj.from));
      var to = Math.round(Number(obj.to));
      if (!isFinite(from) || !isFinite(to)) return null;
      return { from: from, to: to };
    } catch (e) {
      return null;
    }
  }

  /* null clears the stored range (the full list is the default, so nothing
     needs to be written for it). Storage failures leave the in-memory choice
     alone. */
  function writeRange(storage, range) {
    try {
      if (!storage) return;
      if (!range) {
        if (typeof storage.removeItem === 'function') storage.removeItem(RANGE_KEY);
        return;
      }
      storage.setItem(RANGE_KEY, JSON.stringify({ from: range.from, to: range.to }));
    } catch (e) { /* private mode / storage disabled */ }
  }

  /* Always produces a usable, non-empty range: numbers are rounded, clamped
     to 1..maxLen, and a reversed pair is swapped. */
  function clampRange(range, maxLen) {
    var max = Math.max(1, Math.round(Number(maxLen)) || 1);
    var from = Math.round(Number(range && range.from));
    var to = Math.round(Number(range && range.to));
    if (!isFinite(from)) from = 1;
    if (!isFinite(to)) to = max;
    from = Math.min(Math.max(from, 1), max);
    to = Math.min(Math.max(to, 1), max);
    if (from > to) {
      var t = from;
      from = to;
      to = t;
    }
    return { from: from, to: to };
  }

  function rangeCoversAll(range, maxLen) {
    return !range || (range.from <= 1 && range.to >= maxLen);
  }

  /* The words of the range in data-file order, or the whole list when there
     is no (or a full-list) range. */
  function rangeWords(allWords, range) {
    var list = Array.isArray(allWords) ? allWords : [];
    if (rangeCoversAll(range, list.length)) return list;
    var r = clampRange(range, list.length);
    return list.slice(r.from - 1, r.to);
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

  /* Number of questions a word list produces: every word is asked for its
     meaning, and a word whose reading differs from the word itself (i.e. one
     written with kanji) is also asked for that reading. A session size counts
     words, so its question count is this value, not the word count. */
  function questionCount(wordList) {
    var list = Array.isArray(wordList) ? wordList : [];
    var n = 0;
    list.forEach(function (w) { n += canAskReading(w) ? 2 : 1; });
    return n;
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
   * Build a session from `count` WORDS (10 / 20 / 50 / 243).
   *
   * Every chosen word is tested twice: word -> meaning and word -> reading,
   * so a session of 10 kanji words is 20 questions. Kana-only words (whose
   * reading is the word itself) are tested once, for meaning only — a
   * reading question for them would be meaningless. Option generation is the
   * unchanged buildQuestion().
   *
   * `order` (optional, default "shuffle"):
   *  - "ordered": the first `count` words of the pool in its existing order
   *    (for subset sessions that is the order the subset was given in); each
   *    word's meaning question is immediately followed by its reading one.
   *  - "shuffle": a random sample of the pool, as always; the resulting
   *    question list is then shuffled as a whole, so a word's two questions
   *    are not necessarily adjacent. Both steps use the supplied rng, so a
   *    seeded run is deterministic.
   */
  function buildSession(allWords, count, rng, subsetWords, order) {
    rng = rng || Math.random;
    var sourcePool = Array.isArray(subsetWords) && subsetWords.length ? subsetWords : allWords;
    var n = (count === 'all' || !count || Number(count) >= sourcePool.length)
      ? sourcePool.length
      : Math.max(1, Math.min(Number(count), sourcePool.length));

    var ordered = order === 'ordered';
    var chosen = ordered
      ? sourcePool.slice(0, n)
      : shuffle(sourcePool, rng).slice(0, n);

    var questions = [];
    chosen.forEach(function (w) {
      questions.push(buildQuestion(w, allWords, 'meaning', rng));
      if (canAskReading(w)) questions.push(buildQuestion(w, allWords, 'reading', rng));
    });

    if (!ordered) questions = shuffle(questions, rng);

    questions.forEach(function (q, idx) {
      q.n = idx + 1;
      q.total = questions.length;
    });
    return questions;
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
    var rangeStorage = null;
    try {
      orderStorage = window.localStorage;
      rangeStorage = window.localStorage;
    } catch (e) { /* storage disabled */ }

    var ui = {
      words: [],
      selectedCount: 10,
      order: readOrder(orderStorage),
      range: null,          /* {from, to} while a word range is active */
      questions: [],
      sessionWords: 0,      /* words in the current session (size counts words) */
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
      var saved = readRange(rangeStorage);
      if (saved) {
        saved = clampRange(saved, words.length);
        ui.range = rangeCoversAll(saved, words.length) ? null : saved;
      }
      startSession(10, null);
    }).catch(function (err) {
      container.innerHTML =
        '<section class="practice-setup"><p class="practice-error">Could not load ' +
        'vocabulary data: ' + esc(err.message) + '</p></section>';
    });

    /* The active word range as a word list, or null for the full list.
       Distractors still come from every word: buildSession receives
       ui.words as allWords and this range as the session pool. */
    function rangePool() {
      return ui.range ? rangeWords(ui.words, ui.range) : null;
    }

    function rangeSize() {
      return ui.range ? (ui.range.to - ui.range.from + 1) : ui.words.length;
    }

    function setRange(range) {
      ui.range = range;
      writeRange(rangeStorage, range);
      /* Restart so what is on screen matches the controls, as with order. */
      startSession(ui.selectedCount, null);
    }

    /* Read the From / To fields (on change, so typing does not restart the
       session mid-edit). Empty or non-numeric input means the full list;
       otherwise the pair is clamped/swapped into a valid non-empty range. */
    function applyRangeInputs() {
      var fromEl = container.querySelector('[data-range-input="from"]');
      var toEl = container.querySelector('[data-range-input="to"]');
      if (!fromEl || !toEl) return;
      var rawFrom = String(fromEl.value).trim();
      var rawTo = String(toEl.value).trim();
      var from = Number(rawFrom);
      var to = Number(rawTo);
      if (!rawFrom || !rawTo || !isFinite(from) || !isFinite(to)) {
        setRange(null);
        return;
      }
      var clamped = clampRange({ from: from, to: to }, ui.words.length);
      setRange(rangeCoversAll(clamped, ui.words.length) ? null : clamped);
    }

    function startSession(count, subset) {
      ui.subset = subset || null;
      if (!subset) ui.selectedCount = count;
      /* A retry-missed subset ignores the range, as it always has. */
      ui.questions = buildSession(ui.words, count, Math.random,
        subset || rangePool(), ui.order);
      /* Each word contributes exactly one meaning question, so counting those
         gives the session's word count however many readings it added. */
      ui.sessionWords = ui.questions.filter(function (q) {
        return q.type === 'meaning';
      }).length;
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
      return c === 243 ? 'All ' + rangeSize() : String(c);
    }

    function setupHTML() {
      var buttons = COUNTS.map(function (c) {
        var active = !ui.subset && ui.selectedCount === c;
        return '<button type="button" class="btn small count-btn' + (active ? ' is-active' : '') +
          '" data-count="' + c + '" aria-pressed="' + active + '">' + esc(sizeLabel(c)) + '</button>';
      }).join('');

      var allWords = ui.words.length;
      var rangeFrom = ui.range ? ui.range.from : 1;
      var rangeTo = ui.range ? ui.range.to : allWords;
      var rangeHTML =
        '<div class="ps-group ps-range" role="group" aria-label="Word range">' +
          '<label class="ps-range-label" for="ps-range-from">From</label>' +
          '<input type="number" id="ps-range-from" class="ps-range-input" data-range-input="from"' +
            ' min="1" max="' + allWords + '" step="1" inputmode="numeric"' +
            ' value="' + rangeFrom + '" aria-label="First word of the range">' +
          '<label class="ps-range-label" for="ps-range-to">To</label>' +
          '<input type="number" id="ps-range-to" class="ps-range-input" data-range-input="to"' +
            ' min="1" max="' + allWords + '" step="1" inputmode="numeric"' +
            ' value="' + rangeTo + '" aria-label="Last word of the range">' +
          '<button type="button" class="btn small ghost range-reset-btn' +
            (ui.range ? '' : ' is-active') + '" data-act="range-reset"' +
            ' aria-pressed="' + (ui.range ? 'false' : 'true') + '"' +
            ' title="Practice all ' + allWords + ' words">All words</button>' +
        '</div>';

      var rangeBadge = ui.range
        ? '<span class="ps-range-badge">Words ' + ui.range.from + '–' + ui.range.to +
          ' of ' + allWords + '</span>'
        : '';

      var orderButtons = [
        { value: 'shuffle', label: 'Shuffle' },
        { value: 'ordered', label: 'In order' }
      ].map(function (o) {
        var active = ui.order === o.value;
        return '<button type="button" class="btn small order-btn' + (active ? ' is-active' : '') +
          '" data-order="' + o.value + '" aria-pressed="' + active + '">' + o.label + '</button>';
      }).join('');

      /* Honest counts: the size buttons count words, so the subtitle spells
         out how many questions that produced (kana-only words add no reading
         question). Derived from the live session, never a hardcoded 2x. */
      var ordered = ui.order === 'ordered';
      var wordsN = ui.sessionWords;
      var questionsN = ui.questions.length;
      var perWord = questionsN === wordsN * 2
        ? 'meaning + reading for each word'
        : (questionsN === wordsN
          ? 'meaning for each word'
          : 'meaning for every word, reading where the word has kana');
      var subText = wordsN + (wordsN === 1 ? ' word' : ' words') + ' · ' +
        questionsN + (questionsN === 1 ? ' question' : ' questions') +
        ' (' + (ordered ? 'in list order' : 'shuffled') + ' · ' + perWord +
        ' · no timer)';
      var restartLabel = ordered ? 'Restart ↻' : 'Shuffle ↻';
      var restartTitle = ordered ? 'Restart this ordered session' : 'Start a newly shuffled session';

      return '' +
        '<section class="practice-setup" aria-label="Session setup">' +
          '<div class="ps-copy">' +
            '<span class="ps-title">Session setup</span>' +
            '<span class="ps-sub">' + subText + '</span>' +
            rangeBadge +
          '</div>' +
          '<div class="ps-controls">' +
            rangeHTML +
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
              '<span class="q-no" aria-label="Question ' + q.n + ' of ' + q.total + '">' +
                q.n + ' / ' + q.total + '</span>' +
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
                esc(ui.selectedCount === 243 ? 'All ' + rangeSize() + ' words'
                  : ui.selectedCount + (ui.selectedCount === 1 ? ' word' : ' words')) + ')</button>' +
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
      } else if (act === 'range-reset') {
        setRange(null);
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

    /* Range inputs commit on change (blur / Enter), never per keystroke. */
    container.addEventListener('change', function (e) {
      var t = e.target;
      if (!t || !t.closest || !t.closest('[data-range-input]')) return;
      applyRangeInputs();
    });
  }

  return {
    DATA_URL: DATA_URL,
    COUNTS: COUNTS,
    ORDER_KEY: ORDER_KEY,
    RANGE_KEY: RANGE_KEY,
    readOrder: readOrder,
    writeOrder: writeOrder,
    readRange: readRange,
    writeRange: writeRange,
    clampRange: clampRange,
    rangeCoversAll: rangeCoversAll,
    rangeWords: rangeWords,
    shuffle: shuffle,
    glossParts: glossParts,
    canAskReading: canAskReading,
    questionCount: questionCount,
    buildQuestion: buildQuestion,
    buildSession: buildSession,
    gradeAnswer: gradeAnswer,
    mountPractice: mountPractice
  };
});
