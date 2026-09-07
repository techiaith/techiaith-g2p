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
    "Cost: £5.99",
    "1 2 3",                    # no letters: no evidence, the voice's own language
    "Mae'r Bank of Wales yn 3 oed",   # an English name does not outvote the Welsh around it
    "Dyma'r internet café am 3",
    "Mae'r gwas yn is na'r to am 3",   # "was"/"is"/"to" are Welsh words, not evidence
])
def test_number_lang_welsh(g2p, text):
    assert g2p._number_lang(text) == "cy"


def test_function_words_are_not_welsh_words(g2p):
    """The list exists because these are hidden as loans in bangordict.dict; none may be a
    real Welsh word, and the known Welsh homographs must stay out of it."""
    from techiaith.g2p.bangor_g2p import _EN_FUNCTION_WORDS
    for w in ("at", "is", "to", "was", "her", "be", "can", "had", "call", "an", "all", "or"):
        assert w not in _EN_FUNCTION_WORDS
    for w in ("the", "of", "for", "it", "not", "and", "in", "on"):
        assert w in _EN_FUNCTION_WORDS


def test_text_to_ids_threads_the_language(g2p):
    """An explicit lang is the caller's word; None detects. The ids differ exactly when the
    number words do."""
    auto = g2p.text_to_ids("Page 3")
    assert auto == g2p.text_to_ids("Page 3", lang="en")
    assert auto != g2p.text_to_ids("Page 3", lang="cy")
    assert g2p.text_to_ids("Tudalen 3") == g2p.text_to_ids("Tudalen 3", lang="cy")
