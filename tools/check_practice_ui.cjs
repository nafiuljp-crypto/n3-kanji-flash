#!/usr/bin/env node
/* Headless-Chromium check for the Vocab Practice order toggle.
 *
 * The built site is served from dist/ through context.route() at a public
 * test origin (http://site.test/n3-kanji-flash/) with correct MIME types, so
 * nothing touches the network and localStorage works per origin. Chromium is
 * the image's /opt/meta-chromium/chrome, which needs the Hatch WebGL policy
 * flags. See AGENTS.md.
 *
 * Run: node tools/check_practice_ui.cjs
 */
'use strict';

var fs = require('fs');
var path = require('path');
var os = require('os');
var crypto = require('crypto');

var ROOT = path.resolve(__dirname, '..');
var DIST = path.join(ROOT, 'dist');
var DATA = path.join(ROOT, 'data', 'vocab_practice_2025_12.json');
var ORIGIN = 'http://site.test';
var SITE = '/n3-kanji-flash/';
var CHROME = process.env.CHROMIUM_PATH || '/opt/meta-chromium/chrome';
var POLICY = process.env.HATCH_WEBGL_POLICY ||
  '/var/lib/hatch-browser/rootfs-base/usr/share/hatch/chromium/webgl-allowed-domains.txt';
var LOCK_HASH = '03ac674216f3e15c761ee1a5e255f067953623c8b388b4459e13f978d7c846f4';
var ORDER_KEY = 'n3practice-order:v1';
var RANGE_KEY = 'n3practice-range:v1';

var checks = 0;
var failures = [];

function check(cond, msg) {
  checks++;
  if (!cond) { failures.push(msg); console.error('  ✗ ' + msg); }
  else console.log('  ✓ ' + msg);
}

function resolvePlaywright() {
  try { return require('playwright-core'); } catch (e) { /* fall through */ }
  var npx = path.join(os.homedir(), '.npm', '_npx');
  var candidates = [];
  if (fs.existsSync(npx)) {
    fs.readdirSync(npx).forEach(function (dir) {
      var p = path.join(npx, dir, 'node_modules', 'playwright-core');
      if (fs.existsSync(p)) candidates.push(p);
    });
  }
  for (var i = 0; i < candidates.length; i++) {
    try { return require(candidates[i]); } catch (e) {}
  }
  throw new Error('playwright-core not found (npm i playwright-core in a temp dir or set NODE_PATH)');
}

var MIME = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'application/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json; charset=utf-8',
  '.svg': 'image/svg+xml',
  '.png': 'image/png',
  '.ico': 'image/x-icon'
};

var PNG_1x1 = Buffer.from(
  'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII=',
  'base64'
);

function serveFromDist(route) {
  var req = route.request();
  var url = new URL(req.url());
  if (url.host !== 'site.test') {
    /* External assets (e.g. WaniKani radical images) become a placeholder. */
    return route.fulfill({ status: 200, contentType: 'image/png', body: PNG_1x1 });
  }
  var rel = decodeURIComponent(url.pathname.slice(SITE.length));
  if (url.pathname === '/favicon.ico' || rel === 'favicon.ico') {
    return route.fulfill({ status: 200, contentType: 'image/png', body: PNG_1x1 });
  }
  if (!rel || rel.endsWith('/')) rel += 'index.html';
  var file = path.join(DIST, rel);
  if (!file.startsWith(DIST + path.sep) || !fs.existsSync(file) || !fs.statSync(file).isFile()) {
    return route.fulfill({ status: 404, contentType: 'text/html; charset=utf-8', body: 'not found' });
  }
  var type = MIME[path.extname(file).toLowerCase()] || 'application/octet-stream';
  return route.fulfill({ status: 200, contentType: type, body: fs.readFileSync(file) });
}

(async function main() {
  var words = JSON.parse(fs.readFileSync(DATA, 'utf8'));
  var playwright = resolvePlaywright();
  var policySha = crypto.createHash('sha256').update(fs.readFileSync(POLICY)).digest('hex');

  var browser = await playwright.chromium.launch({
    executablePath: CHROME,
    headless: true,
    args: [
      '--no-sandbox',
      '--disable-dev-shm-usage',
      '--hatch-webgl-allowed-domains-file=' + POLICY,
      '--hatch-webgl-allowed-domains-sha256=' + policySha
    ]
  });

  var context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.addInitScript(function (args) {
    try {
      localStorage.setItem('n3lock:v1', args.lockHash);
      localStorage.setItem('n3theme:v1', 'light');
    } catch (e) {}
  }, { lockHash: LOCK_HASH });

  var consoleErrors = [];
  await context.route('**/*', serveFromDist);

  var page = await context.newPage();
  page.on('console', function (msg) {
    if (msg.type() === 'error') consoleErrors.push('console: ' + msg.text());
  });
  page.on('pageerror', function (err) {
    consoleErrors.push('pageerror: ' + (err && err.message));
  });

  function state() {
    return page.evaluate(function () {
      var sub = document.querySelector('.ps-sub');
      var restart = document.querySelector('[data-act="reshuffle"]');
      var prompt = document.querySelector('.practice-prompt');
      var qno = document.querySelector('.q-no');
      var orderButtons = Array.prototype.map.call(
        document.querySelectorAll('[data-order]'),
        function (b) {
          return {
            value: b.getAttribute('data-order'),
            active: b.classList.contains('is-active'),
            pressed: b.getAttribute('aria-pressed')
          };
        });
      return {
        sub: sub ? sub.textContent : null,
        restart: restart ? restart.textContent.trim() : null,
        restartTitle: restart ? restart.getAttribute('title') : null,
        prompt: prompt ? prompt.textContent : null,
        qno: qno ? qno.textContent : null,
        optionCount: document.querySelectorAll('.practice-opt').length,
        orderButtons: orderButtons,
        stored: localStorage.getItem('n3practice-order:v1')
      };
    });
  }

  function rangeState() {
    return page.evaluate(function () {
      var fromEl = document.querySelector('#ps-range-from');
      var toEl = document.querySelector('#ps-range-to');
      var badge = document.querySelector('.ps-range-badge');
      var reset = document.querySelector('[data-act="range-reset"]');
      var allBtn = document.querySelector('[data-count="243"]');
      var qno = document.querySelector('.q-no');
      var prompt = document.querySelector('.practice-prompt');
      return {
        from: fromEl ? fromEl.value : null,
        to: toEl ? toEl.value : null,
        hasInputs: Boolean(fromEl && toEl),
        badge: badge ? badge.textContent.trim() : null,
        resetActive: reset ? reset.classList.contains('is-active') : null,
        allLabel: allBtn ? allBtn.textContent.trim() : null,
        qno: qno ? qno.textContent.trim() : null,
        prompt: prompt ? prompt.textContent : null,
        stored: localStorage.getItem('n3practice-range:v1')
      };
    });
  }

  async function setRangeInputs(from, to) {
    await page.evaluate(function (v) {
      var f = document.querySelector('#ps-range-from');
      var t = document.querySelector('#ps-range-to');
      if (!f || !t) return;
      f.value = v.from;
      t.value = v.to;
      t.dispatchEvent(new Event('change', { bubbles: true }));
    }, { from: String(from), to: String(to) });
    await page.waitForSelector('.practice-setup');
  }

  async function collectPrompts(n) {
    var prompts = [];
    for (var i = 0; i < n; i++) {
      prompts.push((await state()).prompt);
      if (i + 1 < n) {
        await page.click('.practice-opt[data-opt="1"]');
        await page.waitForSelector('.practice-feedback');
        await page.click('[data-act="next"]');
        await page.waitForFunction(function (k) {
          var el = document.querySelector('.q-no');
          return el && el.textContent.trim().indexOf(k + ' /') === 0;
        }, i + 2);
      }
    }
    return prompts;
  }

  async function startClean(mode) {
    await page.goto(ORIGIN + SITE + 'practice.html');
    await page.waitForSelector('.practice-setup');
    await page.evaluate(function (key) { localStorage.removeItem(key); }, ORDER_KEY);
    await page.reload();
    await page.waitForSelector('.practice-setup');
    if (mode) {
      await page.click('[data-order="' + mode + '"]');
      await page.waitForFunction(function (m) {
        var b = document.querySelector('[data-order="' + m + '"]');
        return b && b.classList.contains('is-active');
      }, mode);
    }
  }

  /* ---------- 1. default load: shuffle, session starts ---------- */
  console.log('\n[1] default load');
  await startClean(null);
  var s = await state();
  check(s.sub.indexOf('shuffled') !== -1, 'default subtitle says shuffled');
  check(s.orderButtons.find(function (b) { return b.value === 'shuffle'; }).active === true,
    'Shuffle order button is active by default');
  check(s.orderButtons.find(function (b) { return b.value === 'ordered'; }).active === false,
    'In order button is inactive by default');
  check(s.restart === 'Shuffle ↻', 'restart button reads "Shuffle ↻" by default');
  check(s.qno === '1 / 10', 'a 10-question session starts automatically');
  check(words.some(function (w) { return w.word === s.prompt; }), 'first prompt is a vocabulary word');
  check(s.optionCount === 4, 'first question has four options');
  check(s.stored === null, 'no order key is written before the user chooses');

  /* ---------- 2. ordered mode: file order ---------- */
  console.log('\n[2] In order');
  await page.click('[data-order="ordered"]');
  await page.waitForFunction(function (key) {
    return localStorage.getItem(key) === 'ordered';
  }, ORDER_KEY);
  s = await state();
  check(s.sub.indexOf('in list order') !== -1, 'ordered subtitle says "in list order"');
  check(s.restart === 'Restart ↻', 'restart button reads "Restart ↻" in ordered mode');
  check(s.restartTitle === 'Restart this ordered session', 'restart title does not claim a shuffle');
  check(s.stored === 'ordered', 'localStorage n3practice-order:v1 === "ordered"');
  check(s.prompt === words[0].word, 'ordered q1 is data[0]: ' + words[0].word);

  var prompts = [];
  for (var i = 0; i < 5; i++) {
    var cur = await state();
    prompts.push(cur.prompt);
    await page.click('.practice-opt[data-opt="1"]');
    await page.waitForSelector('.practice-feedback');
    await page.click('[data-act="next"]');
    await page.waitForFunction(function (n) {
      var el = document.querySelector('.q-no');
      return el && el.textContent.trim().indexOf(n + ' /') === 0;
    }, i + 2);
  }
  prompts.push((await state()).prompt);
  check(JSON.stringify(prompts) ===
    JSON.stringify(words.slice(0, 6).map(function (w) { return w.word; })),
    'first six prompts follow the data file order exactly');

  /* Restart must replay the same ordered session. */
  console.log('\n[3] restart in ordered mode');
  await page.click('[data-act="reshuffle"]');
  await page.waitForFunction(function (first) {
    var p = document.querySelector('.practice-prompt');
    return p && p.textContent === first;
  }, words[0].word);
  s = await state();
  check(s.prompt === words[0].word, 'Restart ↻ replays the ordered session from data[0]');
  check(s.sub.indexOf('in list order') !== -1, 'restart keeps the ordered subtitle');
  check(s.stored === 'ordered', 'restart keeps the stored order');
  await page.click('.practice-opt[data-opt="1"]');
  await page.waitForSelector('.practice-feedback');
  await page.click('[data-act="next"]');
  await page.waitForFunction(function (n) {
    var el = document.querySelector('.q-no');
    return el && el.textContent.trim().indexOf(n + ' /') === 0;
  }, 2);
  check((await state()).prompt === words[1].word,
    'Restart ↻ replays the same ordered sequence (q2 = data[1])');

  /* ---------- 4. back to shuffle: a session starts normally ---------- */
  console.log('\n[4] back to Shuffle');
  await page.click('[data-order="shuffle"]');
  await page.waitForFunction(function (key) {
    return localStorage.getItem(key) === 'shuffle';
  }, ORDER_KEY);
  s = await state();
  check(s.sub.indexOf('shuffled') !== -1, 'shuffle subtitle restored');
  check(s.restart === 'Shuffle ↻', 'restart button reads "Shuffle ↻" again');
  check(s.qno === '1 / 10', 'a fresh 10-question session starts');
  check(words.some(function (w) { return w.word === s.prompt; }), 'shuffle session has a valid prompt');
  check(s.optionCount === 4, 'shuffle session has four options');

  /* ---------- 5. persistence across reload ---------- */
  console.log('\n[5] persistence');
  await page.click('[data-order="ordered"]');
  await page.waitForFunction(function (key) {
    return localStorage.getItem(key) === 'ordered';
  }, ORDER_KEY);
  await page.reload();
  await page.waitForSelector('.practice-setup');
  s = await state();
  check(s.stored === 'ordered', 'ordered choice survives a reload');
  check(s.orderButtons.find(function (b) { return b.value === 'ordered'; }).active === true,
    'In order button is active after reload');
  check(s.sub.indexOf('in list order') !== -1, 'subtitle reflects the restored order');
  check(s.prompt === words[0].word, 'restored ordered session starts at data[0]');

  /* ---------- 6. retry-missed keeps miss order ---------- */
  console.log('\n[6] retry misses in ordered mode');
  /* This is a fresh ordered 10-question session at q1. Answer every question
     by option 1; collect the words that were actually missed, then check the
     retry session uses that same sequence. */
  for (var q = 1; q <= 10; q++) {
    await page.click('.practice-opt[data-opt="1"]');
    await page.waitForSelector('.practice-feedback');
    await page.click('[data-act="next"]');
    if (q < 10) {
      await page.waitForFunction(function (n) {
        var el = document.querySelector('.q-no');
        return el && el.textContent.trim().indexOf(n + ' /') === 0;
      }, q + 1);
    }
  }
  await page.waitForSelector('.practice-end');
  var missed = await page.evaluate(function () {
    return Array.prototype.map.call(document.querySelectorAll('.missed-item .mi-word'),
      function (el) { return el.textContent; });
  });
  check(missed.length > 0, 'the 10-question run produced missed words (' + missed.length + ')');
  if (missed.length > 0) {
    await page.click('[data-act="retry-missed"]');
    await page.waitForFunction(function (n) {
      var el = document.querySelector('.q-no');
      return el && el.textContent.trim().indexOf('1 / ' + n) === 0;
    }, missed.length);
    var retryPrompts = [];
    for (var r = 0; r < Math.min(missed.length, 6); r++) {
      retryPrompts.push((await state()).prompt);
      await page.click('.practice-opt[data-opt="1"]');
      await page.waitForSelector('.practice-feedback');
      if (r + 1 < Math.min(missed.length, 6)) {
        await page.click('[data-act="next"]');
        await page.waitForFunction(function (n) {
          var el = document.querySelector('.q-no');
          return el && el.textContent.trim().indexOf(n + ' /') === 0;
        }, r + 2);
      }
    }
    check(JSON.stringify(retryPrompts) === JSON.stringify(missed.slice(0, retryPrompts.length)),
      'retry-missed questions follow the miss occurrence order');
  }

  /* ---------- 7. dark mode styling ---------- */
  console.log('\n[7] dark mode');
  await page.click('#theme-toggle');
  await page.waitForFunction(function () {
    return document.documentElement.getAttribute('data-theme') === 'dark';
  });
  var darkStyle = await page.evaluate(function () {
    var active = document.querySelector('.order-btn.is-active');
    var idle = document.querySelector('.order-btn:not(.is-active)');
    function style(el) {
      var cs = getComputedStyle(el);
      return { bg: cs.backgroundColor, color: cs.color, border: cs.borderTopColor };
    }
    return { active: style(active), idle: style(idle) };
  });
  check(darkStyle.active.bg !== 'rgba(0, 0, 0, 0)' && darkStyle.active.bg !== 'transparent',
    'active order button keeps a filled background in dark mode');
  check(darkStyle.idle.bg !== undefined, 'inactive order button has a computed style');
  await page.click('#theme-toggle');
  await page.waitForFunction(function () {
    return document.documentElement.getAttribute('data-theme') === 'light';
  });

  /* ---------- 8. phone-width layout ---------- */
  console.log('\n[8] phone width');
  await page.setViewportSize({ width: 390, height: 844 });
  var fit = await page.evaluate(function () {
    var setup = document.querySelector('.practice-setup');
    return {
      page: document.documentElement.scrollWidth,
      win: window.innerWidth,
      setup: setup.scrollWidth,
      setupBox: setup.clientWidth
    };
  });
  check(fit.page <= fit.win + 1,
    'no horizontal page overflow at 390px (' + fit.page + ' <= ' + fit.win + ')');
  check(fit.setup <= fit.setupBox + 1,
    'session-setup controls fit at 390px (' + fit.setup + ' <= ' + fit.setupBox + ')');
  await page.setViewportSize({ width: 1280, height: 900 });

  /* ---------- 9. word range ---------- */
  console.log('\n[9] word range');
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.evaluate(function (key) { localStorage.removeItem(key); }, RANGE_KEY);
  await page.reload();
  await page.waitForSelector('.practice-setup');
  await page.click('[data-order="ordered"]');
  await page.waitForFunction(function (key) {
    return localStorage.getItem(key) === 'ordered';
  }, ORDER_KEY);

  /* Real typing: fill From, Tab (fires change), fill To, Tab. */
  await page.fill('#ps-range-from', '51');
  await page.press('#ps-range-from', 'Tab');
  await page.fill('#ps-range-to', '100');
  await page.press('#ps-range-to', 'Tab');
  await page.waitForFunction(function () {
    var b = document.querySelector('.ps-range-badge');
    return b && b.textContent.indexOf('51') !== -1;
  });
  var rs = await rangeState();
  check(rs.hasInputs, 'range From/To inputs are rendered in the setup bar');
  check(rs.from === '51' && rs.to === '100', 'typed range 51-100 is kept in the inputs');
  check(rs.badge === 'Words 51–100 of 243', 'range label reads "Words 51–100 of 243" (' + rs.badge + ')');
  check(rs.stored === '{"from":51,"to":100}', 'range persisted as JSON under n3practice-range:v1');
  check(rs.allLabel === 'All 50', 'All size button reflects the range size ("All 50" for 51-100)');
  check(rs.resetActive === false, 'reset button is not active while a range is set');
  check(rs.qno === '1 / 10', 'changing the range restarts the 10-question session');
  check(rs.prompt === words[50].word, 'ordered range session starts at data[50]: ' + words[50].word);

  var rangePrompts = await collectPrompts(6);
  check(JSON.stringify(rangePrompts) ===
    JSON.stringify(words.slice(50, 56).map(function (w) { return w.word; })),
    'ordered range prompts follow data[50..55]');

  /* Range survives a reload. */
  await page.reload();
  await page.waitForSelector('.practice-setup');
  await page.waitForFunction(function () {
    var b = document.querySelector('.ps-range-badge');
    return b && b.textContent.indexOf('51') !== -1;
  });
  rs = await rangeState();
  check(rs.stored === '{"from":51,"to":100}', 'range choice survives a reload');
  check(rs.badge === 'Words 51–100 of 243', 'range label restored after reload');
  check(rs.qno === '1 / 10' && rs.prompt === words[50].word,
    'restored range session starts at data[50]');

  /* Ordered All inside the range = exactly the range. */
  await page.click('[data-count="243"]');
  await page.waitForFunction(function (n) {
    var el = document.querySelector('.q-no');
    return el && el.textContent.trim() === '1 / ' + n;
  }, 50);
  rs = await rangeState();
  check(rs.prompt === words[50].word, 'ordered All in range starts at data[50]');

  /* Shuffle sessions draw only from the range. */
  await page.click('[data-order="shuffle"]');
  await page.waitForFunction(function (key) {
    return localStorage.getItem(key) === 'shuffle';
  }, ORDER_KEY);
  var rangeSet = {};
  words.slice(50, 100).forEach(function (w) { rangeSet[w.word] = true; });
  var shufflePrompts = await collectPrompts(10);
  check(new Set(shufflePrompts).size === 10, 'shuffled range session has 10 distinct words');
  check(shufflePrompts.every(function (w) { return rangeSet[w] === true; }),
    'shuffled range session draws only from data[50..99]');
  await page.click('[data-order="ordered"]');
  await page.waitForFunction(function (key) {
    return localStorage.getItem(key) === 'ordered';
  }, ORDER_KEY);

  /* Size larger than the range: the whole range. */
  await setRangeInputs(51, 55);
  await page.waitForFunction(function () {
    var b = document.querySelector('.ps-range-badge');
    return b && b.textContent === 'Words 51–55 of 243';
  });
  await page.click('[data-count="20"]');
  rs = await rangeState();
  check(rs.qno === '1 / 5', 'size 20 in a 5-word range is the whole range (1 / 5)');
  check(rs.allLabel === 'All 5', 'All size button reads "All 5" for a 5-word range');
  check(rs.prompt === words[50].word, 'range 51-55 ordered session starts at data[50]');

  /* Size within the range keeps the requested size. */
  await setRangeInputs(51, 100);
  await page.waitForFunction(function () {
    var b = document.querySelector('.ps-range-badge');
    return b && b.textContent === 'Words 51–100 of 243';
  });
  await page.click('[data-count="20"]');
  rs = await rangeState();
  check(rs.qno === '1 / 20', 'size 20 within range 51-100 gives 20 questions');

  /* From > To is swapped, never empty. */
  await setRangeInputs(100, 50);
  await page.waitForFunction(function () {
    var f = document.querySelector('#ps-range-from');
    var t = document.querySelector('#ps-range-to');
    return f && t && f.value === '50' && t.value === '100';
  });
  rs = await rangeState();
  check(rs.badge === 'Words 50–100 of 243', 'From > To is swapped to Words 50–100');
  check(rs.stored === '{"from":50,"to":100}', 'swapped range is persisted');
  check(rs.qno === '1 / 20', 'swapped range keeps the session size (20)');

  /* Out-of-bounds input clamps to the full list (no empty session). */
  await setRangeInputs(-5, 999);
  await page.waitForFunction(function () {
    var b = document.querySelector('.ps-range-badge');
    var f = document.querySelector('#ps-range-from');
    var t = document.querySelector('#ps-range-to');
    return !b && f && t && f.value === '1' && t.value === '243';
  });
  rs = await rangeState();
  check(rs.badge === null, 'out-of-bounds range clamps to the full list (no range label)');
  check(rs.stored === null, 'out-of-bounds range clears the stored range');
  check(rs.allLabel === 'All 243', 'All size button is "All 243" again');
  check(rs.qno === '1 / 20' && words.some(function (w) { return w.word === rs.prompt; }),
    'full-list fallback still yields a valid session');

  /* Empty fields fall back to the full list too. */
  await setRangeInputs('', '');
  await page.waitForFunction(function () {
    var b = document.querySelector('.ps-range-badge');
    return !b;
  });
  rs = await rangeState();
  check(rs.from === '1' && rs.to === '243', 'empty fields reset to 1 / 243');
  check(rs.stored === null, 'empty fields clear the stored range');

  /* The "All words" reset button clears an active range. */
  await setRangeInputs(51, 60);
  await page.waitForFunction(function () {
    var b = document.querySelector('.ps-range-badge');
    return b && b.textContent === 'Words 51–60 of 243';
  });
  await page.click('[data-act="range-reset"]');
  await page.waitForFunction(function () {
    var b = document.querySelector('.ps-range-badge');
    return !b;
  });
  rs = await rangeState();
  check(rs.stored === null, 'All words button clears the stored range');
  check(rs.resetActive === true, 'All words button is active for the full list');
  check(rs.from === '1' && rs.to === '243', 'All words button restores 1 / 243');

  /* 390px with a range active: no horizontal overflow. */
  await setRangeInputs(51, 100);
  await page.waitForFunction(function () {
    var b = document.querySelector('.ps-range-badge');
    return b && b.textContent.indexOf('51') !== -1;
  });
  await page.setViewportSize({ width: 390, height: 844 });
  var rangeFit = await page.evaluate(function () {
    var setup = document.querySelector('.practice-setup');
    return {
      page: document.documentElement.scrollWidth,
      win: window.innerWidth,
      setup: setup.scrollWidth,
      setupBox: setup.clientWidth
    };
  });
  check(rangeFit.page <= rangeFit.win + 1,
    'no page overflow at 390px with a range set (' + rangeFit.page + ' <= ' + rangeFit.win + ')');
  check(rangeFit.setup <= rangeFit.setupBox + 1,
    'range controls fit the setup bar at 390px (' + rangeFit.setup + ' <= ' + rangeFit.setupBox + ')');
  await page.setViewportSize({ width: 1280, height: 900 });

  /* Dark mode keeps the range controls legible. */
  await page.click('#theme-toggle');
  await page.waitForFunction(function () {
    return document.documentElement.getAttribute('data-theme') === 'dark';
  });
  var darkRange = await page.evaluate(function () {
    var input = document.querySelector('.ps-range-input');
    var badge = document.querySelector('.ps-range-badge');
    function style(el) {
      if (!el) return null;
      var cs = getComputedStyle(el);
      return { bg: cs.backgroundColor, color: cs.color, border: cs.borderTopColor };
    }
    return { input: style(input), badge: style(badge) };
  });
  check(darkRange.input && darkRange.input.bg !== 'rgba(0, 0, 0, 0)',
    'range input has a solid background in dark mode');
  check(darkRange.input && darkRange.input.color !== 'rgba(0, 0, 0, 0)',
    'range input text is visible in dark mode');
  check(darkRange.badge && darkRange.badge.color !== 'rgba(0, 0, 0, 0)',
    'range label is visible in dark mode');
  await page.click('#theme-toggle');
  await page.waitForFunction(function () {
    return document.documentElement.getAttribute('data-theme') === 'light';
  });

  /* Leave the page in its default state for the console check. */
  await page.evaluate(function (keys) {
    localStorage.removeItem(keys.range);
    localStorage.removeItem(keys.order);
  }, { range: RANGE_KEY, order: ORDER_KEY });

  /* ---------- 10. console ---------- */
  check(consoleErrors.length === 0,
    'no console errors' + (consoleErrors.length ? ': ' + consoleErrors.join(' | ') : ''));

  await browser.close();

  console.log('\n' + (checks - failures.length) + ' / ' + checks + ' UI checks passed');
  if (failures.length) process.exit(1);
})().catch(function (err) {
  console.error(err && err.stack || err);
  process.exit(1);
});
