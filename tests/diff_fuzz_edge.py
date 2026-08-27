"""Targeted edge-case differential: Python BangorG2P vs C, on inputs the random
corpus under-samples — the exact failure classes the two fixes address, plus
Unicode/UTF-8 boundary conditions. Exhaustive where feasible.

    python3 tests/diff_fuzz_edge.py

Exit 0 iff every case matches in both modes.
"""
from __future__ import annotations

import itertools
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "bindings" / "python"))

from techiaith.g2p.bangor_g2p import BangorG2P
from cy_phonemize import CyPhonemizer  # noqa: E402

ACCENTS = "âêîôûŵŷëïüäöáéíóúàèìòùñçøœæÂÊÎÔÛŴŶ"
LATIN_EXT = "".join(chr(c) for c in range(0x0100, 0x0180))  # all Latin Ext-A
EDGE_UNICODE = "×÷£€°±¬§¶·¿¡​­́̂’—…"      # non-alpha in letter ranges
LETTERS = "abcdefghijklmnopqrstuvwxyz"


def cases() -> list[str]:
    out: list[str] = []

    # 1. Word-final c/g softening (the `"" in "eiy"` quirk) — every consonant end.
    for pre in ["", "a", "ba", "do", "ma", "bea", "stri"]:
        for end in "cg":
            out.append(pre + end)
        for end in LETTERS:
            out.append(pre + end)          # all single-letter endings

    # 2. Soft c/g before every possible following char (e,i,y AND others AND end).
    for cg in "cg":
        for nxt in LETTERS + ACCENTS + "":
            out.append("a" + cg + nxt)
        out.append("a" + cg)               # word-final

    # 3. Accented letter breaking every 2-char digraph/diphthong.
    digraphs = ["sh","ch","th","ph","ck","ng","qu","wh","gh","kn","wr","gn","ar","or",
                "er","ir","ur","ee","ea","oo","oa","ai","ay","oi","oy","ou","ow","au",
                "aw","ew","ie","igh","tch","ough","augh"]
    for dg in digraphs:
        for acc in ACCENTS[:12]:
            # insert accent inside the digraph and around it
            if len(dg) >= 2:
                out.append(dg[0] + acc + dg[1:])
            out.append(acc + dg)
            out.append(dg + acc)
            out.append("z" + dg[0] + acc + dg[1:] + "n")

    # 4. Silent-final-e interacting with accents/sentinels.
    for w in ["mace","cage","face","page","race","rage","nice","ice","age","huge",
              "maçe","fâce","naïve","naive","caïn","reïd","noël","zoë"]:
        out.append(w)

    # 5. Every accented letter alone, doubled, and in a word.
    for ch in ACCENTS + LATIN_EXT:
        out += [ch, ch + ch, "a" + ch + "b", "b" + ch, ch + "c", "c" + ch + "g"]

    # 6. Non-alpha unicode (must be DROPPED, merging adjacency) between digraph halves.
    for junk in EDGE_UNICODE:
        out += ["zo" + junk + "i", "a" + junk + "c", junk + "cog", "dog" + junk,
                "z" + junk + "g", "sh" + junk, junk.join("ck")]

    # 7. Multi-byte boundary / truncation robustness (must not crash, must match).
    # NB: no embedded NUL — the C ABI is a NUL-terminated char*, so a mid-string \x00
    # is outside its contract (and never occurs in file-sourced training text).
    out += ["", "\x01", "\x01\x01", "a\x01b", "café"]

    # 8. Mixed real code-switch with accents.
    out += ["Café Bangor", "naïve résumé", "S4C à la carte", "dŵr çà", "coöperate",
            "Zoë's c© dog", "±5°C yn Bangor", "£5 giçin"]

    # 9. Short exhaustive: all 2-letter ASCII words (catches routing + final-cons).
    for a, b in itertools.product(LETTERS, LETTERS):
        out.append(a + b)

    # 10. Leading-zero digit runs abutting a letter or "_", swept across the UK phone
    # band (9-11 digits) and one length either side. Fix round 1 (Task 4, 2026-07-29)
    # found that welsh_normalize._phone_repl had none of _digit_seq_repl's trailing-
    # separator logic, so a 9-11-digit leading-zero run -- claimed by _PHONE, not
    # _DIGIT_SEQ -- FUSED into a following letter ("0800123456x" -> "...pump chwechx")
    # while the identical shape at length 8 or 12 correctly separated. This corpus had
    # no leading-zero run abutting a letter at exactly those lengths, so a clean
    # differential run was not evidence this path worked.
    for d in range(6, 13):
        digits = "0" + "".join(str(k % 10) for k in range(1, d))
        out.append(digits + "x")
        out.append(digits + "_")
    out += ["0800123456x", "0123456789x", "012345678x", "01234567891x",
            "0800 123 456x", "01248 382000x", "0800_"]

    # 10b. GROUPED phone shapes whose non-leading group is 5 digits. _PHONE's
    # `(?:[  -]?\d{2,4}){1,3}` cannot take 5 digits in one group, so Python's engine
    # BACKTRACKS and re-splits them 3+2 through the zero-width separator branch:
    # "0800 12345" matches as 0800|123|45. C's phone matcher was a single greedy walk, took
    # "1234", could not make a 2-digit group out of the lone "5" and gave up -- so the run
    # fell through to the cardinal pass and "0800 12345x" read "...tri chant pedwar deg
    # pumpx" in C against Python's "...tri pedwar pump x". The rows without a trailing
    # letter had been divergent since before the (?!\d) change; nothing in this corpus or in
    # normalize_golden.tsv had a 5-digit non-leading group, so "0 mismatches" was measuring
    # coverage rather than parity. Section 10 above only adds contiguous runs, which any
    # greedy parse gets right.
    out += ["0800 12345x", "07700 90012x", "0800 12345", "07700 90012",
            "0800 12345_", "07700 90012.", "01 234 56789x", "012 345 6789",
            "0800-12345x", "0800 12345x", "(01248) 38200x", "a(01248) 382000",
            # A phone-shaped match that _phone_repl DECLINES on the digit total (12 and 13
            # here). re.sub then resumes AFTER the declined span, so no position inside it
            # can start another _PHONE match -- "058 513715" sits inside "012 058 513715"
            # and is itself a valid 9-digit shape, which C used to claim and Python never
            # offered to the pattern. _DIGIT_SEQ, a separate pass, still spells "012" and
            # "058", leaving "513715" to the cardinal pass.
            "012 058 513715", "01 01442-58225", "012 04979690 56",
            "0123 0974 80 407", "01-09-65 44739", "012 0326 28967-0x"]
    # 10c. NON-ASCII DECIMAL DIGITS reaching the digit-run passes. `\d` and str.isdigit()
    # match every Unicode Nd, so `_DIGIT_SEQ`'s `0\d+` claimed "0٣٣" (Arabic-Indic threes)
    # and `_spell_digits` raised KeyError '٣' out of an ASCII-keyed table -- a crash on
    # ordinary mixed text, on the canonical interpreter. `_PHONE`/`_DIGIT_SEQ`/`_INTEGER`
    # are now ASCII (`_D` in welsh_normalize.py), which is the class cy_normalize.c's
    # byte-oriented passes can see, so these read the ASCII digits and leave the rest --
    # the same answer on both sides and on every interpreter, Unicode 13 or 16.
    # "𞓰" (U+1E4F0 Nag Mundari zero) is the interpreter-drift row: it postdates Unicode 13,
    # so it is a digit to 3.14 and not to the canonical 3.10. Under the old `\d` the SAME
    # input crashed on 3.14 and did not on 3.10; under `_D` neither claims it.
    for d in ("٣", "٠", "١", "۵", "०", "𝟑", "𞓰"):
        out += ["0" + d + d + "x", "0" + d + d, d + d, d, "0" + d, d + "x",
                "1" + d, "1," + d + d + d, "12" + d, "0800 " + d + d, "0800" + d]
    # The 2026-08-21 sweep narrowed EVERY consuming digit position to the ASCII class
    # (`_DECIMAL`, `_CURRENCY`, `_PERCENT`, `_DATE_MONTH`, `_TIME`, `_FRACTION`, `_UNIT`,
    # `_PENCE`, `_ORDINAL_RE`, `_BLYNEDD`, the math/degree lookarounds), so the four
    # previously-excluded divergences are now convergent passthroughs and are IN:
    for d in ("٣", "٠", "۵"):
        out += [d + "." + d, "£" + d, d + "%", d + " Ionawr 2020", d + "af", d + "/" + d,
                d + " blynedd", d + ":30", d + "km", d + "pm"]
    # Still divergent and still excluded: "٣05" -- the digit-run patterns' NEGATIVE
    # lookbehind guards deliberately keep `\d` (a guard narrowed is a match widened), so
    # Python refuses the "05" after a wide digit where C's byte test accepts it.
    # Recorded in docs/FOLLOWUPS.md §G; unchanged by the sweep.
    #
    # NOT added, deliberately: "0800α"/"0800д"/"0800中"/"0800ª"/"0800µ"/"0800ɐ". Those
    # still diverge -- Python's str.isalpha() is true for all six, but C's separator
    # decision (digit_seq_sep in cy_normalize.c) is built on cyp__cp_is_alpha, which
    # documents its own pre-existing gap: outside ASCII it defers to cp_is_word, which
    # knows only four Latin ranges. Adding any of these here would fail this gate, not
    # exercise a fix -- the actual fix needs real Unicode letter tables shared across
    # every \b-based pass in cy_normalize.c, which is out of scope for this task.
    # (The digit/letter SPLITTER below deliberately shares no part of that gap: both
    # sides use the Latin-only class, so these inputs stay out of section 11 too.)

    # 11. THE DIGIT/LETTER SPLITTER (FOLLOWUPS section G's peeling job, closed). A space
    # at every ASCII-digit <-> Latin-letter/_ boundary, both directions, mirrored between
    # _DIGIT_LETTER_BOUNDARY (Python) and pass_digit_letter_split (C) -- plus the trailing
    # separators inside currency and percent, which run before the splitter and glue their
    # REPLACEMENT. The matrix crosses digit runs with letters from every Latin range the
    # shared class knows (ASCII, Latin-1, Extended-A, Extended Additional) and "_", in
    # both directions and sandwiched, through the suffix passes that must keep their
    # claims (£Nx vs £NM, N% tails, pence, ordinals, the colonless clock) and the
    # s4c-alike codes whose pence lookbehind must keep refusing.
    latin = ["x", "q", "ê", "ō", "ŵ", "ŷ", "ḁ", "_"]
    runs = ["5", "05", "800", "0800", "2026", "1,000"]
    for L in latin:
        for r in runs:
            out += [r + L, L + r, L + r + L, r + L + r, L + " " + r + L]
    out += ["s4c", "s4c.", "a4b5c6", "covid19", "h2o", "x£5", "£5x", "£5M", "£5Mx",
            "£5millionx", "5%x", "50%x", "50%_", "3afx", "5kmx", "7pmx", "9ypx",
            "x7pm", "tud.007x", "1 Ionawr 2026x", "25 Rhagfyr 1999abc", "1 Ionawr 20261",
            "12:30x", "07:00x", "0.5x", "x0.5", "5_5", "_5_", "covid19 s4c h2o"]

    # 12. THE INTERIOR PUNCTUATION PEEL (FOLLOWUPS section G, closed). Every _PUNCT
    # member fused between word chars, at both attachment sides ("(" leads right,
    # everything else trails left), in runs, mixed with the multibyte marks (… —),
    # against digraph neighbours, hyphen-letter runs, the ACRONYM_JOIN marker (U+00B7,
    # NOT a _PUNCT member -- must stay word-internal), clitics and compounds. The
    # invariant behind these rows is phonemize(a+m+b) == phonemize(a+m+" b"); here they
    # guard the C mirror at id level.
    marks = [".", ",", ";", ":", "!", "?", "(", ")", '"', "…", "—"]
    words12 = ["ie", "na", "ci", "cath", "llan", "gŵn", "b-a-ch", "i'r", "d-d-d"]
    for m in marks:
        for a in words12[:4]:
            for b in words12:
                out.append(f"{a}{m}{b}")
        out += [f"ie{m}{m}na", f"ie{m} na", f"ie {m}na", f"a{m}(b", f"a){m}b",
                f"5{m}7", f"x{m}5", f"{m}ie{m}", f"ie{m}"]
    out += ["helo!!!sut", "((a))", "a.b.c.d", "un;;;dau", 'cath"…"ci', "a…—b",
            "ty(bach)!ci", "mae'r ci!yn dda", "a·b!c", "pris·da!ie", "No.10",
            "b-a-ch!na", "d-d-d.e-e-e", "(y)sgol", "llyfr(au)"]

    return out


def main() -> int:
    corpus = cases()
    print(f"edge corpus: {len(corpus)} inputs")
    bad = 0
    tok = {}
    with open(_REPO / "techiaith" / "g2p" / "c" / "tokens.tsv", encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 2 and p[1].lstrip("-").isdigit():
                tok[int(p[1])] = p[0]

    def sym(ids):
        return [tok.get(i, f"?{i}") for i in ids if i != 0] if isinstance(ids, list) else ids

    for mode in ("accented", "native"):
        ref = BangorG2P(english_mode=mode)
        lib = CyPhonemizer(english_mode=mode)
        mism = 0
        for t in corpus:
            try:
                r = ref.text_to_ids(t)
            except Exception as e:
                r = ("PYERR", type(e).__name__)
            try:
                c = lib.text_to_ids(t)
            except Exception as e:
                c = ("CERR", type(e).__name__)
            if r != c:
                if mism < 20:
                    print(f"  [{mode}] MISMATCH {t!r}\n     py={sym(r)}\n     c ={sym(c)}")
                mism += 1
        print(f"[{mode}] {len(corpus) - mism}/{len(corpus)} match" + ("  ✓" if not mism else "  FAIL"))
        bad += mism
    if bad:
        print(f"\nFAIL: {bad} edge mismatches")
        return 1
    print("\nPASS: byte-identical on all edge cases, both modes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
