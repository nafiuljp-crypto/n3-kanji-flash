/* N3 kanji site — Dec 2025 Vocab Learn (243 words with logical breakdowns).
   Loads data/vocab_learn_2025_12.json and renders one card per word. Each
   card shows the word, its reading, the kanji parts (meaning + the exact
   reading each part contributes), the reading composition, and one factual
   meaning-logic line. No story mnemonics. */
(function (root, factory) {
  if (typeof module !== 'undefined' && module.exports) {
    module.exports = factory();
  } else {
    root.N3VocabLearn = factory();
  }
})(typeof window !== 'undefined' ? window : globalThis, function () {
  'use strict';

  var DATA_URL = 'data/vocab_learn_2025_12.json';
  var RANGE_KEY = 'n3vocab:learn-range:v1';
  var HIDE_KEY = 'n3vocab:learn-hide:v1';

  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }

  function typeLabel(p) {
    return p.used_type === 'onyomi' ? "on'yomi" : 'kun’yomi';
  }

  /* Plain-text reading composition, e.g.
     せい (西, on'yomi) + よう (洋, on'yomi) = せいよう */
  function readingComposition(entry) {
    if (!entry || !entry.parts) return '';
    if (entry.reading_pattern === 'whole') {
      return 'Reading: ' + entry.reading + ' (fixed set reading — see note)';
    }
    if (!entry.parts.some(function (p) { return p.type === 'kanji'; })) {
      return 'Kana only — read exactly as written';
    }
    var chunks = entry.parts.map(function (p) {
      if (p.type === 'kana') return p.text + ' (kana)';
      if (!p.used_reading) return p.char + ' (whole-word reading)';
      return p.used_reading + ' (' + p.char + ', ' + typeLabel(p) + ')';
    });
    return chunks.join(' + ') + ' = ' + entry.reading;
  }

  function partChip(p) {
    if (p.type === 'kana') {
      return '<div class="vl-part is-kana" role="listitem">' +
        '<span class="vl-part-text jp" lang="ja">' + esc(p.text) + '</span>' +
        '<span class="vl-part-tag">kana</span>' +
        '</div>';
    }
    var used = p.used_reading
      ? '<span class="vl-part-used jp" lang="ja">' + esc(p.used_reading) + '</span>'
      : '';
    var type = p.used_type
      ? '<span class="vl-part-type">' + esc(typeLabel(p)) + '</span>'
      : '<span class="vl-part-type">whole word</span>';
    var note = p.note
      ? '<span class="vl-readnote">' + esc(p.note) + '</span>'
      : '';
    return '<div class="vl-part" role="listitem">' +
      '<span class="vl-part-char jp" lang="ja">' + esc(p.char) + '</span>' +
      '<span class="vl-part-meaning">' + esc(p.meaning) + '</span>' +
      used + type + note +
      '</div>';
  }

  function cardHTML(entry, index) {
    var kanaClass = entry.kana_class
      ? '<span class="vl-kana-class">' + esc(entry.kana_class) + '</span>'
      : '';
    var readNote = entry.reading_note
      ? '<p class="vl-readnote vl-reading-note">' + esc(entry.reading_note) + '</p>'
      : '';
    return '<article class="vl-card" data-i="' + index + '" tabindex="0" ' +
      'aria-label="' + esc('Word ' + index + ': ' + entry.word) + '">' +
      '<header class="vl-card-head">' +
        '<span class="vl-num" aria-hidden="true">' + index + '</span>' +
        '<div class="vl-word-wrap">' +
          '<span class="vl-reading jp" lang="ja">' + esc(entry.reading) + '</span>' +
          '<span class="vl-word jp" lang="ja">' + esc(entry.word) + '</span>' +
          kanaClass +
        '</div>' +
        '<p class="vl-meaning">' + esc(entry.meaning) + '</p>' +
        '<button type="button" class="vl-reveal" data-act="reveal">Reveal</button>' +
      '</header>' +
      '<div class="vl-parts" role="list" aria-label="Kanji parts">' +
        entry.parts.map(partChip).join('') +
      '</div>' +
      '<p class="vl-compose">' + esc(readingComposition(entry)) + '</p>' +
      readNote +
      '<p class="vl-logic"><span class="vl-logic-label">Logic</span> ' +
        esc(entry.meaning_logic) + '</p>' +
      '</article>';
  }

  function loadWords(url) {
    return fetch(url, { cache: 'no-store' }).then(function (r) {
      if (!r.ok) throw new Error(url + ': HTTP ' + r.status);
      return r.json();
    }).then(function (doc) {
      var list = Array.isArray(doc) ? doc : (doc && doc.words ? doc.words : []);
      if (!list.length) throw new Error('No vocabulary entries in ' + url);
      return list;
    });
  }

  function clamp(n, lo, hi) {
    n = parseInt(n, 10);
    if (isNaN(n)) return lo;
    return Math.max(lo, Math.min(hi, n));
  }

  function readRange(total) {
    var saved = null;
    try { saved = JSON.parse(localStorage.getItem(RANGE_KEY) || 'null'); } catch (e) {}
    var from = 1, to = total;
    if (saved && saved.from >= 1 && saved.to <= total && saved.from <= saved.to) {
      from = saved.from; to = saved.to;
    }
    try {
      var q = new URLSearchParams(root.location ? root.location.search : '');
      var qf = parseInt(q.get('from'), 10);
      var qt = parseInt(q.get('to'), 10);
      if (!isNaN(qf)) from = clamp(qf, 1, total);
      if (!isNaN(qt)) to = clamp(qt, 1, total);
      if (from > to) to = from;
    } catch (e) {}
    return { from: from, to: to };
  }

  function readHides() {
    try {
      var v = JSON.parse(localStorage.getItem(HIDE_KEY) || 'null');
      if (v && typeof v === 'object') {
        return { readings: !!v.readings, meanings: !!v.meanings };
      }
    } catch (e) {}
    return { readings: false, meanings: false };
  }

  function saveHides() {
    try {
      localStorage.setItem(HIDE_KEY, JSON.stringify({
        readings: state.hideReadings, meanings: state.hideMeanings
      }));
    } catch (e) {}
  }

  var state = {
    total: 0,
    from: 1,
    to: 0,
    hideReadings: false,
    hideMeanings: false
  };

  function rangeText() {
    var shown = state.to - state.from + 1;
    return 'Showing ' + state.from + '–' + state.to + ' of ' + state.total +
      ' (' + shown + ' card' + (shown === 1 ? '' : 's') + ')';
  }

  function applyRange(container) {
    var cards = container.querySelectorAll('.vl-card');
    for (var i = 0; i < cards.length; i++) {
      var n = parseInt(cards[i].getAttribute('data-i'), 10);
      cards[i].hidden = n < state.from || n > state.to;
    }
    var count = container.querySelector('.vl-count');
    if (count) count.textContent = rangeText();
    var fromInput = container.querySelector('#vl-from');
    var toInput = container.querySelector('#vl-to');
    if (fromInput) fromInput.value = state.from;
    if (toInput) toInput.value = state.to;
  }

  function applyHides(container) {
    container.classList.toggle('hide-readings', state.hideReadings);
    container.classList.toggle('hide-meanings', state.hideMeanings);
    var r = container.querySelector('[data-toggle="readings"]');
    var m = container.querySelector('[data-toggle="meanings"]');
    if (r) {
      r.setAttribute('aria-pressed', state.hideReadings ? 'true' : 'false');
      r.classList.toggle('is-active', state.hideReadings);
    }
    if (m) {
      m.setAttribute('aria-pressed', state.hideMeanings ? 'true' : 'false');
      m.classList.toggle('is-active', state.hideMeanings);
    }
    var cards = container.querySelectorAll('.vl-card.revealed');
    for (var i = 0; i < cards.length; i++) {
      cards[i].classList.remove('revealed');
      var b = cards[i].querySelector('.vl-reveal');
      if (b) b.textContent = 'Reveal';
    }
  }

  function toggleReveal(card) {
    if (!state.hideReadings && !state.hideMeanings) return;
    var on = card.classList.toggle('revealed');
    var b = card.querySelector('.vl-reveal');
    if (b) b.textContent = on ? 'Hide' : 'Reveal';
  }

  function mount(container, options) {
    if (!container) return;
    options = options || {};
    var dataUrl = options.dataUrl || DATA_URL;

    loadWords(dataUrl).then(function (words) {
      state.total = words.length;
      var r = readRange(state.total);
      state.from = r.from;
      state.to = r.to;
      var h = readHides();
      state.hideReadings = h.readings;
      state.hideMeanings = h.meanings;

      container.innerHTML =
        '<div class="vl-toolbar">' +
          '<div class="vl-range" role="group" aria-label="Word range">' +
            '<label for="vl-from">From</label>' +
            '<input type="number" id="vl-from" inputmode="numeric" min="1" max="' +
              state.total + '" value="' + state.from + '">' +
            '<label for="vl-to">To</label>' +
            '<input type="number" id="vl-to" inputmode="numeric" min="1" max="' +
              state.total + '" value="' + state.to + '">' +
            '<span class="vl-range-of">of ' + state.total + '</span>' +
            '<button type="button" class="vl-btn" data-act="all">Show all</button>' +
          '</div>' +
          '<div class="vl-toggles" role="group" aria-label="Self-check">' +
            '<button type="button" class="vl-btn vl-toggle" data-toggle="readings" ' +
              'aria-pressed="' + (state.hideReadings ? 'true' : 'false') + '">Hide readings</button>' +
            '<button type="button" class="vl-btn vl-toggle" data-toggle="meanings" ' +
              'aria-pressed="' + (state.hideMeanings ? 'true' : 'false') + '">Hide meanings</button>' +
          '</div>' +
        '</div>' +
        '<p class="vl-count" aria-live="polite">' + rangeText() + '</p>' +
        '<div class="vl-list">' +
          words.map(function (w, i) { return cardHTML(w, i + 1); }).join('') +
        '</div>';

      applyRange(container);
      applyHides(container);

      container.addEventListener('click', function (e) {
        var t = e.target;
        if (!t || !t.closest) return;

        var toggle = t.closest('[data-toggle]');
        if (toggle) {
          var which = toggle.getAttribute('data-toggle');
          if (which === 'readings') state.hideReadings = !state.hideReadings;
          if (which === 'meanings') state.hideMeanings = !state.hideMeanings;
          saveHides();
          applyHides(container);
          return;
        }

        var act = t.closest('[data-act]');
        if (act) {
          if (act.getAttribute('data-act') === 'all') {
            state.from = 1;
            state.to = state.total;
            try {
              localStorage.setItem(RANGE_KEY, JSON.stringify({ from: 1, to: state.total }));
            } catch (err) {}
            applyRange(container);
          } else if (act.getAttribute('data-act') === 'reveal') {
            var card = act.closest('.vl-card');
            if (card) toggleReveal(card);
          }
          return;
        }

        if (t.closest('a, input, button')) return;
        var cardEl = t.closest('.vl-card');
        if (cardEl) toggleReveal(cardEl);
      });

      container.addEventListener('keydown', function (e) {
        if (e.key !== 'Enter' && e.key !== ' ') return;
        var card = e.target && e.target.classList &&
          e.target.classList.contains('vl-card') ? e.target : null;
        if (!card) return;
        e.preventDefault();
        toggleReveal(card);
      });

      function onRangeChange() {
        var fromInput = container.querySelector('#vl-from');
        var toInput = container.querySelector('#vl-to');
        var f = clamp(fromInput.value, 1, state.total);
        var to = clamp(toInput.value, 1, state.total);
        if (f > to) to = f;
        state.from = f;
        state.to = to;
        try {
          localStorage.setItem(RANGE_KEY, JSON.stringify({ from: f, to: to }));
        } catch (err) {}
        applyRange(container);
      }
      container.addEventListener('change', function (e) {
        if (e.target && (e.target.id === 'vl-from' || e.target.id === 'vl-to')) {
          onRangeChange();
        }
      });
      container.addEventListener('input', function (e) {
        if (e.target && (e.target.id === 'vl-from' || e.target.id === 'vl-to')) {
          onRangeChange();
        }
      });
    }).catch(function (err) {
      container.innerHTML = '<p class="vl-error">Could not load the vocabulary ' +
        'breakdowns: ' + esc(err.message) + '</p>';
    });
  }

  return {
    DATA_URL: DATA_URL,
    RANGE_KEY: RANGE_KEY,
    HIDE_KEY: HIDE_KEY,
    esc: esc,
    readingComposition: readingComposition,
    cardHTML: cardHTML,
    mount: mount
  };
});
