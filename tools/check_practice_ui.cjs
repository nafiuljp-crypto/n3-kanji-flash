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

  /* ---------- 9. console ---------- */
  check(consoleErrors.length === 0,
    'no console errors' + (consoleErrors.length ? ': ' + consoleErrors.join(' | ') : ''));

  await browser.close();

  console.log('\n' + (checks - failures.length) + ' / ' + checks + ' UI checks passed');
  if (failures.length) process.exit(1);
})().catch(function (err) {
  console.error(err && err.stack || err);
  process.exit(1);
});
