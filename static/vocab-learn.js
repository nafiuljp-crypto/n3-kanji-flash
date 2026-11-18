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
  var LOGIC_URL = 'data/kanji_logic.json';
  var RANGE_KEY = 'n3vocab:learn-range:v1';
  var HIDE_KEY = 'n3vocab:learn-hide:v1';
  var ROLE_LABEL = {
    sound: '音 sound',
    meaning: '意 meaning',
    both: '音+意 both',
    part: '部 part'
  };
  var TYPE_EN = {
    'phono-semantic': 'phono-semantic',
    compound: 'compound ideograph',
    pictograph: 'pictograph',
    ideograph: 'ideograph',
    opaque: 'no kanji structure'
  };

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

  function partChip(p, cardIndex, partIndex) {
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
    var panelId = 'vl-logic-' + cardIndex + '-' + partIndex;
    return '<div class="vl-part vl-part-logic" role="listitem">' +
      '<button type="button" class="vl-part-btn" data-logic="' + esc(p.char) + '" ' +
        'aria-expanded="false" aria-controls="' + panelId + '" ' +
        'aria-label="' + esc('Why ' + p.char + ': ' + p.meaning) + '">' +
        '<span class="vl-part-char jp" lang="ja">' + esc(p.char) + '</span>' +
        '<span class="vl-part-meaning">' + esc(p.meaning) + '</span>' +
        used + type + note +
        '<span class="vl-why">why <span class="vl-caret" aria-hidden="true">▾</span></span>' +
      '</button>' +
      '</div>';
  }

  function logicPanelHTML(ch, e) {
    if (!e) {
      return '<p class="vl-logic-empty">No structural entry for ' + esc(ch) + '.</p>';
    }
    var comps = (e.components || []).map(function (c) {
      var role = c.role || 'part';
      return '<span class="vl-lcomp vl-lcomp-' + esc(role) + '">' +
        '<span class="vl-lcomp-label jp" lang="ja">' + esc(c.label) + '</span>' +
        '<span class="vl-lcomp-meaning">' + esc(c.meaning) + '</span>' +
        '<span class="vl-role vl-role-' + esc(role) + '">' +
          esc(ROLE_LABEL[role] || role) + '</span>' +
        (c.note ? '<span class="vl-lcomp-note">' + esc(c.note) + '</span>' : '') +
        '</span>';
    }).join('');
    var exact = [], near = [];
    if (e.sound && e.sound.same) {
      e.sound.same.forEach(function (s) {
        var w = s.words && s.words[0]
          ? s.words[0].word + ' (' + s.words[0].reading + ')' : '';
        var item = s.kanji + ' (' + s.reading + ')' + (w ? ' — ' + w : '');
        (s.exact ? exact : near).push(item);
      });
    }
    var sound = '';
    if (e.sound) {
      sound = '<p class="vl-sound"><span class="vl-logic-tag">Sound pattern</span> ' +
        esc(e.sound.label) + ' (' + esc(e.sound.reading) + ')' +
        (exact.length ? ' · same component: ' + esc(exact.join('; ')) : '') +
        (near.length ? ' · near: ' + esc(near.join('; ')) : '') +
        '</p>';
    }
    return '<div class="vl-logic-head">' +
        '<span class="vl-logic-kanji jp" lang="ja">' + esc(ch) + '</span>' +
        '<span class="vl-logic-kind">' + esc(e.kind || '') + '</span>' +
        '<span class="vl-logic-word">' + esc(e.meaning || '') + '</span>' +
      '</div>' +
      '<div class="vl-lcomps">' + comps + '</div>' +
      '<p class="vl-logic-line"><span class="vl-logic-tag">Meaning</span> ' +
        esc(e.meaning_line) + '</p>' +
      '<p class="vl-logic-line"><span class="vl-logic-tag">Reading</span> ' +
        esc(e.reading_line) + '</p>' +
      sound;
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
        entry.parts.map(function (p, pi) { return partChip(p, index, pi); }).join('') +
        entry.parts.map(function (p, pi) {
          if (p.type !== 'kanji' || !p.char) return '';
          return '<div class="vl-logic-panel" id="vl-logic-' + index + '-' + pi +
            '" data-for="' + esc(p.char) + '" hidden></div>';
        }).join('') +
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

  function loadLogic(url) {
    return fetch(url).then(function (r) {
      if (!r.ok) throw new Error(url + ': HTTP ' + r.status);
      return r.json();
    }).then(function (doc) {
      return doc && typeof doc === 'object' && !Array.isArray(doc) ? doc : {};
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
    hideMeanings: false,
    logic: {}
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
    var open = container.querySelectorAll('.vl-logic-panel:not([hidden])');
    for (var j = 0; j < open.length; j++) {
      var openCard = open[j].closest('.vl-card');
      if (openCard) closeLogicPanels(openCard);
    }
  }

  function closeLogicPanels(card) {
    var panels = card.querySelectorAll('.vl-logic-panel');
    for (var i = 0; i < panels.length; i++) {
      if (panels[i].hidden) continue;
      panels[i].hidden = true;
      var btn = card.querySelector('[aria-controls="' + panels[i].id + '"]');
      if (btn) {
        btn.setAttribute('aria-expanded', 'false');
        var chip = btn.closest('.vl-part-logic');
        if (chip) chip.classList.remove('is-open');
      }
    }
  }

  function toggleLogic(card, btn) {
    var panelId = btn.getAttribute('aria-controls');
    var panel = panelId ? card.querySelector('[id="' + panelId + '"]') : null;
    if (!panel) return;
    var wasOpen = !panel.hidden;
    closeLogicPanels(card);
    if (wasOpen) return;
    var ch = btn.getAttribute('data-logic');
    panel.innerHTML = logicPanelHTML(ch, state.logic[ch]);
    panel.hidden = false;
    btn.setAttribute('aria-expanded', 'true');
    var chip = btn.closest('.vl-part-logic');
    if (chip) chip.classList.add('is-open');
  }

  function setRevealed(card, on) {
    card.classList.toggle('revealed', on);
    var b = card.querySelector('.vl-reveal');
    if (b) b.textContent = on ? 'Hide' : 'Reveal';
    if (!on) closeLogicPanels(card);
  }

  function toggleReveal(card) {
    if (!state.hideReadings && !state.hideMeanings) return;
    setRevealed(card, !card.classList.contains('revealed'));
  }

  function mount(container, options) {
    if (!container) return;
    options = options || {};
    var dataUrl = options.dataUrl || DATA_URL;
    var logicUrl = options.logicUrl || LOGIC_URL;

    Promise.all([
      loadWords(dataUrl),
      loadLogic(logicUrl).catch(function (err) {
        if (root.console && root.console.warn) {
          root.console.warn('kanji logic unavailable:', err);
        }
        return {};
      })
    ]).then(function (res) {
      var words = res[0];
      state.logic = res[1] || {};
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

        var logicBtn = t.closest('[data-logic]');
        if (logicBtn) {
          var logicCard = logicBtn.closest('.vl-card');
          if (logicCard) {
            if ((state.hideReadings || state.hideMeanings) &&
                !logicCard.classList.contains('revealed')) {
              setRevealed(logicCard, true);
            }
            toggleLogic(logicCard, logicBtn);
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
    LOGIC_URL: LOGIC_URL,
    RANGE_KEY: RANGE_KEY,
    HIDE_KEY: HIDE_KEY,
    ROLE_LABEL: ROLE_LABEL,
    esc: esc,
    readingComposition: readingComposition,
    cardHTML: cardHTML,
    logicPanelHTML: logicPanelHTML,
    mount: mount
  };
});
