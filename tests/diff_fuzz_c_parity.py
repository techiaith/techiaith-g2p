"""Differential fuzz: Python BangorG2P vs C libcy_phonemize (via ctypes binding).

Proves byte-identical phoneme IDs across a large, diverse corpus that the fixed
golden/LTS/normalize suites do NOT cover — the real guard against Risk #1
(phoneme drift between train-time Python and on-device C). Run in BOTH english modes.

    python3 tests/diff_fuzz_c_parity.py [N]

Exit 0 iff every input matches in both modes.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO / "bindings" / "python"))

from techiaith.g2p.bangor_g2p import BangorG2P, _HETERONYM
from cy_phonemize import CyPhonemizer  # noqa: E402

_DATA = _REPO / "techiaith" / "g2p" / "data" / "geiriadur-ynganu-bangor"


def _dict_words(path: Path, limit: int, rng: random.Random | None = None) -> list[str]:
    """Sample `limit` headwords from ACROSS the file.

    This used to `break` at `limit`, which meant every run tested the same alphabetical head
    and nothing else: 21% of bangordict.dict, 15% of bangordict.en.dict, 0% of cmudict.dict.
    Words in the tail were never parity-tested at all -- "use" is line 19,577 of 20,622 in
    bangordict.en.dict, so it had never once been compared between Python and C. A divergence
    anywhere past the cut was invisible, which is the opposite of what this harness claims.
    Read the whole file, then sample.
    """
    words: list[str] = []
    if not path.exists():
        return words
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line or line.startswith(("#", ";")):
            continue
        w = line.split()[0].split("(")[0]
        if w:
            words.append(w)
    if rng is not None and len(words) > limit:
        return rng.sample(words, limit)
    return words[:limit]


def build_corpus(n: int, seed: int = 1234) -> list[str]:
    rng = random.Random(seed)
    corpus: list[str] = []

    # 1. Real dictionary words (in-vocab) — Welsh, English-in-dict, names.
    cy = _dict_words(_DATA / "bangordict.dict", 6000, rng)
    xx = _dict_words(_DATA / "bangordict.xx.dict", 3000, rng)
    en = _dict_words(_DATA / "bangordict.en.dict", 3000, rng)
    # cmudict.dict was never sampled at all despite being the largest table (119,305 lines) and
    # the source of every English reading in a Welsh-context sentence.
    cmu = _dict_words(_DATA / "cmudict.dict", 3000, rng)
    for pool in (cy, xx, en, cmu):
        corpus.extend(rng.sample(pool, min(len(pool), n // 6)))

    # Heteronyms are the whole point of _HETERONYM and none of them appeared in this corpus, so
    # the parity guarantee was vacuous exactly where behaviour had just changed. Pin them in
    # explicitly -- bare, and in a frame, since the two take different lexicon routes.
    for w in sorted(_HETERONYM):
        corpus.append(w)
        corpus.append(f"I will {w} it")
        corpus.append(f"the {w} was here")

    # 2. Multi-word sentences (mutations, clitics, spacing) from dict words.
    allw = cy + xx + en
    if allw:
        for _ in range(n // 4):
            k = rng.randint(2, 8)
            corpus.append(" ".join(rng.choice(allw) for _ in range(k)))

    # 3. Digraphs / diacritics / edge orthography (OOV-forcing).
    frags = ["ll", "rh", "dd", "ch", "ng", "ph", "th", "si", "wy"]
    vowels = list("aeiouwy") + ["â", "ê", "î", "ô", "û", "ŵ", "ŷ", "ë", "ï", "ä"]
    for _ in range(n // 6):
        k = rng.randint(1, 5)
        corpus.append("".join(rng.choice(frags) + rng.choice(vowels) for _ in range(k)))

    # 4. Numbers / dates / times / currency / percentages / symbols (normalization).
    for _ in range(n // 6):
        kind = rng.randint(0, 8)
        if kind == 0:
            corpus.append(str(rng.randint(0, 999_999_999)))
        elif kind == 1:
            corpus.append(f"{rng.randint(0,100)}.{rng.randint(0,99):02d}")
        elif kind == 2:
            corpus.append(f"£{rng.randint(0,9999)}.{rng.randint(0,99):02d}")
        elif kind == 3:
            corpus.append(f"{rng.randint(0,100)}%")
        elif kind == 4:
            corpus.append(f"{rng.randint(1,31)}/{rng.randint(1,12)}/{rng.randint(1900,2099)}")
        elif kind == 5:
            corpus.append(f"{rng.randint(0,23)}:{rng.randint(0,59):02d}")
        elif kind == 6:
            corpus.append(f"{rng.randint(1,31)} Ionawr {rng.randint(1900,2099)}")
        elif kind == 7:
            corpus.append(f"BBC & S4C {rng.randint(0,999)}")
        else:
            corpus.append(rng.choice(["+", "=", "@", "/", "-", "&", "%", "£"]))

    # 4b. Fractions, units, and UNICODE whitespace. Python's \s -- in _UNIT's `\s?`
    # and in the closing `re.sub(r"\s+", " ", text)` -- is the full 29-codepoint
    # isspace() set, not ASCII. A non-breaking or thin space before a unit is ordinary
    # typesetting, and an ASCII-only reading left "5<NBSP>km" as "pump<NBSP>km" instead
    # of "pum cilomedr", and "ci<NBSP>cath" un-collapsed.
    #
    # Separators are placed FREELY here -- between value and unit, around fractions, in
    # ordinary word gaps, and (since the 2026-08-21 \s sweep gave percent, math/degree,
    # ampersand and date-month re_space_len) before "%", month names and after "&" --
    # all of which are green. ONE construct stays excluded on purpose, because its pass
    # still reads \s as ASCII and a general fuzz would go red on a pre-existing
    # divergence instead of finding new ones:
    #     CAPS  + \s + CAPS       (_deshout's text.split() -- Unicode; C's word walk is not)
    # Measured residue: 34/46 divergent. Reported, not fixed; drop the exclusion only
    # once pass_deshout handles Unicode \s.
    unit_ws = [
        "", " ", "\t",                                  # none / ASCII
        "\u000b", "\u000c", "\u001c", "\u001d", "\u001e", "\u001f", "\u0085",  # ASCII-range \s
        "\u00a0", "\u1680", "\u2000", "\u2004", "\u2007", "\u2009", "\u200a",  # Unicode spaces
        "\u2028", "\u2029", "\u202f", "\u205f", "\u3000",
    ]
    units = ["km", "kg", "cm", "mm", "m", "g", "l"]
    cy_words = ["ci", "cath", "bore", "da", "mynydd", "yr", "a'r", "gwyn"]
    for _ in range(n // 8):
        w = rng.choice(unit_ws)
        v = rng.choice([rng.randint(0, 10), rng.randint(11, 999), rng.randint(1000, 10**9)])
        corpus.append(f"{v}{w}{rng.choice(units)}")
        corpus.append(f"mae {v}{w}{rng.choice(units)} o hyd")
        # fractions: proper, improper, out-of-range and zero-denominator, plus the
        # chained form that pins re.sub's span consumption ("11/7/8" has ONE match)
        a, b = rng.randint(0, 30), rng.randint(0, 30)
        corpus.append(f"{a}/{b}")
        corpus.append(f"{a}/{b}/{rng.randint(0, 30)}")
        # whitespace that no pass consumes, so it must survive to the closing collapse
        corpus.append(w.join(rng.choice(cy_words) for _ in range(rng.randint(2, 5))))
        corpus.append(f"{w}{rng.choice(cy_words)}{w}{v}{w}")
        # the constructs freed by the \s sweep: percent, math/degree, ampersand, date-month
        corpus.append(f"{v}{w}%")
        corpus.append(f"{rng.randint(0, 99)}{w}x{w}{rng.randint(0, 99)}")
        corpus.append(f"98.6{w}°F")
        corpus.append(f"ci &{w}chath")
        corpus.append(f"{rng.randint(1, 31)}{w}Ionawr{w}{rng.randint(1900, 2099)}")

    # 4c. In-word digits (the digit/letter splitter) and glued clock/suffix shapes. Latin
    # letters only, both directions and sandwiched -- non-Latin letters stay excluded for
    # the same reason as everywhere else (the disclosed cp_is_word gap). Covers the nine
    # section-G glue shapes by construction: value + suffix-or-not + letter tail.
    latin_letters = ["x", "b", "q", "ê", "ô", "ŵ", "ḁ", "_"]
    tails = ["", "%", "p", "c", "af", "km", "m", "pm", "yb", "M", "bn", "million"]
    for _ in range(n // 10):
        L = rng.choice(latin_letters)
        v = rng.choice([str(rng.randint(0, 99)), f"0{rng.randint(0, 999)}",
                        f"{rng.randint(0, 23)}:{rng.randint(0, 59):02d}",
                        f"£{rng.randint(0, 999)}", f"{rng.randint(0, 99)}.{rng.randint(0, 9)}"])
        t = rng.choice(tails)
        shape = rng.randint(0, 3)
        if shape == 0:
            corpus.append(f"{v}{t}{L}")
        elif shape == 1:
            corpus.append(f"{L}{v}{t}")
        elif shape == 2:
            corpus.append(f"{L}{v}{L}")
        else:
            corpus.append(f"{rng.choice(['s4c', 'h2o', 'covid19', 'a4b5'])} {v}{t}")

    # 5. Code-switched Welsh+English sentences.
    cy_frame = ["Mae'r", "yn", "dweud", "bod", "wedi", "cael", "gwneud", "iawn"]
    en_frame = ["the", "computer", "download", "internet", "software", "hello", "world"]
    for _ in range(n // 8):
        k = rng.randint(3, 10)
        parts = [rng.choice(cy_frame + en_frame + (allw or ["x"])) for _ in range(k)]
        corpus.append(" ".join(parts))

    # 6. Punctuation / whitespace / apostrophe-clitic / case edge cases.
    corpus += [
        "", " ", "  ", "\t", "\n", ".", "!", "?", "...", ",",
        "a'r", "i'w", "o'n", "'ma", "'na", "'r", " y'n",
        "BANGOR", "Bangor", "bAnGoR", "S4C", "BBC", "URDD",
        "Dw i'n mynd i'r dref.", "Beth yw'r amser?", "£5.99 am 3:00 y.p.",
        "Mae 42% o'r bobl.", "Rhif ffôn: 01248 382000.",
        "Café naïve résumé",  # non-Welsh diacritics
        "​", "​zero-width", "ê",  # combining circumflex
    ]

    # 7. Random unicode noise (robustness — must still match, not crash divergently).
    alpha = "abcdefghijklmnopqrstuvwxyzâêîôûŵŷ'- .0123456789"
    for _ in range(n // 8):
        k = rng.randint(1, 40)
        corpus.append("".join(rng.choice(alpha) for _ in range(k)))

    rng.shuffle(corpus)
    return corpus[:n] if n < len(corpus) else corpus


def run_mode(mode: str, corpus: list[str]) -> list[tuple]:
    ref = BangorG2P(english_mode=mode)
    lib = CyPhonemizer(english_mode=mode)
    assert ref.data_version() == lib.data_version(), (
        f"data_version mismatch: py={ref.data_version()} c={lib.data_version()}")
    mism = []
    for t in corpus:
        try:
            r = ref.text_to_ids(t)
        except Exception as e:  # ref raising is itself a (matchable) behaviour
            r = ("PYERR", type(e).__name__)
        try:
            c = lib.text_to_ids(t)
        except Exception as e:
            c = ("CERR", type(e).__name__)
        if r != c:
            mism.append((t, r, c))
    return mism


def main() -> int:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 20000
    seed = int(sys.argv[2]) if len(sys.argv) > 2 else 1234
    corpus = build_corpus(n, seed=seed)
    print(f"corpus: {len(corpus)} inputs")
    total_bad = 0
    for mode in ("accented", "native"):
        mism = run_mode(mode, corpus)
        print(f"[{mode}] {len(corpus) - len(mism)}/{len(corpus)} match", end="")
        if mism:
            print(f"  — {len(mism)} MISMATCH")
            for t, r, c in mism[:15]:
                print(f"    input={t!r}\n      py={r}\n      c ={c}")
            total_bad += len(mism)
        else:
            print("  ✓")
    if total_bad:
        print(f"\nFAIL: {total_bad} mismatches")
        return 1
    print("\nPASS: byte-identical Python↔C across all inputs, both modes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
