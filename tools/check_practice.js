#!/usr/bin/env node
/* Logic checks for the Dec 2025 Vocab Practice generator (static/practice.js).
 *
 * There is no browser here: the module's UMD wrapper lets us require the
 * exact file the site ships, and buildSession/buildQuestion are pure. Covers
 * the original question guarantees plus the Shuffle / In-order toggle.
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

/* ---------- data sanity ---------- */
check(Array.isArray(words) && words.length === 243, 'data has 243 words');
var uniqueWords = {};
words.forEach(function (w) { uniqueWords[w.word] = true; });
check(Object.keys(uniqueWords).length === words.length, 'data words are unique');
check(words.every(function (w) { return w.word && w.reading && w.meaning; }),
  'every data word has word/reading/meaning');

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

function validateSession(session, expectedWords, allWords, label) {
  check(Array.isArray(session), label + ': session is an array');
  if (!Array.isArray(session)) return;
  check(session.length === expectedWords.length, label + ': session length ' + expectedWords.length);
  eq(session.map(function (q) { return q.word; }),
    expectedWords.map(function (w) { return w.word; }), label + ': word sequence');
  session.forEach(function (q, i) {
    check(q.n === i + 1, label + ': question ' + (i + 1) + ' numbering');
    check(q.total === expectedWords.length, label + ': question ' + (i + 1) + ' total');
    validateQuestion(q, expectedWords[i], allWords, label + ' q' + (i + 1));
  });
}

/* ---------- ordered mode ---------- */
[10, 20, 50].forEach(function (count) {
  var session = P.buildSession(words, count, mulberry32(count), null, 'ordered');
  validateSession(session, words.slice(0, count), words, 'ordered ' + count);
});

['all', 243, 999].forEach(function (count) {
  var session = P.buildSession(words, count, mulberry32(7), null, 'ordered');
  validateSession(session, words, words, 'ordered ' + count);
});

/* Ordered sessions ignore the RNG for word choice: same words, same order on
   every call, whatever the seed. (Question types/options may still vary.) */
[1, 2, 3, 99, 123456].forEach(function (seed) {
  var session = P.buildSession(words, 10, mulberry32(seed), null, 'ordered');
  eq(session.map(function (q) { return q.word; }),
    words.slice(0, 10).map(function (w) { return w.word; }),
    'ordered 10 seed ' + seed + ': file order');
});

/* A subset (retry-missed) in ordered mode is taken in the order given. */
var subset = [words[7], words[2], words[42], words[0]];
var subSession = P.buildSession(words, 'all', mulberry32(5), subset, 'ordered');
validateSession(subSession, subset, words, 'ordered subset');
var subSessionN = P.buildSession(words, 2, mulberry32(5), subset, 'ordered');
validateSession(subSessionN, subset.slice(0, 2), words, 'ordered subset first 2');

/* ---------- shuffle mode (unchanged behaviour) ---------- */
var defaultSession = P.buildSession(words, 10, mulberry32(42));
var explicitShuffle = P.buildSession(words, 10, mulberry32(42), null, 'shuffle');
eq(defaultSession, explicitShuffle, 'default order is shuffle');

[10, 20, 50, 'all'].forEach(function (count) {
  var n = count === 'all' ? words.length : count;
  var session = P.buildSession(words, count, mulberry32(11), null, 'shuffle');
  check(session.length === n, 'shuffle ' + count + ': length');
  var seen = {};
  session.forEach(function (q) { seen[q.word] = true; });
  check(Object.keys(seen).length === n, 'shuffle ' + count + ': unique words');
  session.forEach(function (q) {
    var item = words.filter(function (w) { return w.word === q.word; })[0];
    validateQuestion(q, item, words, 'shuffle ' + count + ' ' + q.word);
  });
});

/* A shuffled sample must not simply be the file-order prefix. */
var shuffledPrefixes = 0;
for (var s = 1; s <= 25; s++) {
  var sh = P.buildSession(words, 10, mulberry32(s), null, 'shuffle');
  if (sh.map(function (q) { return q.word; }).join('|') ===
      words.slice(0, 10).map(function (w) { return w.word; }).join('|')) {
    shuffledPrefixes++;
  }
  check(new Set(sh.map(function (q) { return q.word; })).size === 10,
    'shuffle seed ' + s + ': ten distinct words');
}
check(shuffledPrefixes === 0, 'shuffle sessions are not the file-order prefix');

/* ---------- options still shuffled in ordered mode ---------- */
var firstQuestionIndexes = {};
var firstOptionOrders = {};
for (var seed = 1; seed <= 40; seed++) {
  var ordered = P.buildSession(words, 10, mulberry32(seed), null, 'ordered');
  check(ordered[0].word === words[0].word, 'ordered seed ' + seed + ': first word is data[0]');
  firstQuestionIndexes[ordered[0].answerIndex] = true;
  firstOptionOrders[ordered[0].options.join('\u0001')] = true;
}
check(Object.keys(firstQuestionIndexes).length >= 3,
  'ordered mode: correct option position varies (options are shuffled)');
check(Object.keys(firstOptionOrders).length >= 3,
  'ordered mode: option order varies between sessions');

/* ---------- every word, both question types ---------- */
var byWord = Object.create(null);
words.forEach(function (w) { byWord[w.word] = w; });
words.forEach(function (w, i) {
  validateQuestion(P.buildQuestion(w, words, 'meaning', mulberry32(i + 1)),
    w, words, 'direct meaning ' + w.word);
  if (P.canAskReading(w)) {
    validateQuestion(P.buildQuestion(w, words, 'reading', mulberry32(i + 1)),
      w, words, 'direct reading ' + w.word);
  }
});

/* ---------- many seeded sessions, both orders ---------- */
var sessionTypes = {};
for (var mixSeed = 1; mixSeed <= 60; mixSeed++) {
  var mixCount = [10, 20, 50, 'all'][mixSeed % 4];
  var mixOrder = mixSeed % 2 ? 'ordered' : 'shuffle';
  var mixN = mixCount === 'all' ? words.length : mixCount;
  var mixSession = P.buildSession(words, mixCount, mulberry32(mixSeed * 17), null, mixOrder);
  var mixLabel = mixOrder + ' mixed seed ' + mixSeed;
  check(mixSession.length === mixN, mixLabel + ': length');
  var mixSeen = Object.create(null);
  mixSession.forEach(function (q) {
    mixSeen[q.word] = true;
    sessionTypes[q.type] = true;
    validateQuestion(q, byWord[q.word], words, mixLabel + ' ' + q.word);
  });
  check(Object.keys(mixSeen).length === mixN, mixLabel + ': unique words');
  if (mixOrder === 'ordered') {
    eq(mixSession.map(function (q) { return q.word; }),
      words.slice(0, mixN).map(function (w) { return w.word; }),
      mixLabel + ': file order');
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
    setItem: function (k, v) { data[k] = String(v); }
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

/* ---------- shuffle mode vs the pre-change git baseline ---------- */
/* While the working tree has uncommitted changes, `git show HEAD:...` is the
   previous release. Comparing seeded sessions proves shuffle mode is
   behaviourally identical to it. After the orchestrator commits, HEAD is this
   file and the comparison is skipped. */
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
        var oldSession = oldP.buildSession(words, count, mulberry32(seed));
        var newSession = P.buildSession(words, count, mulberry32(seed), null, 'shuffle');
        eq(newSession, oldSession,
          'shuffle ' + count + ' seed ' + seed + ' matches pre-change baseline');
      });
      var oldSub = oldP.buildSession(words, 'all', mulberry32(seed), subset);
      var newSub = P.buildSession(words, 'all', mulberry32(seed), subset, 'shuffle');
      eq(newSub, oldSub, 'shuffle subset seed ' + seed + ' matches pre-change baseline');
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
