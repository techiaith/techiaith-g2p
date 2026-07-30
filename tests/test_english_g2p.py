"""Native English G2P (CMUdict lexicon + fold + OOV LTS) — Workstream P bilingual."""
import sys

from techiaith.g2p.english_g2p import EnglishG2P

# Native English (from CMUdict) — the reserved English phones appear (ɹ, @r, etc.)
NATIVE = {
    "cardiff": ["k", "ˈ", "aa", "ɹ", "d", "i", "f"],
    "the": ["dh", "@"],
    "water": ["w", "ˈ", "oo", "t", "@r"],
    "nation": ["n", "ˈ", "ei", "sh", "@", "n"],
}


def test_native_lookup():
    g = EnglishG2P()
    bad = {w: (exp, g.phonemize(w, native=True)) for w, exp in NATIVE.items()
           if g.phonemize(w, native=True) != exp}
    assert not bad, f"native mismatches: {bad}"


def test_fold_removes_english_phones():
    g = EnglishG2P()
    # folded output for the current Welsh-only model must contain no reserved English phones
    english_phones = {"æ", "ʌ", "ɒ", "ɪə", "eə", "ʊə", "ɹ"}
    for w in ["cardiff", "cat", "cup", "hobby", "rabbit"]:
        folded = g.phonemize(w, native=False)
        assert not (set(folded) & english_phones), f"{w}: fold leaked {set(folded) & english_phones}"
        # ɹ must have folded to Welsh r
        native = g.phonemize(w, native=True)
        if "ɹ" in native:
            assert "r" in folded


def test_oov_uses_lts():
    g = EnglishG2P()
    nonce = "zworbtastic"
    assert g.lookup(nonce) is None
    toks = g.phonemize(nonce, native=True)   # must not raise, must produce tokens
    assert toks and all(isinstance(t, str) for t in toks)


def test_bangor_native_mode_routes_english():
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    # English word -> native English tokens (via the CMUdict lexicon)
    assert g.phonemize("computer", on_oov="lts") == g.english.phonemize("computer", native=True)
    # a Welsh word still goes through the Welsh path (no English phones)
    cy = g.phonemize("cymraeg", on_oov="lts")
    assert cy and "ɹ" not in cy


def test_bangor_accented_default_unchanged():
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P()  # default accented mode
    # English words resolve via the Bangor Welsh-accented tables (unchanged behaviour)
    assert g.phonemize("computer") == g.lexicon.lookup("computer")


def _run():
    g = EnglishG2P()
    fails = [(w, e, g.phonemize(w, native=True)) for w, e in NATIVE.items()
             if g.phonemize(w, native=True) != e]
    return fails


if __name__ == "__main__":
    fails = _run()
    print(f"{len(NATIVE) - len(fails)}/{len(NATIVE)} native lookups pass")
    for w, e, g_ in fails:
        print(f"  FAIL {w!r}: want {e} got {g_}")
    sys.exit(1 if fails else 0)
