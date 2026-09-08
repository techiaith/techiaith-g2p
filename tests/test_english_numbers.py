"""Number LANGUAGE: digits inside an English utterance read as English words (1.3.0).

Three layers, each pinned separately so a regression names its layer:
  * english_numbers -- the British English verbaliser (the conventions the owner agreed
    2026-09-07 are the docstring of that module; these tests are those examples);
  * WelshNormalizer.normalize(text, lang="en") -- the shared triggers writing English back,
    and the Welsh path byte-identical to what it was;
  * BangorG2P._number_lang -- which language a raw utterance's digits take, including the
    English function words the Welsh dictionary hides as loanword entries.
The C mirror is held to all of it by normalize_golden_en.tsv (test_norm) and the parity fuzz.
"""
import pytest

from techiaith.g2p import english_numbers as en
from techiaith.g2p.bangor_g2p import BangorG2P
from techiaith.g2p.welsh_normalize import WelshNormalizer


@pytest.fixture(scope="module")
def g2p():
    return BangorG2P(english_mode="native")


@pytest.fixture(scope="module")
def wn():
    return WelshNormalizer()


# --- the verbaliser -------------------------------------------------------------------------

@pytest.mark.parametrize("n, words", [
    (0, "zero"), (7, "seven"), (13, "thirteen"), (20, "twenty"), (21, "twenty one"),
    (100, "one hundred"), (101, "one hundred and one"), (123, "one hundred and twenty three"),
    (1000, "one thousand"), (1005, "one thousand and five"),
    (1234, "one thousand two hundred and thirty four"),
    (1_000_000, "one million"), (2_500_001, "two million five hundred thousand and one"),
    (-5, "minus five"),
    (999_999_999_999, "nine hundred and ninety nine billion nine hundred and ninety nine "
                      "million nine hundred and ninety nine thousand nine hundred and ninety nine"),
    (1_000_000_000_000, "one zero zero zero zero zero zero zero zero zero zero zero zero"),
])
def test_cardinal(n, words):
    assert en.cardinal(n) == words


@pytest.mark.parametrize("n, words", [
    (1, "first"), (2, "second"), (3, "third"), (4, "fourth"), (5, "fifth"), (8, "eighth"),
    (9, "ninth"), (11, "eleventh"), (12, "twelfth"), (13, "thirteenth"), (20, "twentieth"),
    (21, "twenty first"), (100, "one hundredth"), (112, "one hundred and twelfth"),
    (1000, "one thousandth"),
])
def test_ordinal(n, words):
    assert en.ordinal(n) == words


@pytest.mark.parametrize("y, words", [
    (2000, "two thousand"), (2005, "two thousand and five"), (2010, "twenty ten"),
    (2026, "twenty twenty six"), (1999, "nineteen ninety nine"), (1905, "nineteen oh five"),
    (1900, "nineteen hundred"), (1100, "eleven hundred"),
    (1066, "one thousand and sixty six"),      # below the band: a cardinal, by decision
    (26, "twenty six"),
])
def test_year(y, words):
    assert en.year(y) == words


def test_money_and_time_and_dates():
    assert en.pounds(250) == "two hundred and fifty pounds"
    assert en.pounds(1) == "one pound"
    assert en.pounds(5, 99) == "five pounds ninety nine"
    assert en.pounds(0, 50) == "fifty pence"
    assert en.pence(1) == "one penny"
    assert en.pence(99) == "ninety nine pence"
    assert en.time(3, 30, None) == "three thirty"
    assert en.time(3, 0, None) == "three o'clock"
    assert en.time(3, 5, None) == "three oh five"
    assert en.time(15, 30, None) == "fifteen thirty"
    assert en.time(3, 0, "pm") == "three o'clock p·m"
    assert en.time(9, 15, "a.m.") == "nine fifteen a·m"
    assert en.time(10, 0, "yb") == "ten o'clock a·m"
    assert en.date(31, 1) == "the thirty first of january"
    assert en.date(12, 3, 2026) == "the twelfth of march twenty twenty six"


def test_fractions_units_roman():
    assert en.fraction(1, 2) == "one half"
    assert en.fraction(3, 4) == "three quarters"
    assert en.fraction(2, 3) == "two thirds"
    assert en.fraction(3, 16) == "three sixteenths"
    assert en.fraction(7, 2) is None          # improper: left to the digit passes
    assert en.fraction(1, 25) is None         # no everyday name
    assert en.unit("5", "km") == "five kilometres"
    assert en.unit("1", "km") == "one kilometre"
    assert en.unit("2.5", "kg") == "two point five kilograms"
    assert en.roman(8, after_structural=False) == "the eighth"
    assert en.roman(4, after_structural=True) == "four"
    assert en.decimal(3, "5") == "three point five"
    assert en.percent(15) == "fifteen percent"
    assert en.spell_digits("0300 123") == "zero three zero zero one two three"


# --- the normaliser -------------------------------------------------------------------------

@pytest.mark.parametrize("text, expected", [
    ("Home screen 1 of 3", "home screen one of three"),
    ("Page 3", "page three"),
    ("123", "one hundred and twenty three"),
    ("1,234", "one thousand two hundred and thirty four"),
    ("In 2026 and 1999", "in twenty twenty six and nineteen ninety nine"),
    ("1500 people", "fifteen hundred people"),
    ("2,026", "two thousand and twenty six"),           # a comma says "amount", not year
    ("21st", "twenty first"), ("3rd", "third"), ("3Rd", "third"), ("100th", "one hundredth"),
    ("3RD", "tri r·d"),          # the acronym pass claims "RD" first, as it does "3YDD" in Welsh
    ("12 March 2026", "the twelfth of march twenty twenty six"),
    # abbreviated UI dates (2026-09-08: TalkBack read a widget's "Tue 8 Sept" as "tue eight sept")
    ("Tue 8 Sept", "tuesday the eighth of september"), ("Tue Sep 8", "tuesday the eighth of september"),
    ("Tuesday, September 8, 2026", "tuesday, the eighth of september twenty twenty six"),
    ("Sep 8", "the eighth of september"), ("Sat 12 Dec", "saturday the twelfth of december"),
    ("Tues 9 Sept", "tuesday the ninth of september"), ("Thurs 1 Aug", "thursday the first of august"),
    ("may 5 people", "may five people"),               # month-first needs title case: "may" is a verb
    ("sat on 8 Sept", "sat on the eighth of september"),   # a weekday abbreviation is title case too
    ("March 3rd", "the third of march"), ("Jan 1st", "the first of january"),
    ("8th Sept 2026", "the eighth of september twenty twenty six"), ("Sep 8:30", "sep eight thirty"),
    ("31/12/1999", "the thirty first of december nineteen ninety nine"),
    ("3:30pm", "three thirty p·m"), ("7.30pm", "seven thirty p·m"), ("11am", "eleven o'clock a·m"),
    ("15:30", "fifteen thirty"), ("00:00", "zero o'clock"),
    ("£5.99", "five pounds ninety nine"), ("£0.50", "fifty pence"), ("£1", "one pound"),
    ("£5m", "five million pounds"), ("£1k", "one thousand pounds"), ("50p", "fifty pence"),
    ("15%", "fifteen percent"), ("3.5", "three point five"),
    ("1/2", "one half"), ("3/4", "three quarters"), ("7/2", "seven two"),
    ("5km", "five kilometres"), ("2.5 kg", "two point five kilograms"),
    ("0300 123 4567", "zero three zero zero one two three four five six seven"),
    ("007", "zero zero seven"),
    ("Henry VIII", "henry the eighth"), ("Chapter IV", "chapter four"),
    ("5 + 3", "five plus three"), ("2 x 3", "two times three"), ("a=b", "a equals b"),
    ("20°C", "twenty degrees celsius"), ("45°", "forty five degrees"),
    ("Dr Smith", "doctor smith"), ("Mr and Mrs Jones", "mister and missus jones"),
    ("Tom & Jerry", "tom and jerry"),
    ("5 blynedd", "five blynedd"),                       # "N blynedd" is Welsh-only
])
def test_normalize_english(wn, text, expected):
    assert wn.normalize(text, lang="en") == expected


def test_normalize_welsh_path_is_the_default_and_unchanged(wn):
    for text in ("Tudalen 3 o 5", "12 Mawrth 2026", "£5.99", "3:30", "Henry VIII", "5 blynedd"):
        assert wn.normalize(text) == wn.normalize(text, lang="cy")
    assert wn.normalize("Tudalen 3 o 5") == "tudalen tri o pump"
    assert wn.normalize("£5.99") == "pum punt naw deg naw ceiniog"


def test_normalize_rejects_other_languages(wn):
    with pytest.raises(ValueError):
        wn.normalize("1", lang="fr")


# --- detection --------------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Home screen 1 of 3", "Tab 1 of 4", "Page 3", "Showing 2 of 10 items", "Battery at 45%",
    "3 items in your basket", "The meeting is at 3:30pm on 12 March 2026", "Chapter IV",
    "Older state pensioners set for automatic bonus from DWP", "You have 1 new notification",
])
def test_number_lang_english(g2p, text):
    assert g2p._number_lang(text) == "en"


@pytest.mark.parametrize("text", [
    "Mae 3 o'r plant yn yr ysgol", "Rhif 10", "Tudalen 3 o 5", "Am 3 o'r gloch", "Pennod IV",
    # ("Cost: £5.99" is spelled the same in both languages; the corpus prior reads it as English)
    "1 2 3",                    # no letters: no evidence, the voice's own language
    "Mae'r Bank of Wales yn 3 oed",   # an English name does not outvote the Welsh around it
    "Dyma'r internet café am 3",
    "Mae'r gwas yn is na'r to am 3",   # "was"/"is"/"to" are Welsh words here; the Welsh weight wins
    "Un taxi", "Y BBC", "c, a, th.",    # numeral + loan; article + acronym; a dictation of letters
])
def test_number_lang_welsh(g2p, text):
    assert g2p._number_lang(text) == "cy"



def test_text_to_ids_threads_the_language(g2p):
    """An explicit lang is the caller's word; None detects. The ids differ exactly when the
    number words do."""
    auto = g2p.text_to_ids("Page 3")
    assert auto == g2p.text_to_ids("Page 3", lang="en")
    assert auto != g2p.text_to_ids("Page 3", lang="cy")
    assert g2p.text_to_ids("Tudalen 3") == g2p.text_to_ids("Tudalen 3", lang="cy")


# --- sentence and clause boundaries (owner, 2026-09-07: "1 o 1. 1 of 1" came out English) ---

@pytest.mark.parametrize("text, expected", [
    ("1 o 1. 1 of 1", "un o un. one of one"),
    ("1 o 1, 1 of 1", "un o un, one of one"),                    # "o" is Welsh evidence
    ("Tudalen 1 o 3, Page 1 of 3", "tudalen un o tri, page one of three"),
    ("Croeso - Welcome, 1 o 3 – 1 of 3", "croeso, welcome, un o tri, one of three"),   # dashes are comma pauses
    ("Battery. 45%.", "battery. forty five percent."),           # no evidence: carries forward
    ("Page 3. Tudalen 3.", "page three. tudalen tri."),
    ("e.e. 3 peth. 2 things", "er enghraifft tri peth. two things"),   # "e.e." is not an end
    ("Dr. Jones has 3 cats. Mae 2 gath.", "doctor jones has three cats. mae dau gath."),
    ("Project information\n1 Commit\n0 Tags", "project information one commit zero tags"),
    ("It's 3 o'clock", "it's three o'clock"), ("3 o'clock", "three o'clock"),   # "o'" is not Welsh
    ("Mae 3 o'r plant yn yr ysgol", "mae tri o'r plant yn yr ysgol"),
    ("Home screen 1 of 3", "home screen one of three"),
    ("Battery, 45%", "battery, forty five percent"),             # English sentence with a comma: one span
])
def test_number_language_per_sentence(g2p, text, expected):
    assert g2p.normalize(text) == expected


def test_single_language_text_is_one_pass(g2p, wn):
    """When every span agrees the whole text is normalised once, so a Welsh utterance is
    byte-identical to WelshNormalizer.normalize(text) whatever its punctuation."""
    for text in ("Rhif 1, Rhif 2. Tudalen 3!", "Mae 3 o'r plant yn yr ysgol. Am 3:30.", "1, 1"):
        assert g2p.normalize(text) == wn.normalize(text)
    assert g2p.normalize("1, 1") == "un, un"                      # the comma is a pause, not "1,1"
    assert wn.normalize("£5, os gwelwch yn dda") == "pum punt, os gwelwch yn dda"


def test_c_auto_normalisation_matches_python_per_span(g2p):
    """cyp_normalize_auto is what cyp_text_to_ids feeds the phonemizer: the per-sentence /
    per-clause number language, the carry-forward and the joins. It must equal
    BangorG2P.normalize(text) as TEXT, not only as ids, so a divergence names the span."""
    import ctypes
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    so = repo / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
    if not so.exists():
        pytest.skip("libcy_phonemize.so not built (make -C techiaith/g2p/c libcy_phonemize.so)")
    lib = ctypes.CDLL(str(so))
    lib.cyp_create.restype = ctypes.c_void_p
    lib.cyp_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.cyp_normalize_auto.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    h = lib.cyp_create(str(repo / "techiaith" / "g2p").encode(), b"native")
    assert h, "cyp_create failed"
    cases = ["1 o 1. 1 of 1", "1 o 1, 1 of 1", "Tudalen 1 o 3, Page 1 of 3", "Battery. 45%.",
             "Page 3. Tudalen 3.", "e.e. 3 peth. 2 things", "Dr. Jones has 3 cats. Mae 2 gath.",
             "Croeso - Welcome, 1 o 3 – 1 of 3", "Project information\n1 Commit\n0 Tags",
             "It's 3 o'clock", "Mae'r 3 yma. Page 3 here!", "Rhif 1; Number 1: 2 things",
             "y.b. 3. 4 items", "U.S.A. 3 things. Mae 2 beth", "Mae 3 o'r plant. Show 3 of 4.",
             "Home screen 1 of 3", "Rhif 1, Rhif 2", "1, 1", "", "...", "3", "1 o 1.\r\n1 of 1"]
    for text in cases:
        buf = ctypes.create_string_buffer(65536)
        lib.cyp_normalize_auto(h, text.encode("utf-8"), buf, 65536)
        assert buf.value.decode("utf-8") == g2p.normalize(text), f"AUTO normalisation diverges on {text!r}"


# --- phone routing per sentence (owner, 2026-09-08) --------------------------------------------

def test_phone_routing_per_sentence(g2p):
    """An English sentence followed by a Welsh one gets each sentence's own phones."""
    segs = g2p.segments("1 of 1. 1 o 1")
    assert [s.phone_lang for s in segs] == ["en", "cy"]
    assert segs[0].tokens == g2p.phonemize("one of one.", on_oov="lts", lang="en")
    assert segs[1].tokens == g2p.phonemize("un o un", on_oov="lts", lang="cy")
    assert "y" in segs[1].tokens and "ʌ" in segs[0].tokens        # Welsh /y/ in "un", English /ʌ/ in "one"
    # a lowercase continuation after the stop is NOT a sentence end ("learn more. link")
    assert len(g2p.segments("one of one. un o un")) == 1


def test_techiaith_is_welsh_in_any_context(g2p):
    welsh = ["ˈ", "t", "e", "x", "|", "j", "ai", "th"]
    for text in ("Techiaith TTS", "Google Lens button double tap to activate. Techiaith TTS",
                 "Techiaith TTS, button, double tap to activate", "Open the Techiaith app now please"):
        toks = g2p.phonemize(g2p.normalize(text), on_oov="lts")
        assert any(toks[i:i + 8] == welsh for i in range(len(toks))), (text, toks)


def test_single_language_text_routes_in_one_pass(g2p):
    """Every sentence agreeing means one pass with that language: byte-identical to an explicit
    lang, whatever the number of sentences."""
    for text, lang in (("Mae'r tywydd yn braf. Mae'r haul yn gwenu. Dewch allan.", "cy"),
                       ("The weather is fine today. The sun is shining. Come outside.", "en"),
                       ("Dw i'n mynd i'r dref.", "cy")):
        assert g2p.phonemize(text, on_oov="lts") == g2p.phonemize(text, on_oov="lts", lang=lang)


def test_no_evidence_sentence_inherits_the_utterance(g2p):
    """"I agree." alone would route Welsh (no English bar); inside an English utterance it
    inherits English, so "i" is the pronoun, not the Welsh preposition."""
    toks = g2p.phonemize("The weather is fine today and the sun is out. I agree.", on_oov="lts")
    assert toks == g2p.phonemize("The weather is fine today and the sun is out. I agree.", on_oov="lts", lang="en")


def test_c_ids_match_python_across_sentence_routing(g2p):
    import ctypes
    from pathlib import Path
    repo = Path(__file__).resolve().parent.parent
    so = repo / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
    if not so.exists():
        pytest.skip("libcy_phonemize.so not built")
    lib = ctypes.CDLL(str(so))
    lib.cyp_create.restype = ctypes.c_void_p
    lib.cyp_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.cyp_text_to_ids.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int32), ctypes.c_int]
    h = lib.cyp_create(str(repo / "techiaith" / "g2p").encode(), b"native")
    for text in ("1 of 1. 1 o 1", "1 o 1. 1 of 1", "Google Lens button double tap to activate. Techiaith TTS",
                 "Mae'r tywydd yn braf. The weather is fine.", "The weather is fine today and the sun is out. I agree.",
                 "Iawn. OK. Da. Fine.", "Croeso - Welcome, 1 o 3 – 1 of 3. Diolch.", "Settings\nGeneral\nAbout phone"):
        buf = (ctypes.c_int32 * 8192)()
        n = lib.cyp_text_to_ids(h, text.encode("utf-8"), buf, 8192)
        assert list(buf[:n]) == g2p.text_to_ids(text), text


def test_live_as_a_label_is_the_adjective(g2p):
    """VoiceOver's "Live Recognition" was /lɪv/: a capitalised label-initial "Live" is tagged PROPN,
    which the heteronym table did not map. PROPN and ADV take the adjective reading; verbs keep /lɪv/."""
    def live(text):
        toks = g2p.phonemize(g2p.normalize(text), on_oov="lts")
        i = toks.index("l"); return toks[i:i + 4]
    for text in ("Live Recognition", "Live Text", "Live Photos", "live music", "Go live", "Live Recognition, button",
                 "to start Live Recognition or use the Live Recognition Rotor", "there is live music tonight"):
        assert live(text) == ["l", "ˈ", "ai", "v"], text
    for text in ("I live in Bangor", "They live here", "We live and learn"):
        assert live(text) == ["l", "ˈ", "i", "v"], text
