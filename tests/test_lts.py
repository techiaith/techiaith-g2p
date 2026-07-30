"""Tests for the rule-based Welsh LTS / OOV grapheme->phone (Workstream P, P3).

Expected token sequences are taken verbatim from the Bangor dictionary
(the oracle). RED until techiaith/g2p/bangor_lts.py exists.
"""
import sys

from techiaith.g2p.bangor_lts import lts

# word -> expected tokens (stress ˈ, syllable |) — from bangordict.dict
CASES = {
    "cath": ["ˈ", "k", "aa", "th"],
    "nos": ["ˈ", "n", "oo", "s"],
    "coch": ["ˈ", "k", "oo", "x"],
    "ci": ["ˈ", "k", "ii"],
    "du": ["ˈ", "d", "yy"],
    "tân": ["ˈ", "t", "aa", "n"],
    "môr": ["ˈ", "m", "oo", "r"],
    "plant": ["ˈ", "p", "l", "a", "n", "t"],
    "siop": ["ˈ", "sh", "o", "p"],
    "haf": ["ˈ", "hh", "aa", "v"],
    "tref": ["ˈ", "t", "r", "ee", "v"],
    "llaw": ["ˈ", "lh", "au"],
    "gwyn": ["ˈ", "g", "uy", "n"],
    "iaith": ["ˈ", "j", "ai", "th"],
    "afal": ["ˈ", "aa", "|", "v", "a", "l"],
    "cadair": ["ˈ", "k", "aa", "|", "d", "ai", "r"],
    "ceffyl": ["ˈ", "k", "ee", "|", "f", "y", "l"],
    "mynydd": ["ˈ", "m", "@", "|", "n", "y", "dh"],
}


def test_lts_curated():
    bad = {w: (exp, lts(w)) for w, exp in CASES.items() if lts(w) != exp}
    assert not bad, "LTS mismatches:\n" + "\n".join(
        f"  {w!r}: want {e} got {g}" for w, (e, g) in bad.items()
    )


def test_g2p_oov_uses_lts():
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P()
    nonce = "sgrwtlaniog"
    assert g.lexicon.lookup(nonce) is None, "nonce unexpectedly in lexicon; pick another"
    assert g.phonemize(nonce, on_oov="lts") == lts(nonce)
    ids = g.text_to_ids(nonce)   # default path must not raise on OOV
    assert ids[0] == g.control["bos"] and ids[-1] == g.control["eos"]


def _run():
    fails = [(w, e, lts(w)) for w, e in CASES.items() if lts(w) != e]
    return fails


if __name__ == "__main__":
    fails = _run()
    print(f"{len(CASES) - len(fails)}/{len(CASES)} pass")
    for w, e, g in fails:
        print(f"  FAIL {w!r}: want {e} got {g}")
    sys.exit(1 if fails else 0)
