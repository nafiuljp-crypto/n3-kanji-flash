/* Romaji → kana conversion for the reading questions.
   Hand-rolled, no dependencies (see ANALYSIS.md E.2 / owner decision F6).

   Accepts Hepburn and kunrei spellings (shi/si, chi/ti, tsu/tu, fu/hu,
   ji/zi, sha/sya, cha/tya, ja/zya, ...), consonant doubling (gakkou),
   syllabic n (nn, n', n before a consonant), long vowels (ou/oo/aa/uu/ee)
   and kana passed through untouched.

   N3Romaji.candidates(input) returns every kana form that should count as
   the same reading: the literal conversion, its long-mark (ー) variant, and
   — for romaji input only — the form with the trailing long vowel spelled
   out, so "chu" and "kyo" still match ちゅう / きょう. */
window.N3Romaji = (function () {
    "use strict";

    // 3-character digraphs: Hepburn, kunrei and the common variants.
    var THREE = {
        kya: "きゃ", kyu: "きゅ", kyo: "きょ",
        gya: "ぎゃ", gyu: "ぎゅ", gyo: "ぎょ",
        shi: "し", sha: "しゃ", shu: "しゅ", sho: "しょ", she: "しぇ",
        chi: "ち",
        sya: "しゃ", syu: "しゅ", syo: "しょ",
        cha: "ちゃ", chu: "ちゅ", cho: "ちょ", che: "ちぇ",
        tya: "ちゃ", tyu: "ちゅ", tyo: "ちょ",
        cya: "ちゃ", cyu: "ちゅ", cyo: "ちょ",
        nya: "にゃ", nyu: "にゅ", nyo: "にょ",
        hya: "ひゃ", hyu: "ひゅ", hyo: "ひょ",
        bya: "びゃ", byu: "びゅ", byo: "びょ",
        pya: "ぴゃ", pyu: "ぴゅ", pyo: "ぴょ",
        mya: "みゃ", myu: "みゅ", myo: "みょ",
        rya: "りゃ", ryu: "りゅ", ryo: "りょ",
        zya: "じゃ", zyu: "じゅ", zyo: "じょ",
        jya: "じゃ", jyu: "じゅ", jyo: "じょ",
        dya: "ぢゃ", dyu: "ぢゅ", dyo: "ぢょ",
        tsa: "つぁ", tsi: "つぃ", tsu: "つ", tse: "つぇ", tso: "つぉ",
        thi: "てぃ", dhi: "でぃ"
    };

    // 2-character pairs.
    var TWO = {
        ka: "か", ki: "き", ku: "く", ke: "け", ko: "こ",
        sa: "さ", si: "し", su: "す", se: "せ", so: "そ",
        ta: "た", ti: "ち", tu: "つ", te: "て", to: "と",
        na: "な", ni: "に", nu: "ぬ", ne: "ね", no: "の",
        ha: "は", hi: "ひ", fu: "ふ", hu: "ふ", he: "へ", ho: "ほ",
        ma: "ま", mi: "み", mu: "む", me: "め", mo: "も",
        ya: "や", yu: "ゆ", yo: "よ",
        ra: "ら", ri: "り", ru: "る", re: "れ", ro: "ろ",
        wa: "わ", wo: "を",
        ga: "が", gi: "ぎ", gu: "ぐ", ge: "げ", go: "ご",
        za: "ざ", zi: "じ", zu: "ず", ze: "ぜ", zo: "ぞ",
        da: "だ", di: "ぢ", du: "づ", de: "で", do: "ど",
        ba: "ば", bi: "び", bu: "ぶ", be: "べ", bo: "ぼ",
        pa: "ぱ", pi: "ぴ", pu: "ぷ", pe: "ぺ", po: "ぽ",
        ji: "じ", ja: "じゃ", ju: "じゅ", jo: "じょ",
        fa: "ふぁ", fi: "ふぃ", fe: "ふぇ", fo: "ふぉ"
    };

    var ONE = { a: "あ", i: "い", u: "う", e: "え", o: "お" };

    var VOWELS = "aiueo";
    // kana → the vowel of its row (used for the trailing long-vowel form)
    var ROW = {};
    (function () {
        var rows = [
            ["a", "あかさたなはまやらわがざだばぱゃぁゎ"],
            ["i", "いきしちにひみりぎじぢびぴぃ"],
            ["u", "うくすつぬふむゆるぐずづぶぷゅぅゔ"],
            ["e", "えけせてねへめれげぜでべぺぇ"],
            ["o", "おこそとのほもよろをごぞどぼぽょぉ"]
        ];
        rows.forEach(function (row) {
            for (var i = 0; i < row[1].length; i++) ROW[row[1][i]] = row[0];
        });
    })();
    var LONG_OF = { a: "あ", i: "い", u: "う", e: "い", o: "う" };

    // The plain kana that spells each row's long vowel.
    var VOWEL_KANA = { a: "あ", i: "い", u: "う", e: "え", o: "お" };

    function isLatin(ch) {
        return (ch >= "a" && ch <= "z") || (ch >= "A" && ch <= "Z");
    }

    function isKanaChar(ch) {
        var c = ch.charCodeAt(0);
        return (c >= 0x3041 && c <= 0x309f) ||   // hiragana
            (c >= 0x30a1 && c <= 0x30ff) ||      // katakana
            c === 0x30fc || c === 0x301c;        // ー 〜
    }

    function isConsonant(ch) {
        return !!ch && !VOWELS.includes(ch) && ch >= "a" && ch <= "z";
    }

    function isVowel(ch) {
        return !!ch && VOWELS.includes(ch);
    }

    /* Convert a romaji string to hiragana. Kana in the input passes through. */
    function toKana(input) {
        var s = String(input === undefined || input === null ? "" : input).toLowerCase();
        var out = "";
        var i = 0;
        while (i < s.length) {
            var ch = s[i];
            if (isKanaChar(ch)) { out += ch; i += 1; continue; }
            if (ch === " " || ch === "　" || ch === "'" || ch === "’") { i += 1; continue; }
            if (ch === "-" || ch === "‐" || ch === "−") { out += "ー"; i += 1; continue; }
            if (!isLatin(ch)) { i += 1; continue; }

            // sokuon: doubled consonant (n is handled below as ん)
            if (ch === "t" && s.substr(i, 3) === "tch") { out += "っ"; i += 1; continue; }
            if (ch !== "n" && isConsonant(ch) && s[i + 1] === ch) {
                out += "っ"; i += 1; continue;
            }

            // syllabic n
            if (ch === "n") {
                var nx = s[i + 1];
                if (nx === "n") {
                    // "nn" + vowel is ん + な行 (konnichiha → こんにちは);
                    // otherwise the pair is ん (gakkou-style san + consonant).
                    out += "ん";
                    i += isVowel(s[i + 2]) ? 1 : 2;
                    continue;
                }
                if (nx === "'" || nx === "’") { out += "ん"; i += 2; continue; }
                if (!isVowel(nx)) { out += "ん"; i += 1; continue; }
                // n + vowel falls through to na/ni/nu/ne/no
            }

            var three = s.substr(i, 3);
            if (THREE[three]) { out += THREE[three]; i += 3; continue; }
            var two = s.substr(i, 2);
            if (TWO[two]) { out += TWO[two]; i += 2; continue; }
            if (ONE[ch]) { out += ONE[ch]; i += 1; continue; }
            i += 1; // unknown latin character: drop it
        }
        return toHiragana(out);
    }

    function toHiragana(s) {
        return String(s === undefined || s === null ? "" : s).replace(/[ァ-ヶ]/g, function (ch) {
            return String.fromCharCode(ch.charCodeAt(0) - 0x60);
        });
    }

    /* The same reading with its long vowels written as ー
       (はあとがた → はーとがた, こう → こー). */
    function longMarkVariant(kana) {
        var out = "";
        var i = 0;
        while (i < kana.length) {
            var ch = kana[i];
            var row = ROW[ch];
            var nx = kana[i + 1];
            var isLong = row && nx &&
                (nx === VOWEL_KANA[row] || (row === "o" && nx === "う"));
            if (isLong) { out += ch + "ー"; i += 2; continue; }
            out += ch;
            i += 1;
        }
        return out;
    }

    /* Append the long vowel that follows the last kana's row, if any. */
    function longForm(kana) {
        if (!kana) return "";
        var last = kana[kana.length - 1];
        var row = ROW[last];
        return row ? kana + LONG_OF[row] : "";
    }

    function stripNoise(s) {
        return String(s === undefined || s === null ? "" : s)
            .replace(/[\s　'’]/g, "")
            .replace(/[.,!?！？。、・…]/g, "");
    }

    function kanaOnly(input) {
        return toHiragana(stripNoise(input)).toLowerCase();
    }

    /* Every kana form that should be accepted for this input. */
    function candidates(input) {
        var raw = stripNoise(input);
        var out = {};
        if (!/[A-Za-z]/.test(raw)) {
            var kana = kanaOnly(input);
            if (kana) out[kana] = 1;
            return Object.keys(out);
        }

        var lower = raw.toLowerCase();
        var spellings = {};
        spellings[lower] = 1;
        spellings[lower.replace(/ou/g, "oo")] = 1;   // koota → こうた
        spellings[lower.replace(/oo/g, "ou")] = 1;   // koutei spelled koutei
        Object.keys(spellings).forEach(function (spelling) {
            var base = toKana(spelling);
            if (!base) return;
            out[base] = 1;
            out[longMarkVariant(base)] = 1;
            var long = longForm(base);
            if (long) {
                out[long] = 1;
                out[longMarkVariant(long)] = 1;
            }
        });
        return Object.keys(out).filter(Boolean);
    }

    return {
        toKana: toKana,
        toHiragana: toHiragana,
        candidates: candidates,
        longMarkVariant: longMarkVariant
    };
})();
