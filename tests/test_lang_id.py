"""Word-level Welsh/English classification for bilingual routing (P-bilingual)."""
import sys

from techiaith.g2p.lang_id import classify_word

CY = ["llan", "mynydd", "rhaglen", "ffordd", "gwyrdd", "dŵr", "ysgol", "cymraeg", "yn", "yr"]
# orthographically-cued English words (no-cue words like "computer" are routed by
# dictionary lookup in the G2P, not by this heuristic).
EN = ["keyboard", "zebra", "vision", "extra", "quick", "action", "knock", "the", "and", "taxi"]


def test_welsh_words():
    bad = [w for w in CY if classify_word(w) != "cy"]
    assert not bad, f"classified as non-cy: {bad}"


def test_english_words():
    bad = [w for w in EN if classify_word(w) != "en"]
    assert not bad, f"classified as non-en: {bad}"


def _run():
    fails = [(w, "cy", classify_word(w)) for w in CY if classify_word(w) != "cy"]
    fails += [(w, "en", classify_word(w)) for w in EN if classify_word(w) != "en"]
    return fails


if __name__ == "__main__":
    fails = _run()
    print(f"{len(CY) + len(EN) - len(fails)}/{len(CY) + len(EN)} pass")
    for w, e, g in fails:
        print(f"  FAIL {w!r}: want {e} got {g}")
    sys.exit(1 if fails else 0)
