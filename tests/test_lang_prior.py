"""The per-word language prior (data/lang/lang_prior.tsv) and the routing built on it (1.4.0).

Owner, 2026-09-08: "Learn more" read "mor-eh" on the phones and the API alike -- "more" is a loan in
the Welsh dictionary and one English-only word did not meet the old two-word bar. The prior scores
every word by its frequency in Welsh versus English text; a sentence's language is the sign of the
sum. These tests pin the table's shape, the decisions on the labels that were wrong, the Welsh that
must not move, and the C mirror.
"""
import ctypes
from pathlib import Path

import pytest

from techiaith.g2p.bangor_g2p import BangorG2P, _PRIOR_MIN, _PRIOR_STRONG

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def g2p():
    return BangorG2P(english_mode="native")


def test_table_shape_and_key_weights(g2p):
    t = g2p.lang_prior
    assert 30_000 < len(t) < 60_000
    assert all(-64 <= v <= 64 and v != 0 for v in t.values())
    for w in ("yn", "mae", "mae'r", "y", "o", "un", "wedi", "ei"):          # Welsh
        assert t[w] >= _PRIOR_STRONG, (w, t[w])
    for w in ("the", "of", "it", "more", "now", "all", "learn", "o'clock"):  # English
        assert t[w] <= -_PRIOR_STRONG, (w, t[w])
    assert abs(t["taxi"]) < _PRIOR_STRONG                                   # a loan in both


def test_letters_are_not_words(g2p):
    """Letter names carry no language ("B.", "c, a, th."); only Welsh "o" and "y" are words."""
    for w in ("b", "c", "k", "u", "z", "th", "a", "i"):
        assert g2p._word_weight(w) == 0, w
    assert g2p._word_weight("o") >= _PRIOR_STRONG and g2p._word_weight("y") >= _PRIOR_STRONG
    assert g2p._lang_score(["c", "a", "th"]) == 0


def test_fallback_is_dictionary_exclusivity(g2p):
    assert g2p._word_weight("zzqx") == 0                 # in neither corpus nor either dictionary
    # exclusivity is ADDED to a corpus weight (2026-09-08): "unread" carried +7 from a single
    # Welsh tweet and made a notification banner Welsh; the English lexicon outvotes the noise
    assert g2p._word_weight("unread") < 0
    assert g2p._sentence_lang(g2p._routing_words("2 unread messages")) == "en"
    assert g2p.segments("2 unread messages")[0].text == "two unread messages"
    assert g2p._word_weight("techiaith") > 0             # the Welsh corpus knows the organisation
    assert g2p._word_weight("cardiff") < 0               # English dictionary only
    assert g2p._word_weight("gorffennaf") > 0            # Welsh dictionary only


@pytest.mark.parametrize("label", [
    "Learn more", "Read more", "See all", "Show more", "Log in", "Log out", "More options",
    "Turn on", "Turn off", "Not now", "Got it", "Back", "Next", "Done", "Home screen 1 of 3",
    "Google Lens button double tap to activate", "I agree", "One of one",
])
def test_english_labels_route_english(g2p, label):
    assert g2p._sentence_lang(g2p._routing_words(g2p.normalize(label))) == "en", label


@pytest.mark.parametrize("label", [
    "Cau ffenestr", "Agor dewislen", "Anfon neges", "Gosodiadau sain", "Yn ôl", "Nesaf", "Dewis iaith",
    "Y BBC", "Pris y taxi", "Un taxi", "Y taxi", "Mae'r bws yn hwyr", "Dangos mwy", "Darllen mwy",
    "Rhagor o wybodaeth", "Techiaith TTS", "c, a, th.", "B.", "Un o un", "Tudalen 1 o 3", "Iawn", "Cadw",
])
def test_welsh_labels_route_welsh(g2p, label):
    assert g2p._sentence_lang(g2p._routing_words(g2p.normalize(label))) == "cy", label


def test_learn_more_speaks_english_phones(g2p):
    toks = g2p.phonemize(g2p.normalize("Learn more"), on_oov="lts")
    assert toks == g2p.phonemize("learn more", on_oov="lts", lang="en")
    assert "oo" in toks and "ɹ" in toks                  # English "more", not Welsh "mo-re"


def test_weak_evidence_is_no_decision(g2p):
    """|score| below half a nat must not flip: "ab" alone is -22 (decided); a word both lexicons
    hold with a near-zero corpus weight is not. ("Cancel" used to be the example at +7; with
    lexicon exclusivity added it is now a decided English word, as a screen reader needs.)"""
    weak = [w for w, v in g2p.lang_prior.items() if 0 < abs(v) < _PRIOR_MIN and w.isalpha()
            and g2p.lexicon.lookup_welsh(w) is not None and g2p.english.lookup(w) is not None]
    assert weak, "no weak both-lexicon word in the table"
    for w in weak[:5]:
        assert g2p._word_weight(w) == g2p.lang_prior[w], w
        assert g2p._sentence_lang([w]) == "cy", w        # no decision -> the default
    assert g2p._sentence_lang(["cancel"]) == "en"
    assert g2p._number_lang("Cancel 3") == "en"


def test_c_routing_matches_python_on_labels(g2p):
    so = REPO / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
    if not so.exists():
        pytest.skip("libcy_phonemize.so not built")
    lib = ctypes.CDLL(str(so))
    lib.cyp_create.restype = ctypes.c_void_p
    lib.cyp_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.cyp_text_to_ids.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int32), ctypes.c_int]
    h = lib.cyp_create(str(REPO / "techiaith" / "g2p").encode(), b"native")
    assert h
    for text in ("Learn more", "Un taxi", "c, a, th.", "B.", "Y BBC", "a BBC", "Got it", "Cancel",
                 "1 of 1. 1 o 1", "Techiaith TTS", "ab·cd", "Mae'r Bank of Wales yn 3 oed",
                 "The meeting is at 3:30pm on 12 March 2026. Mae 2 gath gan Siân."):
        buf = (ctypes.c_int32 * 8192)()
        n = lib.cyp_text_to_ids(h, text.encode("utf-8"), buf, 8192)
        assert list(buf[:n]) == g2p.text_to_ids(text), text
