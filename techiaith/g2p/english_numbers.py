"""British English verbalisation of numbers and number-bearing constructs.

The Welsh normaliser (welsh_normalize.py) owns the TRIGGERS -- which spans of text are a
time, a date, a price, a percentage -- and calls these functions when the utterance's
number language is English. Every function here is integer arithmetic over a small word
table, no locale, no dependencies, so that techiaith/g2p/c/cy_normalize.c can mirror it
byte for byte; tests/diff_fuzz_c_parity.py proves it does.

Conventions, agreed with the owner 2026-09-07 (British English, screen-reader register):
  123        one hundred and twenty three        ("and" after hundreds; tens+units as two
                                                  words -- same phones as the hyphenated
                                                  spelling, and both lexicon entries exist)
  2026       twenty twenty six                   (bare 1100-2099 read as a year; 2000 is
  2005       two thousand and five                "two thousand"; 1905 is "nineteen oh five".
                                                  Below 1100 stays a cardinal: "1050 people"
                                                  must not become "ten fifty people", so 1066
                                                  is "one thousand and sixty six" -- accepted.)
  31 January the thirty first of january
  3:30 / 3:00 / 3:05 / 15:30   three thirty / three o'clock / three oh five / fifteen thirty
  3pm        three p·m                           (letters, via the acronym join)
  £250 / £5.99 / 50p          two hundred and fifty pounds / five pounds ninety nine / fifty pence
  15%        fifteen percent
  0300 123 4567               digits individually, "zero"
  3.5        three point five
  1/2, 3/4   one half, three quarters
Output is lowercase; the normaliser lowercases everything at the end anyway.
"""
from __future__ import annotations

from typing import Optional

ACRONYM_JOIN = "·"   # keep in step with welsh_normalize.ACRONYM_JOIN

_ONES = ["zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
         "ten", "eleven", "twelve", "thirteen", "fourteen", "fifteen", "sixteen",
         "seventeen", "eighteen", "nineteen"]
_TENS = ["", "", "twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_SCALES = [(1_000_000_000, "billion"), (1_000_000, "million"), (1_000, "thousand")]
_ORDINAL_IRREGULAR = {
    "one": "first", "two": "second", "three": "third", "five": "fifth", "eight": "eighth",
    "nine": "ninth", "twelve": "twelfth",
}
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
UNITS = {   # abbreviation -> (singular, plural); same key set as welsh_normalize._UNITS_SPOKEN
    "km": ("kilometre", "kilometres"), "kg": ("kilogram", "kilograms"),
    "cm": ("centimetre", "centimetres"), "mm": ("millimetre", "millimetres"),
    "m": ("metre", "metres"), "g": ("gram", "grams"), "l": ("litre", "litres"),
}
# Words after which a Roman numeral is a plain count, not a regnal ordinal: "chapter IV"
# is "chapter four", "Henry IV" is "henry the fourth". Mirrors _ROMAN_STRUCTURAL's role.
ROMAN_STRUCTURAL = frozenset({"chapter", "part", "section", "volume", "book", "act",
                              "scene", "page", "article", "phase", "stage", "level",
                              "class", "type", "grade", "world", "war", "mark", "version"})


def _below_thousand(n: int) -> str:
    """0 < n < 1000, with the British 'and' between hundreds and the remainder."""
    if n < 20:
        return _ONES[n]
    if n < 100:
        t, u = divmod(n, 10)
        return _TENS[t] + (" " + _ONES[u] if u else "")
    h, r = divmod(n, 100)
    return _ONES[h] + " hundred" + (" and " + _below_thousand(r) if r else "")


def cardinal(n: int) -> str:
    """Scale words up to 999,999,999,999; beyond that the digits are read one by one, the
    same floor welsh_normalize uses for absurd runs, so no input can raise here."""
    if n < 0:
        return "minus " + cardinal(-n)
    if n == 0:
        return "zero"
    if n > 999_999_999_999:
        return spell_digits(str(n))
    parts = []
    for scale, name in _SCALES:
        g, n = divmod(n, scale)
        if g:
            parts.append(_below_thousand(g) + " " + name)
    if n:
        # "one thousand AND five" but "one thousand two hundred and thirty four": the
        # remainder takes a leading "and" only when it has no hundreds of its own.
        parts.append(("and " if parts and n < 100 else "") + _below_thousand(n))
    return " ".join(parts)


def ordinal(n: int) -> str:
    words = cardinal(n).split(" ")
    last = words[-1]
    if last in _ORDINAL_IRREGULAR:
        words[-1] = _ORDINAL_IRREGULAR[last]
    elif last.endswith("ty"):
        words[-1] = last[:-1] + "ieth"        # twenty -> twentieth
    else:
        words[-1] = last + "th"               # four -> fourth, hundred -> hundredth
    return " ".join(words)


def year(y: int) -> str:
    """The spoken-year register for 1100..2099; anything else is a plain cardinal."""
    if 2000 <= y <= 2099:
        r = y - 2000
        if r == 0:
            return "two thousand"
        if r < 10:
            return "two thousand and " + _ONES[r]
        return "twenty " + _below_thousand(r)
    if 1100 <= y <= 1999:
        hh, tt = divmod(y, 100)
        if tt == 0:
            return _below_thousand(hh) + " hundred"
        if tt < 10:
            return _below_thousand(hh) + " oh " + _ONES[tt]
        return _below_thousand(hh) + " " + _below_thousand(tt)
    return cardinal(y)


def spell_digits(digits: str) -> str:
    """Each digit its own word; non-digit characters in the run are dropped."""
    return " ".join(_ONES[ord(c) - 48] for c in digits if "0" <= c <= "9")


def decimal(whole: int, frac_digits: str) -> str:
    return cardinal(whole) + " point " + spell_digits(frac_digits)


def percent(n: int) -> str:
    return cardinal(n) + " percent"


def pounds(amount: int, pence_part: Optional[int] = None) -> str:
    """£amount[.pence]. £0.50 is 'fifty pence'; £1 is 'one pound'; £5.99 is
    'five pounds ninety nine' (no 'and', no 'pence' -- the everyday spoken form)."""
    if amount == 0 and pence_part:
        return pence(pence_part)
    out = cardinal(amount) + (" pound" if amount == 1 else " pounds")
    if pence_part:
        out += " " + cardinal(pence_part)
    return out


def pence(p: int) -> str:
    return "one penny" if p == 1 else cardinal(p) + " pence"


def time(h: int, mm: int, marker: Optional[str]) -> str:
    """hh:mm[ marker]. The hour is read as written (15:30 -> fifteen thirty), minutes
    00 -> o'clock, 01-09 -> 'oh N'. am/pm (and the Welsh yb/yh/yp) become letter names
    through the acronym join so the lexicon cannot read 'am' as the verb."""
    if mm == 0:
        core = cardinal(h) + " o'clock"
    elif mm < 10:
        core = cardinal(h) + " oh " + _ONES[mm]
    else:
        core = cardinal(h) + " " + _below_thousand(mm)
    if not marker:
        return core
    k = marker.lower().replace(".", "")
    suffix = "a" + ACRONYM_JOIN + "m" if k in ("am", "yb") else "p" + ACRONYM_JOIN + "m"
    return core + " " + suffix


def date(d: int, m: int, y: Optional[int] = None) -> str:
    out = "the " + ordinal(d) + " of " + MONTHS[m - 1]
    if y is not None:
        out += " " + year(y)
    return out


def fraction(num: int, den: int) -> Optional[str]:
    """Proper fractions with the everyday names; None means 'leave it to the digit passes'."""
    if den == 0 or num >= den:
        return None
    if den == 2:
        return "one half" if num == 1 else cardinal(num) + " halves"
    if den == 4:
        return {1: "one quarter", 3: "three quarters"}.get(num, cardinal(num) + " quarters")
    if den > 20:
        return None
    return cardinal(num) + " " + ordinal(den) + ("" if num == 1 else "s")


def unit(raw: str, abbrev: str) -> str:
    """'5km', '2.5 kg'. Singular only for exactly 1."""
    singular, plural = UNITS[abbrev]
    if "." in raw:
        whole, frac = raw.split(".", 1)
        return decimal(int(whole), frac) + " " + plural
    n = int(raw)
    return cardinal(n) + " " + (singular if n == 1 else plural)


def roman(value: int, after_structural: bool) -> str:
    """'Henry VIII' -> henry the eighth; 'Chapter IV' -> chapter four."""
    if after_structural or value > 31:
        return cardinal(value)
    return "the " + ordinal(value)
