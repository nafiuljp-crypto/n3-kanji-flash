#!/usr/bin/env node
/* Logic checks for the Dec 2025 Vocab Practice generator (static/practice.js).
 *
 * There is no browser here: the module's UMD wrapper lets us require the
 * exact file the site ships, and buildSession/buildQuestion are pure. Covers
 * the question guarantees, the Shuffle / In-order toggle, the word range and
 * the rule that every word is tested for meaning AND reading (once each),
 * except kana-only words which get a meaning question only.
 *
 * Run: node tools/check_practice.js
 */
'use strict';

var fs = require('fs');
var path = require('path');
var os = require('os');
var childProcess = require('child_process');

var ROOT = path.resolve(__dirname, '..');
var PRACTICE = path.join(ROOT, 'static', 'practice.js');
var DATA = path.join(ROOT, 'data', 'vocab_practice_2025_12.json');

var checks = 0;
var failures = [];

function check(cond, msg) {
  checks++;
  if (!cond) failures.push(msg);
}

function eq(actual, expected, msg) {
  var a = JSON.stringify(actual);
  var e = JSON.stringify(expected);
  check(a === e, msg + ' (got ' + a + ', expected ' + e + ')');
}

/* Load a practice.js source file without require() caching, so the same
   process can compare the working tree against a git baseline. */
function loadModule(file) {
  var code = fs.readFileSync(file, 'utf8');
  var module = { exports: {} };
  var fn = new Function('module', 'exports', 'window', code);
  fn(module, module.exports, undefined);
  return module.exports;
}

function mulberry32(seed) {
  var a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) >>> 0;
    var t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

var P = loadModule(PRACTICE);
var words = JSON.parse(fs.readFileSync(DATA, 'utf8'));
var byWord = Object.create(null);
words.forEach(function (w) { byWord[w.word] = w; });

/* Independent restatement of the rule under test: a session size counts
   words; each word yields a meaning question and, when its reading differs
   from the word itself, a reading question too. */
function qCount(list) {
  var n = 0;
  list.forEach(function (w) { n += (w && w.word && w.reading && w.word !== w.reading) ? 2 : 1; });
  return n;
}

/* The expected ordered question sequence for a word list: per word, meaning
   then reading (reading only for kanji words). */
function expectedQuestions(list) {
  var out = [];
  list.forEach(function (w) {
    out.push({ word: w.word, type: 'meaning' });
    if (w.word !== w.reading) out.push({ word: w.word, type: 'reading' });
  });
  return out;
}

function signatures(list) {
  return list.map(function (x) { return x.word + '\u0000' + x.type; });
}

/* ---------- data sanity ---------- */
check(Array.isArray(words) && words.length === 243, 'data has 243 words');
var uniqueWords = {};
words.forEach(function (w) { uniqueWords[w.word] = true; });
check(Object.keys(uniqueWords).length === words.length, 'data words are unique');
check(words.every(function (w) { return w.word && w.reading && w.meaning; }),
  'every data word has word/reading/meaning');
var kanjiWords = words.filter(function (w) { return w.word !== w.reading; });
var kanaWords = words.filter(function (w) { return w.word === w.reading; });
check(kanjiWords.length === 206 && kanaWords.length === 37,
  'data has 206 kanji words and 37 kana-only words');

/* ---------- shared question validator ---------- */
function validateQuestion(q, item, allWords, label) {
  check(q && typeof q === 'object', label + ': question object');
  if (!q) return;
  check(q.prompt === item.word, label + ': prompt is the word');
  check(q.word === item.word, label + ': word echoed');
  check(q.options.length === 4, label + ': four options');
  var seen = {};
  q.options.forEach(function (o) { seen[o] = true; });
  check(Object.keys(seen).length === 4, label + ': four distinct option texts');
  check(q.answerIndex >= 0 && q.answerIndex < 4, label + ': answerIndex in range');
  check(q.options[q.answerIndex] === q.answerText, label + ': answerIndex points at answerText');
  check(q.answer === q.answerIndex + 1, label + ': 1-based answer number');
  check(q.type === 'meaning' || q.type === 'reading', label + ': known question type');
  if (q.type === 'reading') {
    check(item.word !== item.reading && q.answerText === item.reading,
      label + ': reading question answers the kana reading');
    check(q.options.filter(function (o) { return o === item.reading; }).length === 1,
      label + ': exactly one reading option is correct');
  } else {
    check(q.answerText === item.meaning, label + ': meaning question answers the gloss');
    var correctParts = P.glossParts(item.meaning);
    q.options.forEach(function (o) {
      if (o === item.meaning) return;
      check(!sharesGloss(P.glossParts(o), correctParts),
        label + ': meaning distractor shares no gloss with the answer');
    });
  }
}

function sharesGloss(a, b) {
  for (var i = 0; i < a.length; i++) if (b.indexOf(a[i]) !== -1) return true;
  return false;
}

/* Ordered sessions: exact question sequence, numbering and totals. */
function validateOrderedSession(session, expectedWordList, allWords, label) {
  var exp = expectedQuestions(expectedWordList);
  check(Array.isArray(session), label + ': session is an array');
  if (!Array.isArray(session)) return;
  check(session.length === exp.length,
    label + ': ' + exp.length + ' questions for ' + expectedWordList.length + ' words');
  eq(signatures(session), signatures(exp), label + ': word/type sequence');
  session.forEach(function (q, i) {
    check(q.n === i + 1, label + ': question ' + (i + 1) + ' numbering');
    check(q.total === exp.length, label + ': question ' + (i + 1) + ' total');
    validateQuestion(q, byWord[q.word], allWords, label + ' q' + (i + 1));
  });
}

/* Shuffled sessions: the same multiset of word/type questions as the ordered
   generation over the same word set, but in a different (seeded) order. */
function validateSessionCoverage(session, expectedWordList, allWords, label) {
  var exp = expectedQuestions(expectedWordList);
  check(Array.isArray(session), label + ': session is an array');
  if (!Array.isArray(session)) return;
  check(session.length === exp.length,
    label + ': ' + exp.length + ' questions for ' + expectedWordList.length + ' words');
  eq(signatures(session).sort(), signatures(exp).sort(),
    label + ': question multiset (one meaning + one reading per kanji word)');
  session.forEach(function (q, i) {
    check(q.n === i + 1, label + ': question ' + (i + 1) + ' numbering');
    check(q.total === exp.length, label + ': question ' + (i + 1) + ' total');
    validateQuestion(q, byWord[q.word], allWords, label + ' q' + (i + 1));
  });
}

/* ---------- the core rule: both types per word ---------- */
var tenKanji = kanjiWords.slice(0, 10);
var tenKanjiOrdered = P.buildSession(words, 'all', mulberry32(1), tenKanji, 'ordered');
check(tenKanjiOrdered.length === 20,
  '10 kanji words ordered = 20 questions (' + tenKanjiOrdered.length + ')');
var tenCounts = tenKanjiOrdered.reduce(function (m, q) {
  m[q.type] = (m[q.type] || 0) + 1;
  return m;
}, {});
eq(tenCounts, { meaning: 10, reading: 10 }, '10 kanji words = 10 meaning + 10 reading questions');
validateOrderedSession(tenKanjiOrdered, tenKanji, words, '10 kanji words ordered');

/* Same word set through the shuffle path: same 20-question multiset. */
var tenKanjiShuffled = P.buildSession(words, 'all', mulberry32(1), tenKanji, 'shuffle');
check(tenKanjiShuffled.length === 20, '10 kanji words shuffled = 20 questions');
validateSessionCoverage(tenKanjiShuffled, tenKanji, words, '10 kanji words shuffled');

/* Each word appears exactly twice, once per type. */
tenKanji.forEach(function (w) {
  var qs = tenKanjiOrdered.filter(function (q) { return q.word === w.word; });
  check(qs.length === 2, 'kanji word ' + w.word + ' asked exactly twice (' + qs.length + ')');
  eq(qs.map(function (q) { return q.type; }), ['meaning', 'reading'],
    'kanji word ' + w.word + ' asked meaning then reading in ordered mode');
});

/* ---------- kana-only words: meaning only ---------- */
var mixedPool = kanaWords.slice(0, 3).concat(kanjiWords.slice(0, 4));
var mixedOrdered = P.buildSession(words, 'all', mulberry32(2), mixedPool, 'ordered');
eq(mixedOrdered.length, 11, '3 kana + 4 kanji words = 11 questions (3 + 2*4)');
mixedPool.forEach(function (w) {
  var n = mixedOrdered.filter(function (q) { return q.word === w.word; }).length;
  eq(n, w.word === w.reading ? 1 : 2,
    (w.word === w.reading ? 'kana-only' : 'kanji') + ' word ' + w.word + ' question count');
});
validateOrderedSession(mixedOrdered, mixedPool, words, 'kana + kanji ordered');
validateSessionCoverage(
  P.buildSession(words, 'all', mulberry32(2), mixedPool, 'shuffle'),
  mixedPool, words, 'kana + kanji shuffled');

/* An all-kana pool yields one meaning question per word. */
var allKanaSession = P.buildSession(words, 'all', mulberry32(3), kanaWords.slice(0, 6), 'ordered');
check(allKanaSession.length === 6 && allKanaSession.every(function (q) { return q.type === 'meaning'; }),
  'an all-kana pool has exactly one meaning question per word');

/* ---------- exported questionCount helper ---------- */
[words, words.slice(0, 10), mixedPool, kanaWords, tenKanji].forEach(function (list, i) {
  eq(P.questionCount(list), qCount(list), 'exported questionCount matches the rule (list ' + i + ')');
});
check(typeof P.questionCount === 'function', 'questionCount is exported');

/* ---------- ordered mode ---------- */
[10, 20, 50].forEach(function (count) {
  var session = P.buildSession(words, count, mulberry32(count), null, 'ordered');
  validateOrderedSession(session, words.slice(0, count), words, 'ordered ' + count);
});

['all', 243, 999].forEach(function (count) {
  var session = P.buildSession(words, count, mulberry32(7), null, 'ordered');
  validateOrderedSession(session, words, words, 'ordered ' + count);
});

/* Ordered sessions ignore the RNG for word choice: same words, same order on
   every call, whatever the seed. */
[1, 2, 3, 99, 123456].forEach(function (seed) {
  var session = P.buildSession(words, 10, mulberry32(seed), null, 'ordered');
  eq(signatures(session), signatures(expectedQuestions(words.slice(0, 10))),
    'ordered 10 seed ' + seed + ': file order, meaning-then-reading pairs');
});

/* A subset (retry-missed) in ordered mode is taken in the order given. */
var subset = [words[7], words[2], words[42], words[0]];
var subSession = P.buildSession(words, 'all', mulberry32(5), subset, 'ordered');
validateOrderedSession(subSession, subset, words, 'ordered subset');
var subSessionN = P.buildSession(words, 2, mulberry32(5), subset, 'ordered');
validateOrderedSession(subSessionN, subset.slice(0, 2), words, 'ordered subset first 2');

/* ---------- shuffle mode ---------- */
var defaultSession = P.buildSession(words, 10, mulberry32(42));
var explicitShuffle = P.buildSession(words, 10, mulberry32(42), null, 'shuffle');
eq(defaultSession, explicitShuffle, 'default order is shuffle');

[10, 20, 50, 'all'].forEach(function (count) {
  var n = count === 'all' ? words.length : count;
  var session = P.buildSession(words, count, mulberry32(11), null, 'shuffle');
  var seen = Object.create(null);
  session.forEach(function (q) { seen[q.word] = true; });
  var distinct = Object.keys(seen);
  check(distinct.length === n, 'shuffle ' + count + ': ' + n + ' distinct words');
  check(session.length === qCount(distinct.map(function (w) { return byWord[w]; })),
    'shuffle ' + count + ': length is one or two questions per sampled word');
  validateSessionCoverage(session, distinct.map(function (w) { return byWord[w]; }),
    words, 'shuffle ' + count);
});

/* A shuffled sample must not simply be the file-order prefix. */
var shuffledPrefixes = 0;
for (var s = 1; s <= 25; s++) {
  var sh = P.buildSession(words, 10, mulberry32(s), null, 'shuffle');
  var shWords = sh.reduce(function (m, q) { m[q.word] = true; return m; }, {});
  if (Object.keys(shWords).join('|') ===
      words.slice(0, 10).map(function (w) { return w.word; }).join('|')) {
    shuffledPrefixes++;
  }
  check(Object.keys(shWords).length === 10, 'shuffle seed ' + s + ': ten distinct words');
}
check(shuffledPrefixes === 0, 'shuffle sessions are not the file-order prefix');

/* Shuffle is deterministic under a seeded rng and actually reorders the
   question list as a whole. */
var shuffleA = P.buildSession(words, 10, mulberry32(77), null, 'shuffle');
var shuffleB = P.buildSession(words, 10, mulberry32(77), null, 'shuffle');
eq(shuffleA, shuffleB, 'seeded shuffle is deterministic');
var shuffleC = P.buildSession(words, 10, mulberry32(78), null, 'shuffle');
check(JSON.stringify(shuffleA) !== JSON.stringify(shuffleC),
  'different seeds shuffle differently');
/* Pairs are not forced adjacent in shuffle mode (they may be, by chance, so
   compare against the ordered sequence instead: over 30 seeds at least one
   session must break adjacent pairing). */
var adjacentPairs = 0;
for (var ps = 1; ps <= 30; ps++) {
  var psSession = P.buildSession(words, 'all', mulberry32(ps), tenKanji, 'shuffle');
  var sig = signatures(psSession);
  for (var pi = 0; pi + 1 < sig.length; pi += 2) {
    if (sig[pi].indexOf('\u0000meaning') !== -1 &&
        sig[pi + 1] === sig[pi].replace('\u0000meaning', '\u0000reading')) {
      adjacentPairs++;
    }
  }
}
check(adjacentPairs < 30 * 10, 'shuffle mode reorders the whole question list (pairs not always adjacent)');

/* ---------- options still shuffled in ordered mode ---------- */
var firstQuestionIndexes = {};
var firstOptionOrders = {};
for (var seed = 1; seed <= 40; seed++) {
  var ordered = P.buildSession(words, 10, mulberry32(seed), null, 'ordered');
  check(ordered[0].word === words[0].word && ordered[0].type === 'meaning',
    'ordered seed ' + seed + ': q1 is data[0] meaning');
  if (words[0].word !== words[0].reading) {
    check(ordered[1].word === words[0].word && ordered[1].type === 'reading',
      'ordered seed ' + seed + ': q2 is data[0] reading');
  }
  firstQuestionIndexes[ordered[0].answerIndex] = true;
  firstOptionOrders[ordered[0].options.join('\u0001')] = true;
}
check(Object.keys(firstQuestionIndexes).length >= 3,
  'ordered mode: correct option position varies (options are shuffled)');
check(Object.keys(firstOptionOrders).length >= 3,
  'ordered mode: option order varies between sessions');

/* ---------- every word, both question types ---------- */
words.forEach(function (w, i) {
  validateQuestion(P.buildQuestion(w, words, 'meaning', mulberry32(i + 1)),
    w, words, 'direct meaning ' + w.word);
  if (P.canAskReading(w)) {
    validateQuestion(P.buildQuestion(w, words, 'reading', mulberry32(i + 1)),
      w, words, 'direct reading ' + w.word);
  } else {
    var fallback = P.buildQuestion(w, words, 'reading', mulberry32(i + 1));
    check(fallback.type === 'meaning',
      'kana-only word ' + w.word + ' cannot produce a reading question');
  }
});

/* ---------- many seeded sessions, both orders ---------- */
var sessionTypes = {};
for (var mixSeed = 1; mixSeed <= 60; mixSeed++) {
  var mixCount = [10, 20, 50, 'all'][mixSeed % 4];
  var mixOrder = mixSeed % 2 ? 'ordered' : 'shuffle';
  var mixSession = P.buildSession(words, mixCount, mulberry32(mixSeed * 17), null, mixOrder);
  var mixLabel = mixOrder + ' mixed seed ' + mixSeed;
  var mixSeen = Object.create(null);
  mixSession.forEach(function (q) {
    mixSeen[q.word] = true;
    sessionTypes[q.type] = true;
  });
  var mixDistinct = Object.keys(mixSeen);
  var expectedN = mixCount === 'all' ? words.length : mixCount;
  check(mixDistinct.length === expectedN, mixLabel + ': ' + expectedN + ' distinct words');
  check(mixSession.length === qCount(mixDistinct.map(function (w) { return byWord[w]; })),
    mixLabel + ': question count follows the per-word rule');
  if (mixOrder === 'ordered') {
    validateOrderedSession(mixSession, words.slice(0, expectedN), words, mixLabel);
  } else {
    validateSessionCoverage(mixSession, mixDistinct.map(function (w) { return byWord[w]; }),
      words, mixLabel);
  }
}
check(sessionTypes.meaning === true && sessionTypes.reading === true,
  'both question types are generated');

/* ---------- localStorage persistence helpers ---------- */
function fakeStorage(initial) {
  var data = Object.assign({}, initial || {});
  return {
    data: data,
    getItem: function (k) { return Object.prototype.hasOwnProperty.call(data, k) ? data[k] : null; },
    setItem: function (k, v) { data[k] = String(v); },
    removeItem: function (k) { delete data[k]; }
  };
}

check(P.ORDER_KEY === 'n3practice-order:v1', 'storage key is n3practice-order:v1');
var store = fakeStorage();
eq(P.readOrder(store), 'shuffle', 'default order is shuffle');
P.writeOrder(store, 'ordered');
eq(store.getItem('n3practice-order:v1'), 'ordered', 'ordered choice persisted');
eq(P.readOrder(store), 'ordered', 'ordered choice restored');
P.writeOrder(store, 'shuffle');
eq(store.getItem('n3practice-order:v1'), 'shuffle', 'shuffle choice persisted');
eq(P.readOrder(store), 'shuffle', 'shuffle choice restored');
var junk = fakeStorage({ 'n3practice-order:v1': 'sideways' });
eq(P.readOrder(junk), 'shuffle', 'unknown stored value falls back to shuffle');
var broken = {
  getItem: function () { throw new Error('blocked'); },
  setItem: function () { throw new Error('blocked'); }
};
eq(P.readOrder(broken), 'shuffle', 'throwing storage reads as shuffle');
P.writeOrder(broken, 'ordered'); /* must not throw */
check(true, 'throwing storage does not break writeOrder');

/* ---------- word range: clamping / pool ---------- */
check(P.RANGE_KEY === 'n3practice-range:v1', 'storage key is n3practice-range:v1');

eq(P.clampRange({ from: 51, to: 100 }, 243), { from: 51, to: 100 },
  'valid range is kept');
eq(P.clampRange({ from: 100, to: 51 }, 243), { from: 51, to: 100 },
  'From > To is swapped, never empty');
eq(P.clampRange({ from: 5, to: 5 }, 243), { from: 5, to: 5 },
  'a single-word range stays valid');
eq(P.clampRange({ from: -5, to: 999 }, 243), { from: 1, to: 243 },
  'out-of-bounds range clamps to the list');
eq(P.clampRange({ from: 0, to: 0 }, 243), { from: 1, to: 1 },
  'zero/blank numbers clamp to a non-empty range');
eq(P.clampRange({ from: 'x', to: 'y' }, 243), { from: 1, to: 243 },
  'non-numeric range falls back to the full list');
eq(P.clampRange({ from: 50.6, to: 60.2 }, 243), { from: 51, to: 60 },
  'range endpoints are rounded');
eq(P.clampRange({ from: 300, to: 400 }, 243), { from: 243, to: 243 },
  'From beyond the list still yields a non-empty range');

eq(P.rangeWords(words, null), words, 'no range means the full list');
eq(P.rangeWords(words, { from: 1, to: 243 }), words, 'full range means the full list');
eq(P.rangeWords(words, { from: 1, to: 999 }), words, 'range past the end means the full list');
var r51pool = P.rangeWords(words, { from: 51, to: 100 });
eq(r51pool.map(function (w) { return w.word; }),
  words.slice(50, 100).map(function (w) { return w.word; }),
  'range 51-100 is exactly data[50..99] in file order');
eq(r51pool.length, 50, 'range 51-100 has 50 words');

/* ---------- word range: sessions ---------- */
var rOrdered10Words = words.slice(50, 60);
validateOrderedSession(P.buildSession(words, 10, mulberry32(31), r51pool, 'ordered'),
  rOrdered10Words, words, 'range 51-100 ordered 10');
validateOrderedSession(P.buildSession(words, 243, mulberry32(31), r51pool, 'ordered'),
  r51pool, words, 'range 51-100 ordered All 243');
validateOrderedSession(P.buildSession(words, 'all', mulberry32(31), r51pool, 'ordered'),
  r51pool, words, 'range 51-100 ordered "all"');

/* A size larger than the range is the whole range. */
var tinyPool = P.rangeWords(words, { from: 1, to: 5 });
validateOrderedSession(P.buildSession(words, 20, mulberry32(32), tinyPool, 'ordered'),
  tinyPool, words, 'size 20 in a 5-word range ordered = whole range');
validateOrderedSession(P.buildSession(words, 243, mulberry32(32), tinyPool, 'ordered'),
  tinyPool, words, 'All in a 5-word range ordered = whole range');
var tinyShuffle = P.buildSession(words, 20, mulberry32(32), tinyPool, 'shuffle');
eq(Object.keys(tinyShuffle.reduce(function (m, q) { m[q.word] = true; return m; }, {})).sort(),
  tinyPool.map(function (w) { return w.word; }).sort(),
  'size 20 in a 5-word range shuffle covers the whole range');
check(tinyShuffle.length === qCount(tinyPool),
  'size 20 in a 5-word range shuffle = one or two questions per range word');

/* A range larger than the session keeps the session size. */
var widePool = P.rangeWords(words, { from: 1, to: 100 });
validateOrderedSession(P.buildSession(words, 10, mulberry32(33), widePool, 'ordered'),
  words.slice(0, 10), words, 'size 10 in a 100-word range ordered = first 10 of the range');

/* Shuffle sessions draw only from the range, every seed. */
var rWords = Object.create(null);
r51pool.forEach(function (w) { rWords[w.word] = true; });
for (var rSeed = 1; rSeed <= 25; rSeed++) {
  var rShuffle = P.buildSession(words, 10, mulberry32(rSeed), r51pool, 'shuffle');
  var rDistinct = rShuffle.reduce(function (m, q) { m[q.word] = true; return m; }, {});
  check(Object.keys(rDistinct).length === 10,
    'range shuffle seed ' + rSeed + ': 10 distinct words');
  check(rShuffle.length === qCount(Object.keys(rDistinct).map(function (w) { return byWord[w]; })),
    'range shuffle seed ' + rSeed + ': question count follows the per-word rule');
  check(rShuffle.every(function (q) { return rWords[q.word] === true; }),
    'range shuffle seed ' + rSeed + ': every word is inside 51-100');
}
var rShuffleAll = P.buildSession(words, 'all', mulberry32(34), r51pool, 'shuffle');
validateSessionCoverage(rShuffleAll, r51pool, words, 'shuffle All in range 51-100');
eq(Object.keys(rShuffleAll.reduce(function (m, q) { m[q.word] = true; return m; }, {})).sort(),
  Object.keys(rWords).sort(), 'shuffle All in a range covers exactly the range');

/* Distractors may still come from outside the range (allWords is the full
   list), so a small range never runs out of options. */
var tinyQuestions = P.buildSession(words, 5, mulberry32(35), tinyPool, 'ordered');
tinyQuestions.forEach(function (q) {
  validateQuestion(q, byWord[q.word], words, 'tiny-range distractor check ' + q.word);
});

/* Retry-missed subset still wins over the range and regenerates BOTH types
   for each missed word. */
var rangeSubset = [words[120], words[10], words[200]];
validateOrderedSession(P.buildSession(words, 'all', mulberry32(36), rangeSubset, 'ordered'),
  rangeSubset, words, 'retry-missed subset ignores the range (ordered) and keeps both types');
var rangeSubsetShuffle = P.buildSession(words, 'all', mulberry32(36), rangeSubset, 'shuffle');
validateSessionCoverage(rangeSubsetShuffle, rangeSubset, words,
  'retry-missed subset ignores the range (shuffle)');

/* Retry-missed with a kana-only word: that word gets no reading question. */
var retryMix = [words[5], words[0], words[5]]; /* とても (kana), 西洋, とても */
var retryMixSession = P.buildSession(words, 'all', mulberry32(37), retryMix, 'ordered');
validateOrderedSession(retryMixSession, retryMix, words, 'retry-missed kana + kanji');
eq(retryMixSession.length, 4, 'retry-missed kana + kanji = 4 questions (1 + 2 + 1)');

/* ---------- word range: persistence ---------- */
var rangeStore = fakeStorage();
eq(P.readRange(rangeStore), null, 'default range is none (full list)');
P.writeRange(rangeStore, { from: 51, to: 100 });
eq(rangeStore.getItem('n3practice-range:v1'), '{"from":51,"to":100}',
  'range is stored as JSON {from,to}');
eq(P.readRange(rangeStore), { from: 51, to: 100 }, 'range restored from storage');
P.writeRange(rangeStore, null);
eq(rangeStore.getItem('n3practice-range:v1'), null, 'reset removes the range key');
eq(P.readRange(rangeStore), null, 'after reset the full list is active');
eq(P.readRange(fakeStorage({ 'n3practice-range:v1': 'not json' })), null,
  'unparseable stored range reads as full list');
eq(P.readRange(fakeStorage({ 'n3practice-range:v1': '{"from":"x","to":10}' })), null,
  'non-numeric stored range reads as full list');
eq(P.readRange(fakeStorage({ 'n3practice-range:v1': '42' })), null,
  'non-object stored range reads as full list');
var storedOutOfBounds = P.readRange(fakeStorage({ 'n3practice-range:v1': '{"from":-20,"to":9999}' }));
eq(storedOutOfBounds, { from: -20, to: 9999 }, 'stored out-of-bounds range is read raw');
eq(P.clampRange(storedOutOfBounds, 243), { from: 1, to: 243 },
  'stored out-of-bounds range clamps to the full list at load');
var brokenRange = {
  getItem: function () { throw new Error('blocked'); },
  setItem: function () { throw new Error('blocked'); },
  removeItem: function () { throw new Error('blocked'); }
};
eq(P.readRange(brokenRange), null, 'throwing storage reads as no range');
P.writeRange(brokenRange, { from: 1, to: 2 }); /* must not throw */
P.writeRange(brokenRange, null);              /* must not throw */
check(true, 'throwing storage does not break writeRange');
eq(P.rangeCoversAll({ from: 1, to: 243 }, 243), true, 'rangeCoversAll: full range');
eq(P.rangeCoversAll({ from: 1, to: 242 }, 243), false, 'rangeCoversAll: partial range');
eq(P.rangeCoversAll(null, 243), true, 'rangeCoversAll: no range');

/* ---------- word-pool selection vs the pre-change git baseline ---------- */
/* The question list is now two-per-word, so a session no longer matches the
   old one. The guard that still must hold is POOL SELECTION: for a given
   seed the sampled word set is exactly the old sampler's. While the working
   tree has uncommitted changes, `git show HEAD:...` is the previous release.
   After the orchestrator commits, HEAD is this file and the comparison is
   skipped. */
(function compareBaseline() {
  var working = fs.readFileSync(PRACTICE, 'utf8');
  var baseline = null;
  try {
    baseline = childProcess.execFileSync('git', ['show', 'HEAD:static/practice.js'], {
      cwd: ROOT, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore']
    });
  } catch (e) { baseline = null; }
  if (!baseline || baseline === working) {
    console.log('baseline comparison skipped (HEAD already matches the working file)');
    return;
  }
  var tmp = path.join(os.tmpdir(), 'n3-practice-baseline-' + process.pid + '.js');
  fs.writeFileSync(tmp, baseline);
  try {
    var oldP = loadModule(tmp);
    for (var seed = 1; seed <= 20; seed++) {
      [10, 20, 50, 'all'].forEach(function (count) {
        var oldWords = oldP.buildSession(words, count, mulberry32(seed)).map(function (q) { return q.word; });
        var newSession = P.buildSession(words, count, mulberry32(seed), null, 'shuffle');
        var newWords = newSession.reduce(function (m, q) { m[q.word] = true; return m; }, {});
        eq(Object.keys(newWords).sort(), oldWords.slice().sort(),
          'shuffle ' + count + ' seed ' + seed + ': sampled word set matches the old sampler');
      });
      var oldSub = oldP.buildSession(words, 'all', mulberry32(seed), subset)
        .map(function (q) { return q.word; });
      var newSub = P.buildSession(words, 'all', mulberry32(seed), subset, 'shuffle')
        .reduce(function (m, q) { m[q.word] = true; return m; }, {});
      eq(Object.keys(newSub).sort(), oldSub.slice().sort(),
        'shuffle subset seed ' + seed + ': sampled word set matches the old sampler');
      [10, 20, 50].forEach(function (count) {
        var oldOrdered = oldP.buildSession(words, count, mulberry32(seed), null, 'ordered')
          .map(function (q) { return q.word; });
        var seenOrder = Object.create(null);
        var newOrdered = [];
        P.buildSession(words, count, mulberry32(seed), null, 'ordered').forEach(function (q) {
          if (!seenOrder[q.word]) { seenOrder[q.word] = true; newOrdered.push(q.word); }
        });
        eq(newOrdered, oldOrdered,
          'ordered ' + count + ' seed ' + seed + ': word sequence matches the old session');
      });
    }
  } finally {
    try { fs.unlinkSync(tmp); } catch (e) {}
  }
})();

/* ---------- report ---------- */
if (failures.length) {
  console.error('\n' + failures.length + ' check(s) failed:');
  failures.slice(0, 40).forEach(function (f) { console.error('  ✗ ' + f); });
  if (failures.length > 40) console.error('  … and ' + (failures.length - 40) + ' more');
  console.error('\n' + (checks - failures.length) + ' / ' + checks + ' checks passed');
  process.exit(1);
}
console.log('All ' + checks + ' practice logic checks passed.');
