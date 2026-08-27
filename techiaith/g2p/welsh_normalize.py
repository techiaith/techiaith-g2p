"""Welsh text normalization / L1 verbalizer (Workstream P, task P2).

Turns raw text (numbers, symbols, abbreviations, acronyms) into spoken Welsh
words that the G2P (dictionary lookup + OOV) can pronounce.

SCOPE (v1, this module): cardinals 0-999,999,999 (decimal register), integers with
thousands separators, decimals ("pwynt"), percent ("y cant"), the "&" conjunction,
a common-abbreviation table, and acronym spell-out via Welsh letter names.

DEFERRED pending techiaith convention sign-off (see docs/NORMALIZATION.md): the
"a/ac" natural-conjunction register, ordinals, dates, currency mutations, and the
extended symbol set. All the verified reference data for those is recorded in
docs/NORMALIZATION.md so they can be added without re-researching. Times are
implemented (idiomatic clock, decided 2026-07-26) but the individual hour/minute
words beyond the verified core are themselves derived and pending sign-off --
see docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md §5.

Cardinal forms are the VERIFIED reference values (decimal, standalone/masculine).
"""
from __future__ import annotations

import re
from pathlib import Path

from .canonical import decimal_value

# --- what counts as a DIGIT in the digit-run and cardinal passes ------------------------
#
# `[0-9]`, written out, not `\d`, and not `str.isdigit()`. Two separate reasons, and both
# are about these passes agreeing with the C port by construction rather than by luck.
#
# 1. `\d` and `str.isdigit()` read the HOST interpreter's Unicode tables. That is the class
#    of drift canonical.py exists to remove, and it is live: '𞓰' (Nag Mundari zero) is a
#    digit on 3.14/Unicode 16 and not on the canonical 3.10/Unicode 13.
# 2. cy_normalize.c's number passes are BYTE-oriented -- every digit test in them is
#    `isdigit()` on one byte, i.e. ASCII. So ASCII is the digit class the two
#    implementations can actually agree on here.
#
# What went wrong when they disagreed: `_DIGIT_SEQ`'s `0\d+` claimed "0٣٣" (Arabic-Indic
# threes, decimal digits under every Unicode version), `_spell_digits` then indexed
# `_DIGIT_NAMES['٣']` and the whole call RAISED KeyError -- on the canonical interpreter,
# on ordinary mixed text. Before the trailing `\b` became `(?!\d)` the pattern rejected
# those inputs and `_INTEGER` read them as a cardinal (`int("0٣٣")` is 33, "tri deg tri"),
# which did not crash but diverged from C, which reads the ASCII "0" and drops the rest.
#
# `_PHONE`, `_DIGIT_SEQ` and `_INTEGER` all use it, which is what makes the fix hold: those
# three are the whole fall-through chain for a bare digit run, so narrowing one and not the
# others would only move the disagreement along the chain. "0٣٣x" now reads "sero" and
# leaves the Arabic-Indic digits alone -- exactly what C does with them, verified at the id
# level. No new Welsh words were needed and none were invented: a digit this module cannot
# pair with an owner-approved word is a digit it does not claim.
#
# SCOPE, stated plainly. The SPECIALISED number patterns (`_DECIMAL`, `_CURRENCY`,
# `_PERCENT`, `_DATE_*`, `_TIME`, `_FRACTION`, `_UNIT`, `_PENCE`, `_ORDINAL_RE`, `_AGE`, the
# math-operator lookarounds) still say `\d` and so still diverge from C on a non-ASCII
# decimal digit -- measured, and divergent on `main` too: "٣.٣", "£٣", "٣%",
# "٣ Ionawr 2020". None of them crashes; each is the same one-line narrowing as here, and
# they are recorded together in docs/FOLLOWUPS.md SS G rather than swept in with a crash fix.
#
# DELIBERATELY NOT the same class as the SPELL-OUT path. `bangor_g2p.letter_tokens` handles
# every Unicode-13 decimal digit -- '٣' spells "tri" -- and C matches it there, because
# `cyp__cp_decimal_value` decodes codepoints and mirrors `canonical.decimal_value` entry for
# entry (tests/test_ssml_primitives.py walks all 0x110000 of them to prove it). The
# normaliser cannot borrow that wider class until the C passes decode UTF-8 too.
_D = "[0-9]"


def _norm_digit_value(ch: str) -> int:
    """The digit VALUE of `ch` in this module's digit class, or -1 -- see `_D` above.

    Layered on `canonical.decimal_value()` so the vendored Unicode-13 table stays the one
    definition of a decimal digit in this repo and this narrowing can never drift out from
    under it: the value comes from the table, the `ord(ch) < 0x80` test is the documented
    narrowing to what cy_normalize.c's byte-oriented passes can see.
    """
    v = decimal_value(ch)
    return v if v >= 0 and ord(ch) < 0x80 else -1


# EXACTLY the character classes the C port accepts, not Python's \w or str.isalpha().
# Using \w here would be idiomatic and would also introduce a fresh Python/C divergence
# on the first non-Latin input ("α/β" -> "α β" in Python, unchanged in C), since
# cp_is_word is Latin-only. That gap is real and already disclosed elsewhere, but there
# is no reason to add a NEW instance of it when the C domain is small enough to mirror
# outright. Ranges, from cy_normalize.c: C0-FF minus x00D7 and x00F7, Latin Extended-A/B
# and Additional. One shared constant feeds both classes so they can never drift apart:
#   _C_WORD_CLASS   mirrors cp_is_word            (ASCII alnum + "_" + the ranges)
#   _C_LETTER_CLASS mirrors cyp__cp_is_alpha + _  (ASCII alpha + "_" + the ranges --
#                   the class digit_seq_sep tests; "_" included for the same reason
#                   _sep_after_spelled_digits accepts it: it glues in identifiers)
_C_LATIN_RANGES = ("\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u00FF"
                   "\u0100-\u024F\u1E00-\u1EFF")
_C_WORD_CLASS = "0-9A-Za-z_" + _C_LATIN_RANGES
_C_LETTER_CLASS = "A-Za-z_" + _C_LATIN_RANGES

# --- cardinal number words (verified reference §1) ---
_UNITS = {0: "", 1: "un", 2: "dau", 3: "tri", 4: "pedwar", 5: "pump",
          6: "chwech", 7: "saith", 8: "wyth", 9: "naw"}
# VIGESIMAL two-digit forms. NO LONGER USED BY GENERAL CARDINALS -- see _two_digit, which
# reverted to decimal. Kept because the values are correct and corroborated (0-31 by
# _HOUR_TRAD / _MINUTE_TRAD / _ORDINAL) and because the clock register is the same shape, so
# they document what "traditional" means in this file. If the vigesimal question is ever
# reopened for cardinals, _two_digit is the single line to change back.
#
# BTC style guide, "Degol ynteu ugeiniol":
# "Caiff ffigurau eu trin fel ffurfiau clasurol neu ugeiniol, yn hytrach na ffurfiau
# degol. Felly wrth gyfieithu 'and 21' rhowch 'ac 21' fel petai'n darllen 'ac un ar
# hugain' ac nid 'a 21' ('a dau ddeg un')."
#
# This REPLACES the decimal register (_TENS: "dau ddeg", "tri deg", ...), which native-speaker review
# chose on piper-lleol issue #6 -- the owner has ruled that BTC wins a conflict, and that
# this is reversible if the decision changes. Note the decimal choice was made against a
# reason I supplied and had not verified (see that issue): I told him the training data
# was decimal so vigesimal would leave the model's distribution. There is no evidence for
# that anywhere, and the mechanism does not hold -- this is a phoneme-level model, and
# every vigesimal word (ugain, hugain, pymtheg, bymtheg, deugain, deunaw) is in the Welsh
# lexicon exactly like every decimal one, so neither register is out of distribution.
#
# CORROBORATED 0-31 by data already in this file, not authored here:
#   _HOUR_TRAD    masculine 1-12: 11 "un ar ddeg", 12 "deuddeg"
#   _MINUTE_TRAD  feminine 1-29:  the teens and the whole "ar hugain" band, matching once
#                 the feminine numerals are read masculine (tair->tri, pedair->pedwar,
#                 dwy->dau); 25 "pump ar hugain" is identical in both genders
#   _ORDINAL      1-31: the same skeleton in ordinal form, incl. 30 "degfed ar hugain"
#                 and 31 "unfed ar ddeg ar hugain"
#   BTC           21 "un ar hugain", agreeing with _MINUTE_TRAD[21]
#
# DERIVED AND NOT CORROBORATED above 31: the decades deugain/trigain/pedwar ugain and the
# joiners "a deugain"/"a thrigain"/"a phedwar ugain". No repo data and no BTC example
# reaches them. Recorded for sign-off in docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md.
#
# NO EXCEPTIONS, deliberately. 50 is "deg a deugain" by the rule, not the common "hanner
# cant": adopting "hanner cant" would drag in its own incompatible 51-59 family ("hanner
# cant ac un") alongside the rule's "un ar ddeg a deugain", i.e. two sub-systems at once.
# Flagged as the most likely row to be challenged.
_VIG_UNDER_20 = {
    1: "un", 2: "dau", 3: "tri", 4: "pedwar", 5: "pump", 6: "chwech", 7: "saith",
    8: "wyth", 9: "naw", 10: "deg", 11: "un ar ddeg", 12: "deuddeg",
    13: "tri ar ddeg", 14: "pedwar ar ddeg", 15: "pymtheg", 16: "un ar bymtheg",
    17: "dau ar bymtheg", 18: "deunaw", 19: "pedwar ar bymtheg",
}
_VIG_DECADE = {20: "ugain", 40: "deugain", 60: "trigain", 80: "pedwar ugain"}
_VIG_JOIN = {20: "ar hugain", 40: "a deugain", 60: "a thrigain", 80: "a phedwar ugain"}
# 7 and 8 take "gant", not "cant". BTC style guide, "Treiglo ai peidio": "Ni threiglir
# enwau heblaw 'cant', 'punt' a 'ceiniog' yn feddal ar ol 'saith' ac 'wyth'" -- nouns other
# than those three do NOT soft-mutate after saith/wyth, which means those three DO. See
# _SAITH_WYTH_SOFT below for the rule as applied to punt/ceiniog.
#
# This OVERRIDES two rows previously carrying the "verified reference" label (they read
# "saith cant"/"wyth cant"). The owner's ruling is that BTC wins a conflict.
_HUNDREDS = {1: "cant", 2: "dau gant", 3: "tri chant", 4: "pedwar cant",
             5: "pum cant", 6: "chwe chant", 7: "saith gant", 8: "wyth gant",
             9: "naw cant"}
# feminine-agreeing scale multipliers (mil/miliwn are feminine).
# Language decision (2026-07-26, native-speaker review): 1 takes "un" (owner was shown
# the explicit "1000 -> un mil" example and chose it, for both mil and miliwn), and 5/6
# get their pre-nominal reductions ("pum"/"chwe") instead of falling through to
# _below_thousand's unreduced "pump"/"chwech" (native-speaker review confirmed "pum miliwn"; the owner
# extended it to "chwe" -- "if it's pum then it's chwe" -- matching the "chwe chilomedr"
# reduction separately confirmed for units). Neither "pum" nor "chwe" mutates the
# following "m", so no mutated form is needed for either.
# RESOLVED 2026-07-27 (Welsh Government BTC style guide, relayed by the owner from
# issue #2): "peidiwch a threiglo 'miliwn' na 'biliwn' er mwyn osgoi amwysedd rhyngddynt
# (hy, peidiwch a dweud '2 filiwn' ar gyfer '2 miliwn' na '2 biliwn')" -- do not mutate
# "miliwn" or "biliwn", because both soft-mutate to the SAME "filiwn" (m -> f and b -> f
# are the same mutation), so a spoken "dwy filiwn" cannot be told apart from two million
# and two billion. This is exactly the collision an earlier implementer on this branch
# had already flagged when "biliwn" was given no mutated multiplier (see §3.3 of
# docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md) -- the style guide confirms that
# reasoning and extends it to "miliwn" itself. So "dwy filiwn" -> "dwy miliwn": the
# numeral stays feminine ("dwy", not "dau"), only the mutation on "miliwn" drops.
# "mil" is NOT covered by this guide (it names only miliwn/biliwn, and nothing else
# mutates to "fil", so there is no ambiguity to avoid) -- "dwy fil" is unchanged.
# The GENDER of the numeral before miliwn (feminine "dwy"/"tair"/"pedair", vs. a
# masculine "dau"/"tri"/"pedwar") is a separate question the guide's digit-only example
# ("2 miliwn") does not settle either way -- kept as the existing feminine assumption,
# flagged for native-speaker sign-off in docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md.
#
# CLOSED 2026-07-28 (owner): "mil" takes "un" for the same reason "miliwn" does -- the two
# are the same construction and native-speaker review answered it for miliwn, so consistency settles mil
# rather than leaving it as a second open question. This was the last item on the ledger
# that had never had a native-speaker eye on it.
#
# THE YEAR REGISTER IS EXPLICITLY OUT OF SCOPE of that ruling ("don't let it affect the
# date decisions"). A year keeps its BARE "mil": 1980 is "mil naw wyth deg", NOT "un mil
# naw cant wyth deg". The two registers cannot merge by accident -- year_words has its own
# 1000-1999 branch and never consults _MIL_SPECIAL, and the assertion
#     assert not year_words(1980).startswith("un mil")
# in test_years_have_their_own_register_and_decimals_use_the_general_one pins it. Verified
# by mutation: routing the year band through the general cardinal fails that test with
# precisely this diff.
#
# One consequence, deliberate and already tested: a BARE four-digit number in prose is a
# cardinal, not a year, because nothing in "mae 1984 o bobl yma" marks it as a date -- so
# "1984" on its own now reads "un mil naw cant wyth deg pedwar". The year register is
# reached only from a real date (17/07/1984, "1 Ionawr 1984").
_MIL_SPECIAL = {1: "un mil", 2: "dwy fil", 3: "tair mil", 4: "pedair mil",
                5: "pum mil", 6: "chwe mil", 10: "deg mil"}
_MILIWN_SPECIAL = {1: "un miliwn", 2: "dwy miliwn", 3: "tair miliwn",
                   4: "pedair miliwn", 5: "pum miliwn", 6: "chwe miliwn", 10: "deg miliwn"}
# "biliwn" is MASCULINE where "mil"/"miliwn" are feminine ("dau biliwn", not "dwy biliwn").
# That asymmetry is deliberate and was closed by the owner: the no-mutation rule above is
# what keeps 2m and 2bn apart in speech, so the numeral's gender carries no disambiguating
# load and each word keeps its own. Like "miliwn", "biliwn" is never mutated.
#
# ADDED 2026-07-28 as a table, having previously been assembled ad hoc as
# `num_to_welsh(billions) + " biliwn"`. That skipped _scale, so the billion multiplier
# missed BOTH corrections the mil/miliwn multipliers get, and said:
#     5bn   -> "pump biliwn"       (not "pum biliwn")
#     6bn   -> "chwech biliwn"     (not "chwe biliwn")
#     100bn -> "cant biliwn"       (not "can biliwn")
#     200bn -> "dau gant biliwn"   (not "dau gan biliwn")
# The first of those is precisely the defect piper-lleol issue #3 raises against "pump
# miliwn" in data marked verified -- fixed for miliwn at the time, missed for biliwn
# because this path did not share the code. Routing it through _scale is the fix, and is
# why this is a table rather than a special case.
_BILIWN_SPECIAL = {1: "un biliwn", 2: "dau biliwn", 3: "tri biliwn",
                   4: "pedwar biliwn", 5: "pum biliwn", 6: "chwe biliwn", 10: "deg biliwn"}
# Above this, digit-by-digit. 18 nines, not the old billion: it is the widest run the C
# mirror can convert without overflowing its `long`, and cyp__num_words_for_run already
# digit-spells anything longer, so the two sides share one ceiling.
_CARDINAL_CEILING = 999_999_999_999_999_999


# The DECIMAL two-digit forms, back alongside the vigesimal ones. BTC's vigesimal rule
# carries an exception list one paragraph further down, which the first pass of this work
# missed entirely:
#
#   "Mae rhai eithriadau i'r arfer o drin ffigurau fel ffurfiau ugeiniol. Defnyddir y
#    system ddegol yn y sefyllfaoedd hyn:
#      * rhifau tai ...
#      * rhifau ffon
#      * rhifau cyn ac ar ol pwyntiau degol -- 'a 20.15 y cant' ('a dau ddeg pwynt un pump
#        y cant') nid 'ac 20.15 y cant' ('ac ugain pwynt pymtheg y cant')
#      * rhifau blynyddoedd ..."
#
# So decimals (BOTH sides of the point, "cyn ac ar ol") and years are DECIMAL, and the
# guide names "ugain pwynt pymtheg" as the wrong form outright. House and phone numbers are
# also excepted but need context we do not have -- a bare "80" cannot be known to be a
# house number -- so they are out of reach and left vigesimal.
_TENS_DEC = {2: "dau ddeg", 3: "tri deg", 4: "pedwar deg", 5: "pum deg",
             6: "chwe deg", 7: "saith deg", 8: "wyth deg", 9: "naw deg"}


def _two_digit_dec(tu: int) -> str:
    """0-99 in the DECIMAL register: the excepted contexts only (decimals, years)."""
    if tu == 0:
        return ""
    if tu < 10:
        return _UNITS[tu]
    if tu == 10:
        return "deg"
    if tu < 20:
        return "un deg " + _UNITS[tu - 10]
    t, u = divmod(tu, 10)
    return _TENS_DEC[t] + (" " + _UNITS[u] if u else "")


def _cardinal_dec(n: int) -> str:
    """A cardinal in the decimal register, for the contexts BTC excepts.

    FIXED 2026-07-28. This was hand-rolled as _HUNDREDS[n // 100] plus the last two digits,
    which is only correct BELOW 1000 -- and nothing bounded its one caller, the integer part
    of a decimal. So "1000.5" raised KeyError: 10 and "1234.56" raised KeyError: 12, an
    uncaught exception out of the normaliser on ordinary input. The C mirror indexed a
    10-entry array out of bounds for the same reason: "1000.5" SEGFAULTED, and "1234.56"
    silently dropped the "12" and read "tri deg pedwar pwynt pump chwech" -- 34.56. Neither
    was caught by make check, because no parity row has a decimal at or above 1000.

    Kept as a named delegate rather than deleted. It is byte-identical to num_to_welsh for
    every n now (verified 0..999 exhaustively), because the vigesimal revert made the
    general register decimal too -- but BTC excepts "rhifau cyn ac ar ol pwyntiau degol" in
    its own right, so if the vigesimal question is ever reopened this is where the exception
    has to reappear. Same reasoning as _two_digit.
    """
    return num_to_welsh(n)


def _two_digit(tu: int) -> str:
    """0-99 for general cardinals: the DECIMAL register.

    REVERTED 2026-07-27, same day it was changed. BTC's "Degol ynteu ugeiniol" says figures
    are read as vigesimal, and on the owner's "follow BTC on a conflict" ruling this became
    vigesimal for every cardinal in the system. That was too wide. The owner's
    understanding -- and the answer on issue #6 -- scoped the vigesimal question to the
    CLOCK: "degol yn haws i bawb ei ddeall. Degol felly" for numbers, traditional numerals
    for the time. Hearing it decided it: "Mae 25 o bobl" as "pump ar hugain o bobl", and
    99 as seven words ("pedwar ar bymtheg a phedwar ugain").

    So general cardinals are decimal again and this is just _two_digit_dec. The clock is
    UNAFFECTED and stays vigesimal -- _HOUR_TRAD and _MINUTE_TRAD are separate tables, so
    "10:25" is still "pump ar hugain munud wedi deg", which is the register the owner
    picked by ear and confirmed by native-speaker review.

    Also unaffected, because none of it is the register: the connected forms (can/pum/chwe),
    the saith/wyth soft mutation on cant/punt/ceiniog, the blynedd nasal rule, the year
    register, and BTC's decimal-point reading -- which now simply agrees with the general
    register instead of being an exception to it.
    """
    return _two_digit_dec(tu)


def _below_thousand(n: int) -> str:
    parts = []
    h, tu = divmod(n, 100)
    if h:
        parts.append(_HUNDREDS[h])
    if tu:
        parts.append(_two_digit(tu))
    return " ".join(parts)


def _reduce_cant(s: str) -> str:
    # "cant"/"gant"/"chant" -> "can"/"gan"/"chan" when directly before ANY noun, not only
    # before a scale word. BTC style guide, "Y ffurfiau cyswllt ynteu'r ffurfiau dyfynnol":
    # "Defnyddir y ffurfiau cyswllt 'pum' (5), 'chwe' (6) a 'can' (100) yn gyffredinol ee
    # 'pum arth', 'pum dyn', 'chwe adroddiad', 'chwe menyw', 'can metr', 'can merch'."
    #
    # "can metr" is the guide's own example and we read "cant metr" before this, so every
    # numeral-plus-noun site now routes through here. Only a TRAILING cant reduces, which
    # is what keeps "150 metr" as "cant pum deg metr" -- there the hundred is not the word
    # touching the noun.
    for full, red in (("chant", "chan"), ("gant", "gan"), ("cant", "can")):
        if s.endswith(full):
            return s[: -len(full)] + red
    return s


def _scale(mult: int, scale_word: str, special: dict) -> str:
    if mult in special:
        return special[mult]
    body = _below_thousand(mult)
    if mult % 100 == 0:
        body = _reduce_cant(body)
    return body + " " + scale_word


def num_to_welsh(n: int) -> str:
    """Cardinal in the decimal register. Above _CARDINAL_CEILING -> digit-by-digit.

    0..999,999,999 is the verified reference range and is untouched by the 2026-07-28
    billions work: the biliwn tier below only executes for n >= 1,000,000,000, which the
    reference set does not reach (it is why "biliwn" had to be sourced from GPC instead --
    see _BILIWN_SPECIAL and _scaled_cardinal).

    Before that work this function digit-spelled EVERYTHING above 999,999,999, so a
    literal "1000000000" read "un dim dim dim dim dim dim dim dim dim" -- nine "dim"s in a
    row. Only the currency path escaped it, and only when the amount was written with a
    magnitude suffix: "£3bn" said "tri biliwn o bunnoedd" while "£3000000000", the same
    amount, said "tri dim dim ... punt".
    """
    if n < 0:
        return "minws " + num_to_welsh(-n)
    if n == 0:
        return "sero"
    if n == 10:
        return "deg"
    if n > _CARDINAL_CEILING:
        return " ".join(_UNITS[int(d)] if d != "0" else "dim" for d in str(n))
    parts = []
    billions, r1 = divmod(n, 1_000_000_000)
    millions, r = divmod(r1, 1_000_000)
    thousands, rest = divmod(r, 1_000)
    if billions:
        # There is no signed-off Welsh word above "biliwn" -- getting that one word took a
        # GPC attestation (see _scaled_cardinal) -- so a multiplier of 1000+ stacks
        # "biliwn" rather than inventing "triliwn". Recursion is bounded at depth 2:
        # n <= 18 digits makes this argument <= 9 digits, which takes the tiers below.
        parts.append(_scale(billions, "biliwn", _BILIWN_SPECIAL) if billions <= 999
                     else num_to_welsh(billions) + " biliwn")
    if millions:
        parts.append(_scale(millions, "miliwn", _MILIWN_SPECIAL))
    if thousands:
        parts.append(_scale(thousands, "mil", _MIL_SPECIAL))
    if rest:
        parts.append(_below_thousand(rest))
    return " ".join(parts) if parts else "sero"


# --- abbreviations (ordered; verified reference §9). (regex, replacement) ---
_ABBREV = [
    (re.compile(r"\be\.e\.", re.I), "er enghraifft"),
    (re.compile(r"\bee\b", re.I), "er enghraifft"),
    (re.compile(r"\bh\.y\.", re.I), "hynny yw"),
    (re.compile(r"\bhy\b", re.I), "hynny yw"),
    (re.compile(r"\bayy?b\b", re.I), "ac yn y blaen"),
    (re.compile(r"\bd\.s\.", re.I), "dalier sylw"),
    (re.compile(r"\bDr\b\.?"), "doctor"),
    (re.compile(r"\bMrs\b\.?"), "musus"),
    (re.compile(r"\bMr\b\.?"), "mistar"),
    (re.compile(r"\bMs\b\.?"), "ms"),
]

# Acronyms are spelled out as lower-case LETTERS joined by ACRONYM_JOIN (not letter-name
# words): the G2P names the letters itself (bangor_g2p._EN_LETTER_NAMES), so "BBC" ->
# "b·b·c" reads bee-bee-cee. The old letter-name-word table ("bi", "èc", "ce"...) is gone:
# those words weren't in any lexicon, so LTS/CMUdict mangled them ("ce" read as "see-ee").
#
# The join marker is what tells the G2P these letters came from an acronym, and it exists
# because the G2P cannot recover that from spacing alone. It used to guess, by treating any
# run of >=2 adjacent single letters as an acronym — which silently swallowed the one-letter
# Welsh function words next to one: "y BBC" normalized to "y b b c" and came out as the
# ENGLISH letter Y, "wai bee bee see", and likewise "i"/"o"/"a" before an acronym. The
# ambiguity is real and not fixable downstream — lower-cased and space-separated, the
# article-plus-acronym "y b b c" is indistinguishable from the four-letter acronym it would
# be, exactly as "a p i" (from "API") is indistinguishable from Welsh words. So the boundary
# is recorded here, at the only point that still knows it.
#
# Consecutive letters only: a digit breaks the join, which is what keeps S4C reading "ès
# pedwar èc" (its letters are isolated, so they keep their WELSH names) rather than being
# spelled as one English run.
ACRONYM_JOIN = "·"

_VOWELS = set("aeiouwyâêîôûŵŷàáä/")  # for & -> a/ac (Welsh vowels incl. w, y)

# Typographic apostrophes -> ASCII. The Bangor dictionaries key Welsh clitics on the
# straight apostrophe (885 headwords: "i'r", "mae'r", "i'w") and carry no U+2019 form at
# all, so a curly apostrophe — what word processors and phone keyboards emit — misses the
# lexicon and falls through to LTS: "i’w" reads /ˈiː.u/ (two syllables) instead of /ɪu/,
# and "i’n" gains a stress the clitic should not have. Folded before every other pass so
# nothing downstream ever sees the non-ASCII form.
_TYPOGRAPHIC = str.maketrans({"’": "'", "ʼ": "'"})

# --- ordinals 1-31 (masculine, feminine) — traditional (verified reference §3) ---
_ORDINAL = {
    1: ("cyntaf", "cyntaf"), 2: ("ail", "ail"), 3: ("trydydd", "trydedd"),
    4: ("pedwerydd", "pedwaredd"), 5: ("pumed", "pumed"), 6: ("chweched", "chweched"),
    7: ("seithfed", "seithfed"), 8: ("wythfed", "wythfed"), 9: ("nawfed", "nawfed"),
    10: ("degfed", "degfed"), 11: ("unfed ar ddeg", "unfed ar ddeg"),
    12: ("deuddegfed", "deuddegfed"), 13: ("trydydd ar ddeg", "trydedd ar ddeg"),
    14: ("pedwerydd ar ddeg", "pedwaredd ar ddeg"), 15: ("pymthegfed", "pymthegfed"),
    16: ("unfed ar bymtheg", "unfed ar bymtheg"), 17: ("ail ar bymtheg", "ail ar bymtheg"),
    18: ("deunawfed", "deunawfed"), 19: ("pedwerydd ar bymtheg", "pedwaredd ar bymtheg"),
    20: ("ugeinfed", "ugeinfed"), 21: ("unfed ar hugain", "unfed ar hugain"),
    22: ("ail ar hugain", "ail ar hugain"), 23: ("trydydd ar hugain", "trydedd ar hugain"),
    24: ("pedwerydd ar hugain", "pedwaredd ar hugain"), 25: ("pumed ar hugain", "pumed ar hugain"),
    26: ("chweched ar hugain", "chweched ar hugain"), 27: ("seithfed ar hugain", "seithfed ar hugain"),
    28: ("wythfed ar hugain", "wythfed ar hugain"), 29: ("nawfed ar hugain", "nawfed ar hugain"),
    30: ("degfed ar hugain", "degfed ar hugain"), 31: ("unfed ar ddeg ar hugain", "unfed ar ddeg ar hugain"),
}
_MONTHS = ["ionawr", "chwefror", "mawrth", "ebrill", "mai", "mehefin",
           "gorffennaf", "awst", "medi", "hydref", "tachwedd", "rhagfyr"]
# month form after the preposition "o" (soft mutation; verified reference §4)
_MONTH_MUT = ["ionawr", "chwefror", "fawrth", "ebrill", "fai", "fehefin",
              "orffennaf", "awst", "fedi", "hydref", "dachwedd", "ragfyr"]
_MONTH_NUM = {name: i + 1 for i, name in enumerate(_MONTHS)}
_ART_VOWELS = "aeiouwyâêîôûŵŷh"  # article "yr" before these, else "y"


# Years are the fourth BTC exception ("rhifau blynyddoedd"), so DECIMAL, not vigesimal.
# The guide's blynyddoedd entry offers two registers at the translator's discretion and
# warns only against mixing them; the owner chose the "other registers" one:
#
#   'mil naw wyth deg'      (1980)   -- chosen
#   'mil naw cant a phedwar ugain'   (1984, classical)  -- not chosen
#   'dwy fil ac un deg un'  (2011)   -- chosen
#   'dwy fil a dau ddeg tri' (2023)  -- chosen
#   'dwy fil a dau'         (2002)   -- masculine always, per the same entry
#
# Note the leading element is a BARE "mil", not "un mil". The "trin y rhif cyntaf fel 'un'"
# line in the exception list governs which CONJUNCTION to write before a figure
# ("rhwng 1995 ac 1996"); it is not how the year is spoken. An earlier pass of this work
# read it the other way round and told the owner BTC ruled out a bare "mil".
#
# DERIVED, no BTC example: years ending 00 or 0X, and anything from 2100. Recorded in
# docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md rather than presented as the guide's.
_YEAR_ASPIRATE = {"c": "ch", "p": "ph", "t": "th"}


def _year_join(rest: str) -> str:
    """" a" / " ac" before the final element, with the aspirate mutation "a" triggers.

    BTC: 'dwy fil ac un deg un' (vowel -> ac), 'dwy fil a dau ddeg tri' (consonant -> a),
    and in the classical register 'a thri ar hugain' / 'a phedwar ugain' -- so "a"
    aspirate-mutates c/p/t exactly as it does elsewhere in Welsh.
    """
    if rest[0] in _VOWELS:
        return "ac " + rest
    first, tail = rest.split(" ", 1) if " " in rest else (rest, "")
    if first[0] in _YEAR_ASPIRATE:
        first = _YEAR_ASPIRATE[first[0]] + first[1:]
    return "a " + (f"{first} {tail}" if tail else first)


def year_words(y: int) -> str:
    """A year in the decimal register chosen by the owner. See the block comment above."""
    if 1000 <= y <= 1999:
        # "mil" + the hundreds digit as a bare digit + the last two decimal.
        hundreds, tu = divmod(y - 1000, 100)
        parts = ["mil"]
        if hundreds:
            parts.append(_UNITS[hundreds])
        if tu:
            parts.append(_two_digit_dec(tu))
        return " ".join(parts)
    if 2000 <= y <= 2099:
        rest = _two_digit_dec(y - 2000)
        return "dwy fil" if not rest else "dwy fil " + _year_join(rest)
    return num_to_welsh(y)          # outside both bands: no BTC guidance, plain cardinal


def _date_words(d: int, m: int, y=None) -> str:
    ordw = _ORDINAL[d][0]                      # day-of-month = masculine ordinal
    art = "yr" if ordw[0] in _ART_VOWELS else "y"
    parts = [art, ordw, "o", _MONTH_MUT[m - 1]]
    if y is not None:
        parts.append(year_words(y))
    return " ".join(parts)


# Every CONSUMING digit position in the specialised number patterns is the explicit
# ASCII class (the `_D` narrowing, swept across the whole file 2026-08-21 -- FOLLOWUPS
# section G): `\d` matched every Unicode Nd, so `£٣`/`٣%`/`٣.٣`/`٣ Ionawr 2020` were
# claimed here and never by cy_normalize.c's byte-oriented passes -- four measured
# divergences. NEGATIVE lookbehind guards deliberately keep their wide class (`_PHONE`'s
# `(?<![\d,.])`): a guard narrowed is a match widened.
_DATE_NUM = re.compile(r"\b([0-9]{1,2})/([0-9]{1,2})/([0-9]{2,4})\b")
# The year group's trailing guard mirrors C's `!word_after(in, ys)`: "1 Ionawr 2026x" is
# not a date-with-year ("2026x" is a code; its digits fall to the later passes, which the
# digit/letter splitter has already separated for them). Python lacked the guard and C had
# it, so the two engines read the YEAR differently there ("dwy fil A dau ddeg chwech" via
# the year register vs the plain cardinal) -- a pre-existing divergence the fuzzers never
# fed (no corpus shape puts a letter directly after a year). The class is _C_WORD_CLASS,
# not \w, for the usual Latin-only-mirror reason at the top of the module.
_DATE_MONTH = re.compile(r"\b([0-9]{1,2})\s+(" + "|".join(_MONTHS) + r")\b"
                         rf"(?:\s+([0-9]{{4}})(?![{_C_WORD_CLASS}]))?", re.I)
_ORDINAL_RE = re.compile(r"\b([0-9]+)(af|il|ydd|edd|ed|fed|eg|ain)\b")


def _date_num_repl(m: re.Match) -> str:
    d, mm, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return _date_words(d, mm, y) if 1 <= d <= 31 and 1 <= mm <= 12 else m.group(0)


def _date_month_repl(m: re.Match) -> str:
    d = int(m.group(1))
    mm = _MONTH_NUM[m.group(2).lower()]
    y = int(m.group(3)) if m.group(3) else None
    return _date_words(d, mm, y) if 1 <= d <= 31 else m.group(0)


def _ordinal_repl(m: re.Match) -> str:
    n = int(m.group(1))
    if not (1 <= n <= 31):
        return m.group(0)
    return _ORDINAL[n][1 if m.group(2) == "edd" else 0]


# --- currency, time, symbols (recommended defaults; flagged in docs/NORMALIZATION.md) ---
# BTC "Treiglo ai peidio" (quoted at _HUNDREDS): punt soft-mutates after saith and wyth,
# hence the 7/8 rows. 3/4 stay unmutated and 6 takes the aspirate "phunt", as before.
_POUND = {1: "un bunt", 2: "dwy bunt", 3: "tair punt", 4: "pedair punt",
          5: "pum punt", 6: "chwe phunt", 7: "saith bunt", 8: "wyth bunt",
          100: "can punt"}

# The BTC rule as a table, for the sites that build "<numeral> <noun>" at runtime rather
# than reading a literal off _HUNDREDS/_POUND. Only these three nouns, only after these
# two numerals -- the guide says nothing about mutation after un/dau/tri/... for them, so
# nothing else is inferred here.
#
# NOTE what this does NOT fix, now visible alongside it: "ceiniog" is feminine and gets no
# gender agreement or reduction at all on the pence path ("2c" -> "dau ceiniog", "5c" ->
# "pump ceiniog"). That is deferred convention item 7 in docs/NORMALIZATION.md ("voicing
# ceiniog", the ".50" reading) and is not settled by this rule, so it is left alone rather
# than guessed at.
_SAITH_WYTH_SOFT = {"cant": "gant", "punt": "bunt", "ceiniog": "geiniog"}


def _soft_after_saith_wyth(numeral: str, noun: str) -> str:
    """The noun, soft-mutated iff the numeral directly before it is saith or wyth."""
    if numeral.split()[-1] in ("saith", "wyth"):
        return _SAITH_WYTH_SOFT.get(noun, noun)
    return noun


# At and above 1000 a pounds amount takes "o bunnoedd", not the singular "punt".
#
# OWNER, 2026-07-28, answering it with the phrase itself: "Mil o bunnoedd". The defect it
# settles was NOT a matter of taste -- the SAME amount read two ways depending only on how
# the author had typed it, which nobody had chosen:
#
#     £1000000   ->  "un miliwn punt"        (digits)
#     £1m        ->  "un miliwn o bunnoedd"  (magnitude suffix)
#
# The threshold is the scale-word tier, the owner's choice of the three offered: any amount
# reaching mil/miliwn/biliwn takes the plural, and below 1000 keeps the singular, so "£5" is
# still "pum punt" and "£999" still "naw cant naw deg naw punt". It also makes the two
# spellings above finally agree.
#
# BARE "mil", not "un mil" -- also the owner's call, and a DELIBERATE exception to the un mil
# ruling they closed earlier the same day. Welsh idiom drops the "un" in this phrase. The
# exception is scoped to the currency phrase: the cardinal 1000 is still "un mil" and the
# year register is still its own bare "mil".
#
# "un miliwn"/"un biliwn" deliberately KEEP their "un": that is what the magnitude-suffix
# path has always shipped and nobody objected to it, so it is left alone rather than
# changed by inference from a ruling that was about "mil". Flagged in docs/FOLLOWUPS.md.
#
# NOTE "cant" stops reducing to "can" above the threshold, and that is correct rather than a
# regression: _reduce_cant fires only where the numeral DIRECTLY touches the noun, and "o"
# now sits between them. So "£1500" is "mil pum cant o bunnoedd", while "£100" -- below the
# threshold, noun still touching -- stays "can punt".
_POUNDS_PLURAL_FROM = 1000


def _pounds(n: int) -> str:
    # _POUND hand-cases 100 ("can punt"); the fallback needs the same reduction or
    # "£200" reads "dau gant punt" instead of "dau gan punt".
    if n in _POUND:
        return _POUND[n]
    if n >= _POUNDS_PLURAL_FROM:
        return _pounds_plural(n)
    numeral = _reduce_cant(num_to_welsh(n))
    return _counted_noun(numeral, n, "punt")


def _pounds_plural(n: int) -> str:
    """"<numeral> o bunnoedd" -- no _reduce_cant, because "o" separates numeral and noun."""
    numeral = num_to_welsh(n)
    # Exact match or a following SPACE, never a bare prefix test: "un miliwn".startswith(
    # "un mil") is True, so a prefix test would strip the "un" off every million and billion
    # too and silently change "£1m", which the owner's ruling was not about. Caught on the
    # first run of the new test.
    if numeral == "un mil" or numeral.startswith("un mil "):
        numeral = numeral[len("un "):]      # bare "mil o bunnoedd", per the owner
    return numeral + " o bunnoedd"


# Magnitude suffix on a currency amount: in "£5m" the "m" is MILLION, not metres.
# Case-insensitive, and it must sit directly against the amount ("£5 m" is left alone).
# Value = the digits, the optional decimal digits, then the suffix's zeros — built as a
# digit STRING so an absurd amount cannot overflow anything, and so the C port can
# reproduce it without 64-bit arithmetic.
_MAGNITUDE_ZEROS = {"k": 3, "m": 6, "bn": 9}
_CURRENCY = re.compile(r"£\s?([0-9][0-9,]*)(?:\.([0-9]{1,2}))?(?:([Bb][Nn]|[Mm]|[Kk])\b)?")
# (?<![A-Za-z]) stops the pence rule firing inside an alphanumeric code: without it
# the "4c" inside "s4c" read as fourpence ("spedwar ceiniog").
_PENCE = re.compile(r"(?<![A-Za-z])([0-9][0-9,]*)([pc])\b")
# Idiomatic-register clock (language decision, 2026-07-26: the owner chose this register
# over the previous digital default -- see docs/NORMALIZATION.md). Minutes 00-59 only
# ([0-5]\d), not an unrestricted \d{2}, so a garbage ":99" cannot reach the minute logic
# below. The optional trailing group is an explicit am/pm-style marker: Welsh "yb"/"y.b."
# (y bore) and "yp"/"y.p." (y prynhawn), or the English-influenced "am"/"pm" that Welsh
# text commonly borrows verbatim -- in both its bare and dotted ("a.m."/"p.m.") spellings.
# The dotted English forms earn their place the hard way: absent from the alternation,
# "7:00p.m." did not merely lose its marker -- the trailing (?!\w) failed on the unmatched
# "p", the WHOLE time match collapsed, and the minute digits fell through to _PENCE, which
# read "00p" as money: "saith sero ceiniog.m.". A time misread as PENCE is the exact
# confident-wrong-reading class the yh fix below records. (?!\w) rather than a trailing
# \b: a dotted marker like "y.p." ends on a non-word character, so \b (word/non-word
# transition) would never fire at end-of-string there, silently dropping the marker match.
# "yh"/"y.h." (yr hwyr, evening) are listed alongside yb/yp because authors write them:
# the BTC style guide names them precisely to RECOMMEND AGAINST writing them ("10am hyd
# 4pm, nid '10 am hyd 4 pm' na '10yb hyd 4yh'"), which is advice to writers, not to a
# reader. A TTS must read what is actually in front of it. Before this, "16:00yh" did not
# merely lose its qualifier -- the trailing (?!\w) failed on the unmatched "yh", so the
# WHOLE time match failed and the digits fell to the integer pass:
# "un deg chwech:seroyh", colon and all.
#
# The dotted forms must precede the bare ones in the alternation ("y.h." before "yh"),
# or the bare form matches first and leaves a stray "." behind.
# The HOUR is bounded 0-23, the same reasoning as the minute's [0-5]\d. Leaving it \d{1,2}
# while adding the h % 12 reduction turned nonsense into a plausible-sounding lie:
# "90:00" read as "chwech o'r gloch" and "99:59" as "un funud i bedwar". Out of range now
# fails the match and the digits fall to the number pass, which is audibly wrong rather
# than silently wrong -- the behaviour before the reduction existed.
_TIME = re.compile(
    r"\b([01]?[0-9]|2[0-3]):([0-5][0-9])"
    r"(?:\s?(y\.b\.|yb|y\.p\.|yp|y\.h\.|yh|a\.m\.|am|p\.m\.|pm))?(?!\w)", re.I)
# The colonless clock: "7pm", "10yb", "7.30pm" -- the very forms BTC tells Welsh authors
# to WRITE ("10am hyd 4pm, nid ... '10yb hyd 4yh'"), which previously fused into LTS
# nonwords ("saithpm") or, dotted, fell to _PENCE as money ("7p.m." -> "saith
# geiniog.m."). An ALTERNATION beside _TIME, not an optional minute group inside it:
# making _TIME's ":MM" optional would read every bare "7" as "saith o'r gloch".
#
# Three deliberate restrictions, each load-bearing:
#   - The marker is REQUIRED and GLUED (no \s?): "am" is a Welsh preposition, and a
#     spaced allowance turns "5 am ddim" (five for free) and "2 am 1" (two for one)
#     into clock readings -- the confident-wrong class this file exists to avoid.
#     The spaced "7 pm" therefore stays unclaimed (reads "saith pm"): an accepted,
#     pinned limitation. BTC's canonical written form is glued anyway.
#   - (?<![:.,]) blocks the fragment reads a failed context would otherwise leave:
#     "25:00pm" (invalid hour) must not have its "00pm" read as midnight, "99.15pm"
#     its "15pm" as three o'clock, "1,23pm" its "23pm" as eleven. Out-of-range input
#     falls to the number passes -- audibly wrong rather than silently wrong, the same
#     fail-safe direction as _TIME's own hour/minute bounding above.
#   - The dotted-hour minute ("7.30pm") also requires the marker: bare "7.30" belongs
#     to _DECIMAL ("saith pwynt tri sero") and must stay there.
# Groups align with _TIME (1=hour, 2=minutes|None, 3=marker) so one _time_repl serves
# both patterns.
_TIME_NOCOLON = re.compile(
    r"\b(?<![:.,])([01]?[0-9]|2[0-3])(?:\.([0-5][0-9]))?"
    r"(y\.b\.|yb|y\.p\.|yp|y\.h\.|yh|a\.m\.|am|p\.m\.|pm)(?!\w)", re.I)


def _scaled_cardinal(n: int) -> str:
    """Cardinal for a scaled currency amount. Now just num_to_welsh -- kept for the record.

    ABSORBED 2026-07-28. This function existed because num_to_welsh digit-spelled anything
    above 999,999,999, and a "£3bn" must not say "tri dim dim dim dim dim dim dim dim
    dim". Splitting the billions off HERE fixed the symptom for one caller and left the
    disease: the ONLY route to it was a currency amount written with a magnitude suffix,
    so the identical amount in full digits still said the nine "dim"s, currency or not.
    num_to_welsh owns the biliwn tier now, so every caller gets it and this is a delegate.

    Fixing it there rather than here also fixed three wrong multipliers for free, because
    the tier goes through _scale like mil and miliwn do -- see _BILIWN_SPECIAL.

    SIGNED OFF (docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md §3, piper-lleol issue #2):
    "biliwn" sits outside the verified reference set only because that reference stops
    below a billion -- it is NOT a coinage. Native-speaker review confirmed the word and cited GPC,
    which has an attestation from 1725. No mutation is applied to the multiplier
    ("dau biliwn", "tri biliwn"): the BTC style guide (see _MILIWN_SPECIAL's definition)
    says "miliwn"/"biliwn" are never mutated, precisely because both soft-mutate to the
    same "filiwn" and a spoken "dwy filiwn" could not otherwise be told apart from 2m
    and 2bn. The GENDER of the multiplier (masculine "dau" here vs. miliwn's feminine
    "dwy") is a deliberate, accepted asymmetry: the owner closed it on the grounds that
    the no-mutation rule is what protects the 2m/2bn distinction, so the numeral's
    gender carries no disambiguating load and each word keeps its own."""
    return num_to_welsh(n)


def _currency_repl(m: re.Match) -> str:
    suffix = m.group(3)
    if suffix is None and _UNIT_TAIL.match(m.string, m.end()):
        # _CURRENCY now runs BEFORE _UNIT (see WelshNormalizer.normalize), so it is the
        # one that has to yield: whenever _UNIT would have claimed these digits, hand
        # the whole match back untouched and let it. Without this, moving the currency
        # pass first would turn "£5kg" from "£pum cilogram" into "pum puntkg" — a glued
        # nonword LTS reads as gibberish. A magnitude suffix (group 3) wins outright,
        # which is the whole point: "£5m" is millions, not metres.
        return m.group(0)
    if suffix is not None:
        frac = m.group(2) or ""
        zeros = _MAGNITUDE_ZEROS[suffix.lower()]
        digits = m.group(1).replace(",", "") + frac + "0" * (zeros - len(frac))
        # "o bunnoedd" (plural after "o", soft mutation p->b) rather than the singular
        # "punt" the small-amount table uses: PENDING NATIVE-SPEAKER SIGN-OFF, listed
        # in docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md §3 with the other unverified
        # forms, exactly as the fraction and unit tables are.
        # Through _pounds_plural so the suffix and digit spellings of the same amount agree
        # -- "£1k" and "£1000" both say "mil o bunnoedd". Before the 2026-07-28 ruling this
        # path was the ONLY one saying "o bunnoedd" at all, which is what made the two
        # spellings disagree in the first place.
        return _sep_if_latin_tail(_pounds_plural(int(digits)), m)
    pounds = int(m.group(1).replace(",", ""))
    pence = int(m.group(2)) if m.group(2) else 0
    # PENCE KEEP THE SINGULAR (owner, 2026-07-28): "o bunnoedd" mid-phrase is clumsy, so
    # "£1234.56" stays "...tri deg pedwar punt pum deg chwech ceiniog" rather than putting
    # the plural in front of the pence. Only a pounds-only amount takes the plural.
    if pence > 0 and pounds >= _POUNDS_PLURAL_FROM:
        out = _counted_noun(_reduce_cant(num_to_welsh(pounds)), pounds, "punt")
    else:
        out = _pounds(pounds)
    if m.group(2):
        p = pence
        if p > 0:
            # Through _pence_words, so the connected forms and the saith/wyth mutation
            # apply here too. This path built its own string, so "£1.07" said "saith
            # ceiniog" while a bare "7c" correctly said "saith geiniog".
            out += " " + _pence_words(p)
    # "£5x" -> "pum punt x", not the glued nonword "pum puntx". The splitter cannot do
    # it: this pass runs first and the replacement's letters erase the boundary.
    return _sep_if_latin_tail(out, m)


# BTC "Y lluosog ynteu'r unigol", verbatim:
#
#   "Gyda ffigurau a rhifolion hyd at ddeg, defnyddir yr unigol, ee '2 filltir', 'dau ddyn'.
#    Gyda ffigurau a rhifolion o 11 i fyny, defnyddir yr unigol pan fo'r hyn a gyfrifir yn
#    dod ar ol y rhif ee '18 mis' ... yn hytrach na '18 o fisoedd'.
#    Gyda ffigurau a rhifolion o 11 i fyny, defnyddir y lluosog yn y sefyllfaoedd hyn:
#      * pan ddefnyddir y system ugeiniol a phan fo'n arferol rhoi'r hyn a gyfrifir yn y
#        canol -- defnyddir '11 o filltiroedd' ('un ar ddeg o filltiroedd') nid '11 filltir'
#        ('un filltir ar ddeg')"
#
# Three branches. The first two we already satisfied: <=10 is singular ("pum cilomedr"),
# and 11+ with the noun AFTER the numeral is singular too -- "deunaw metr" is exactly the
# shape of BTC's "18 mis", so the metric units were never wrong.
#
# The third is what was missing. It applies only where it is "arferol" to put the counted
# noun MID-numeral, and BTC's own example shows which numerals those are: "un ar ddeg" is
# COMPOUND, and its customary form "un filltir ar ddeg" puts the noun in the middle -- so
# use "o" + plural instead. A simple numeral (ugain, deugain, trigain, can, deg) has no
# middle to sit in and keeps the singular, which is why "can mlynedd" and "ugain mlynedd"
# are right as they are.
#
# DERIVED: the compound test is mine. BTC states the principle and gives one example
# ("milltir", which is not even a noun we emit); it does not enumerate which nouns are
# "arferol" mid-numeral or which numerals count as compound. Applied to the three
# traditional counted nouns we do emit -- punt, ceiniog, blynedd -- and NOT to the metric
# units, which are modern loanwords with no mid-numeral custom. "blwydd" is excluded too:
# "un ar ddeg mlwydd oed" is a fixed adjectival phrase, not a counted plural.
_MID_NUMERAL_PLURAL = {
    "punt": "bunnoedd",        # soft mutation after "o"; the form confirmed on #2
    "ceiniog": "geiniogau",
    "blynedd": "flynyddoedd",
}


def _is_compound_numeral(numeral: str) -> bool:
    """True for a vigesimal numeral with a joiner, i.e. one whose customary form puts the
    counted noun in the middle ("un filltir ar ddeg"). False for a simple word (ugain,
    deugain, can), which has no middle."""
    return " ar " in f" {numeral} " or " a " in f" {numeral} "


def _counted_noun(numeral: str, n: int, singular: str) -> str:
    """"<numeral> <noun>" or "<numeral> o <plural>", per the three BTC branches above."""
    if n >= 11 and singular in _MID_NUMERAL_PLURAL and _is_compound_numeral(numeral):
        return f"{numeral} o {_MID_NUMERAL_PLURAL[singular]}"
    return f"{numeral} {_soft_after_saith_wyth(numeral, singular)}"


def _pence_words(n: int) -> str:
    """"<numeral> ceiniog", with both BTC rules that apply to it.

    * the connected forms: BTC "Y ffurfiau cyswllt" gives pum (5), chwe (6) and can (100)
      "yn gyffredinol", so "5c" is "pum ceiniog", not "pump ceiniog". _MASC_BEFORE_NOUN
      differs from num_to_welsh in exactly those two rows, which is precisely the rule.
    * the soft mutation after saith/wyth, which "£1.07" was missing entirely because the
      currency path built its own pence string instead of coming through here.

    NOT fixed, and deliberately: "ceiniog" is feminine, so 1/2 should be "un"/"dwy" and
    _MASC_BEFORE_NOUN gives "un"/"dau". That is deferred convention item 7 ("voicing
    ceiniog"), BTC is silent on it, and it is not this rule's business.
    """
    numeral = _MASC_BEFORE_NOUN.get(n, _reduce_cant(num_to_welsh(n)))
    return _counted_noun(numeral, n, "ceiniog")


def _pence_repl(m: re.Match) -> str:
    return _pence_words(int(m.group(1).replace(",", "")))


# --- clock: hour and minute word tables -----------------------------------------
# ONLY "o'r gloch"/"wedi"/"i"+mutation/"chwarter"/"hanner awr wedi" and the traditional-
# numerals-for-minutes choice are the VERIFIED reference (docs/NORMALIZATION.md). Every
# individual hour/minute WORD below is DERIVED from standard Welsh vigesimal-counting and
# mutation rules, exactly as the fraction/unit tables were, and is PENDING NATIVE-SPEAKER
# SIGN-OFF -- see docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md §5 for the full
# hour x minute verification table (every hour 1-12 against a representative set of
# minutes) that is the reviewable surface for this.
#
# Traditional cardinal hours 1-12 (masculine; identical to _UNITS/num_to_welsh below 11,
# but 11/12 use the traditional vigesimal words "un ar ddeg"/"deuddeg", not the decimal
# "un deg un"/"un deg dau" -- this is the "clock uses traditional numerals" half of the
# reference that is verified; the words above 10 are themselves the ordinal roots
# already in _ORDINAL, e.g. 13 "trydydd ar ddeg" -> cardinal "tri ar ddeg").
_HOUR_TRAD = {1: "un", 2: "dau", 3: "tri", 4: "pedwar", 5: "pump", 6: "chwech",
              7: "saith", 8: "wyth", 9: "naw", 10: "deg", 11: "un ar ddeg", 12: "deuddeg"}
# Soft-mutated hours, for use after "i" (to) -- the one mutation the verified reference
# names explicitly ("chwarter i ddau"). Only c/p/t/g/b/d/ll/m/rh mutate; "ch" (chwech),
# vowels (un, wyth) and s/n (saith, naw) are unaffected, matching the reference example.
_HOUR_TRAD_MUT = {1: "un", 2: "ddau", 3: "dri", 4: "bedwar", 5: "bump", 6: "chwech",
                   7: "saith", 8: "wyth", 9: "naw", 10: "ddeg", 11: "un ar ddeg",
                   12: "ddeuddeg"}
# Traditional cardinal minutes 1-29 (feminine agreement: "munud" is feminine, so 2/3/4
# take dwy/tair/pedair). Only 1-29 is ever needed: 30/45/60- minus-mm never reaches this
# table (30 and 45 are the special hanner-awr/chwarter forms below, and the "i" branch's
# complement 60-mm is itself always in 1-29 for mm in 31..59, mm != 45).
# NOT the pre-nominal-reduced forms (pum/chwe) inside a compound: "munud" does not
# directly follow the leading digit there ("ar hugain"/"ar ddeg" intervenes), so the
# full/citation form is kept -- e.g. 25 is "pump ar hugain munud", not "*pum ar hugain
# munud" (this is the one form given verbatim in the task brief; every other row here is
# built the same way by analogy with the traditional ordinal table).
_MINUTE_TRAD = {
    1: "un", 2: "dwy", 3: "tair", 4: "pedair", 5: "pump", 6: "chwech", 7: "saith",
    8: "wyth", 9: "naw", 10: "deg", 11: "un ar ddeg", 12: "deuddeg",
    13: "tair ar ddeg", 14: "pedair ar ddeg", 16: "un ar bymtheg", 17: "dwy ar bymtheg",
    18: "deunaw", 19: "pedair ar bymtheg", 20: "ugain", 21: "un ar hugain",
    22: "dwy ar hugain", 23: "tair ar hugain", 24: "pedair ar hugain",
    25: "pump ar hugain", 26: "chwech ar hugain", 27: "saith ar hugain",
    28: "wyth ar hugain", 29: "naw ar hugain",
}
# Standalone (non-compound) minute counts DO take the pre-nominal reduction, because
# "munud" directly follows: pum/chwe (cf. "pum mil"/"chwe mil" above) and the archaic
# nasal "deng" (a fixed idiom before munud/diwrnod/mlynedd, not a general rule -- flagged
# as one of the least-certain rows in the review doc). "un"/"dwy" additionally soft-
# mutate the noun itself (m -> f), the same trigger as any other numeral-noun phrase.
_MINUTE_STANDALONE = {1: "un funud", 2: "dwy funud", 5: "pum munud", 6: "chwe munud",
                       10: "deng munud"}
# marker -> the qualifier it explicitly requests. Three-way, not two: "yh" is yr hwyr
# (evening), which is NOT y prynhawn. "pm" stays y prynhawn, as it always did -- English
# pm spans both halves and picking a side for it would be inventing information.
# Every form _TIME's alternation can match MUST have an entry here: a marker that
# matches but has no entry is silently dropped (the match succeeds, the qualifier is
# None), which is how "7p.m." once read as a bare "saith o'r gloch" in a draft of the
# dotted fix. tests/test_normalize.py drives its marker loop off this dict so the
# alternation and the dict cannot drift apart.
_MARKER_QUALIFIER = {
    "yb": "y bore",     "y.b.": "y bore",     "am": "y bore",     "a.m.": "y bore",
    "yp": "y prynhawn", "y.p.": "y prynhawn", "pm": "y prynhawn", "p.m.": "y prynhawn",
    "yh": "yr hwyr",    "y.h.": "yr hwyr",
}


def _clock_qualifier(h: int, marker: str | None) -> str | None:
    """y bore / y prynhawn / yr hwyr -- ONLY from explicit information, never invented.

    An explicit am/pm-style marker always wins. Failing that, an hour >=13 is
    unambiguous on its own (24h notation), so it may take the qualifier that its own
    reading of the day implies. An hour of 12 or less with no marker is genuinely
    ambiguous in a 12-hour reading (which is what the traditional-numeral clock speaks)
    and gets nothing -- a bare "3:00" is "tri o'r gloch", full stop.
    """
    if marker:
        qualifier = _MARKER_QUALIFIER.get(marker.lower())
        if qualifier:
            return qualifier
    if h >= 13:
        if h <= 17:
            return "y prynhawn"
        if h <= 23:
            return "yr hwyr"
    return None


def _hour_word(h12: int, mutated: bool = False) -> str:
    table = _HOUR_TRAD_MUT if mutated else _HOUR_TRAD
    return table.get(h12, num_to_welsh(h12))


def _minute_phrase(n: int) -> str:
    if n in _MINUTE_STANDALONE:
        return _MINUTE_STANDALONE[n]
    return f"{_MINUTE_TRAD[n]} munud"


def _time_repl(m: re.Match) -> str:
    h = int(m.group(1))
    # _TIME_NOCOLON's minute group is optional: a colonless "7pm" is on the hour, which
    # is behaviourally identical to ":00" -- no sentinel needed anywhere downstream.
    mm = int(m.group(2)) if m.group(2) is not None else 0
    qualifier = _clock_qualifier(h, m.group(3))
    h12 = h % 12 or 12
    if mm == 0:
        core = f"{_hour_word(h12)} o'r gloch"
    elif mm == 15:
        core = f"chwarter wedi {_hour_word(h12)}"
    elif mm == 30:
        core = f"hanner awr wedi {_hour_word(h12)}"
    elif mm == 45:
        nxt = h12 % 12 + 1
        core = f"chwarter i {_hour_word(nxt, mutated=True)}"
    elif mm < 30:
        core = f"{_minute_phrase(mm)} wedi {_hour_word(h12)}"
    else:
        nxt = h12 % 12 + 1
        core = f"{_minute_phrase(60 - mm)} i {_hour_word(nxt, mutated=True)}"
    return f"{core} {qualifier}" if qualifier else core


# (_C_WORD_CLASS / _C_LETTER_CLASS -- the C-mirror character classes -- are defined at
# the top of the module, next to _D, because patterns above this point need them too.)

# The digit/letter SPLITTER: one space at every ASCII-digit <-> Latin-letter/_ boundary,
# both directions. This is FOLLOWUPS section G's "general digit/letter peeling job", and
# it lives HERE, late in the normaliser, not in the G2P as that section first suggested:
# by G2P time the wrong verbalisation is already baked ("x05" -> "xpump" happens in
# _INTEGER, and phonemize silently skips a bare digit token, so nothing downstream can
# recover it). Placement in normalize() is load-bearing on both edges:
#   AFTER every pass that legitimately consumes letter-adjacent digits -- _ORDINAL_RE
#   ("3af"), _CURRENCY ("£5M"), _UNIT ("5km"), _BLYNEDD, _TIME/_TIME_NOCOLON ("7pm",
#   "12:30yb"), _PENCE ("50p") -- and after _EMAIL_OR_URL, so an address's digits are
#   not split before it reads them. By then a remaining digit|letter adjacency is a
#   junk code ("x05", "covid19", "s4c"), and splitting it is what the number passes
#   need to verbalise the digits correctly. _PENCE in particular must have already
#   run: its (?<![A-Za-z]) lookbehind is what keeps the "4c" of "s4c" from reading as
#   fourpence, and this splitter would defeat it ("s 4c") if it ran first.
#   BEFORE _DEGREE/_MATH_OPS/_PERCENT/_DECIMAL/_PHONE/_DIGIT_SEQ/_INTEGER, whose
#   guards can then see the boundary as real: _DIGIT_SEQ's deliberate (?<![\w,.])
#   lookbehind (d27543e) is untouched -- "x 05" now reaches the digit register on both
#   sides where "x05" fell through to _INTEGER and int("05") lost the zero.
# ASCII digits only ([0-9], same narrowing as _D) and Latin letters only
# (_C_LETTER_CLASS): "0800α" keeps its accepted, disclosed divergence exactly as it is
# (Python's older _sep_after_spelled_digits separates, C stays fused), and "٣05" stays
# untouched on both sides -- this pass can see neither.
_DIGIT_LETTER_BOUNDARY = re.compile(
    rf"(?<=[0-9])(?=[{_C_LETTER_CLASS}])|(?<=[{_C_LETTER_CLASS}])(?=[0-9])")

# "/" and ":" -- see _symbols. Both are word-INTERNAL punctuation, and the G2P only peels
# punctuation from a token's EDGES, so an internal one is neither peeled nor spoken: the
# two sides fuse into one word and go to letter-to-sound, with the character itself
# silently dropped.
#
# "-" is deliberately NOT in this class. The G2P's hyphen rule distinguishes a keyboard
# echo ("b-a-ch") from a real compound ("gogledd-ddwyrain") and needs the hyphen intact;
# spacing it would break every Welsh compound.
#
# The G2P's own _PUNCT members now peel from token interiors (bangor_g2p._segment), so
# this class carries only the NON-_PUNCT symbols that fuse: "/" from an unverbalisable
# fraction, ":" from an out-of-range time, and "*" -- which has no approved spoken word
# ("lluosi" is approved only for x/× between digits, and NORMALIZATION.md's deferred
# item 10 still owns the symbol registers), so the space is the conservative floor:
# the two sides are at least heard as two words. "+"/"="/"@" have approved words and
# are verbalised above instead.
_FUSING_PUNCT_BETWEEN_WORDS = re.compile(
    rf"(?<=[{_C_WORD_CLASS}])[/:*](?=[{_C_WORD_CLASS}])")


def _symbols(text: str) -> str:
    text = re.sub(r"(?<= )\+(?= )", "plws", text)
    text = re.sub(r"(?<= )=(?= )", "yn hafal i", text)
    text = re.sub(r"(?<= )@(?= )", "at", text)
    # The same three, LETTER-ADJACENT ("a+b", "a=b", "a@b") -- FOLLOWUPS section G's
    # fusion class again: unspoken, the symbol vanished at the phone layer and its two
    # sides fused into one LTS nonword. The words are the already-approved registers
    # above (owner wordings, 2026-07-28), so nothing new is invented -- only the
    # context widens. Both sides must be word characters: "C++", "A+" and "A+ grade"
    # stay codes (no word char after), exactly as before. _C_WORD_CLASS, not \w, for
    # the usual Latin-only C-mirror reason.
    text = re.sub(rf"(?<=[{_C_WORD_CLASS}])\+(?=[{_C_WORD_CLASS}])", " plws ", text)
    text = re.sub(rf"(?<=[{_C_WORD_CLASS}])=(?=[{_C_WORD_CLASS}])", " yn hafal i ", text)
    text = re.sub(rf"(?<=[{_C_WORD_CLASS}])@(?=[{_C_WORD_CLASS}])", " at ", text)
    # A "/" left BETWEEN TWO WORD CHARACTERS becomes a space. How to SAY "/" is still an open
    # convention (docs/NORMALIZATION.md deferred item 10) and BTC is silent on it, so
    # nothing is invented here -- but leaving the character in place was not "unhandled",
    # it was corrupting. The G2P has no "/" token and does not treat it as a boundary, so
    # the two sides fused into one word and went to letter-to-sound as a nonword:
    #
    #     1/20   -> "un/ugain"   -> y | n yy | g ai n     ("y-nyy-gain")
    #     1/100  -> "un/cant"    -> y ng | k a n t        ("yng cant")
    #     5/100  -> "pump/cant"  -> p y m | p k a n t     ("pym-pkant")
    #
    # i.e. silent garbage audio with a 200, the same failure shape as the U+00B7 deletion.
    # A space is the conservative floor: the two numbers are at least heard as two numbers.
    # It is NOT a fraction reading -- _FRACTION handles the denominators it can verbalise
    # and bails out for the rest, which is why anything reaches here at all.
    text = _FUSING_PUNCT_BETWEEN_WORDS.sub(" ", text)
    return text


_ACRONYM = re.compile(r"\b[A-Z0-9]{2,}\b")
_PERCENT = re.compile(r"([0-9][0-9,]*)\s*%")
_DECIMAL = re.compile(r"([0-9]+)\.([0-9]+)")
# ASCII, like the two patterns above and for the same reason (see `_D`): this is where
# a digit run that the sequence patterns did not claim lands, so if its digit class were
# wider than theirs the crash would simply move here -- `int("0٣٣")` is 33, which C,
# reading the ASCII "0" and dropping the rest, never says.
_INTEGER = re.compile(_D + r"[0-9,]*")
_AMPERSAND = re.compile(r"&\s*([A-Za-zÀ-ÿ])")

# Characters that GLUE their neighbours into a nonword when unhandled. Dropping one silently
# is worse than reading it: "5+3" normalised to "pump+tri", the "+" is not a phone so it
# vanished, and the model heard the single nonword "pumptri" for LTS to guess at. Likewise
# "2x3" -> "dauxtri" -> "docstri" and "5°C" -> "pump°c" -> "pumpc".
# Wording from the owner, 2026-07-28: "Pump plws tri", "dau lluosi tri", "Pump gradd celsiws".
# Note the Welsh spelling "celsiws", not "Celsius".
# --- emails and web addresses -----------------------------------------------------------
# Unread before this. "post@bangor.ac.uk" reached the phone layer intact, where "@" IS a
# symbol in the Bangor inventory -- the SCHWA -- so it was read as a vowel and the address
# came out as gibberish. Wording from the owner, 2026-07-28:
#     post@bangor.ac.uk  ->  "post at bangor dot ac dot wc"
# So "@" is "at", "." is "dot", and a label is read as a WORD rather than spelled out --
# "ac" and "wc" are syllables, not letter names. "wc" is the owner's rendering of ".uk";
# spelling it "u" + "cê" would be both longer and less like how it is said.
_EMAIL_OR_URL = re.compile(
    r"\b(?:[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"      # an address
    r"|(?:www\.|https?://)[A-Za-z0-9.-]+\.[A-Za-z]{2,}(?:/\S*)?)")   # a URL
# Labels whose spoken form is not simply the letters. Only the ones the owner gave; any other
# label is read as written and the phone layer treats it as an ordinary word.
# Labels whose spoken form is not simply the label read as a word.
#   "uk" -> "wc", the owner's rendering of ".uk".
#   "www" -> spelled letter by letter. Owner 2026-07-28: "We should fix www". Read as a
#     word it is unpronounceable, and the "·" separator is what the acronym pass already
#     uses to make the G2P name each letter (BBC -> "b·b·c"), so this needs no new
#     machinery -- it routes into the same letter-naming path.
_URL_LABEL = {"uk": "wc", "www": "w·w·w"}


def _email_url_repl(m: re.Match) -> str:
    t = m.group(0)
    for pre in ("https://", "http://"):
        if t.lower().startswith(pre):
            t = t[len(pre):]
    parts = []
    for chunk in t.replace("@", " at ").split():
        if chunk == "at":
            parts.append("at")
            continue
        labels = [c for c in chunk.split(".") if c]
        parts.append(" dot ".join(_URL_LABEL.get(l.lower(), l) for l in labels))
    return " ".join(parts)


# --- Roman numerals ---------------------------------------------------------------------
# "Pennod IV" spelled out as letters ("pennod i·v"). Owner 2026-07-28: "Penod pedwar" -- the
# CARDINAL. Deliberately narrow, because Roman numerals are ambiguous with real words and
# with initials: "I" is a pronoun in English and "MIX", "DID", "MILL" are words. So this
# fires only on a numeral of TWO OR MORE characters that is a well-formed Roman number, and
# only when it is not part of a longer token. A single "I"/"V"/"X" is left alone.
# Match the RUN and validate in code. The first attempt built the whole grammar into the
# pattern -- M{0,3}(?:CM|CD|D?C{0,3})... -- and every group in that is optional, so it
# happily matched the EMPTY STRING at a word start. _roman_repl then got "" , summed to 0,
# and inserted num_to_welsh(0): "DID" came out as "serodid". A regex that can match nothing
# is the wrong tool for this; validating a captured token is not.
_ROMAN = re.compile(r"\b[MDCLXVI]{2,}\b")
_ROMAN_VALUE = {"M": 1000, "D": 500, "C": 100, "L": 50, "X": 10, "V": 5, "I": 1}
# Words that are also strings of Roman letters. Without this "MIX" reads "mil naw" and "DID"
# reads "pum cant naw deg naw". Upper case only, so ordinary lower-case words never reach the
# pattern; this list is for genuine all-caps text and initials.
_ROMAN_NOT = {"MIX", "DID", "MILL", "DIM", "MI", "DI", "LI", "CI", "MC", "DC", "CD", "ID",
              "DILL", "CILL", "MILI", "LID", "LIM", "MIL"}


def _roman_value(t: str) -> int | None:
    """The value of a CANONICAL Roman numeral, or None if `t` is not one.

    Canonical by round-trip: converted to an integer and back, it must come out identical.
    That is what rejects "IIII", "VV", "IC" and "XXXX" without a second grammar to maintain,
    and it is why the value function is the validator too.
    """
    total, prev = 0, 0
    for ch in reversed(t):
        v = _ROMAN_VALUE[ch]
        total += -v if v < prev else v
        prev = max(prev, v)
    if not 1 <= total <= 3999:
        return None
    out, n = [], total
    for value, sym in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"),
                       (90, "XC"), (50, "L"), (40, "XL"), (10, "X"), (9, "IX"),
                       (5, "V"), (4, "IV"), (1, "I")):
        while n >= value:
            out.append(sym)
            n -= value
    return total if "".join(out) == t else None


# A Roman numeral after a PERSONAL NAME is a regnal number and takes the ORDINAL with its
# article: owner 2026-07-28, "Elisabeth yr ail is correct". After a structural noun it is a
# plain cardinal, which the same owner confirmed for "Pennod IV" -> "pennod pedwar". Both
# behaviours are wanted, so the two have to be told apart.
#
# There is no reliable signal for "is this a personal name", so the DEFAULT is the ordinal and
# the exception is a list of the structural nouns that number their parts. That vocabulary is
# small and nearly closed, where the set of names is not -- listing names instead would fail
# on the first monarch nobody thought of, which is the worse failure. An unlisted structural
# noun reads "dosbarth yr ail" rather than "dosbarth dau": wrong, but not gibberish, and one
# entry away from right.
_ROMAN_STRUCTURAL = {
    "pennod", "rhan", "cyfrol", "adran", "atodiad", "llyfr", "tabl", "ffigur", "cam",
    "gwers", "uned", "rhif", "fersiwn", "dosbarth", "categori", "lefel", "cyfnod",
    "chapter", "part", "volume", "section", "appendix", "book", "table", "figure",
}


def _roman_repl(m: re.Match) -> str:
    t = m.group(0)
    if t in _ROMAN_NOT:
        return t
    v = _roman_value(t)
    if v is None:
        return t
    prev = re.search(r"([A-Za-zÀ-ÿ'\u2019]+)\s*$", m.string[:m.start()])
    if prev and prev.group(1).lower() in _ROMAN_STRUCTURAL:
        return num_to_welsh(v)
    if v in _ORDINAL:
        # Masculine ordinal plus the article, exactly as the date path builds a day-of-month:
        # "yr" before a vowel or h, else "y". "Harri VIII" -> "harri yr wythfed".
        ordw = _ORDINAL[v][0]
        art = "yr" if ordw[0] in _ART_VOWELS else "y"
        return f"{art} {ordw}"
    return num_to_welsh(v)      # past the ordinal table: no regnal number goes this high


_MATH_OPS = [
    (re.compile(r"(?<=[0-9])\s*\+\s*(?=[0-9])"), " plws "),
    (re.compile(r"(?<=[0-9])\s*[xX×]\s*(?=[0-9])"), " lluosi "),
]
# Degree symbol. "gradd" alone for a bare degree, and the scale named when it is given. The
# scale letter is consumed so it cannot fall through to the acronym pass and be spelled out.
_DEGREE = [
    (re.compile(r"(?<=[0-9])\s*°\s*[Cc]\b"), " gradd celsiws"),
    (re.compile(r"(?<=[0-9])\s*°\s*[Ff]\b"), " gradd fahrenheit"),
    (re.compile(r"(?<=[0-9])\s*°"), " gradd"),
]

# --- emoji ------------------------------------------------------------------------------
# Emoji were DROPPED silently: "Da iawn 👍" read "da iawn" and the emoji contributed nothing.
# Owner 2026-07-28: they should be read.
#
# THE NAMES COME FROM THE piper-cy VOICE, like the phone-number rule. espeak-ng's cy voice
# already carries a full Welsh emoji set (CLDR-derived), and "espeak-ng -v cy -q -X" prints the
# replacement as WORDS ("Replace: ❤   calon goch"), so the table is extracted rather than
# translated -- 1424 entries of existing, idiomatic Welsh: "wyneb â dagrau hapusrwydd",
# "cacen pen-blwydd", "penglog ac esgyrn croes", "enfys".
#
# The sweep was deliberately restricted to the genuine emoji blocks. A first pass over a wider
# range pulled in espeak's ordinary symbol dictionary, which is not emoji and is partly
# ENGLISH -- "+" -> "plus", "₨" -> "rupee" -- and would have regressed the "plws" decision
# made hours earlier. The extractor asserts zero English-word leakage.
#
# NOT hashed into data_version: that covers only the four files in _DICT_ORDER, which live in
# data/geiriadur-ynganu-bangor/. This table is beside them, not among them, so it needs no
# model-config bump. Asserted in the tests.
# Beside this module's own data dir. bangor_g2p has _DEFAULT_DATA but importing it here
# would invert the dependency -- welsh_normalize is the lower layer and knows nothing about
# the G2P -- so the path is derived locally from __file__.
_EMOJI_TSV = Path(__file__).resolve().parent / "data" / "emoji_cy.tsv"


def _load_emoji(path: Path) -> dict:
    if not path.exists():
        raise RuntimeError(
            f"Package data file is missing: {path}\n"
            f"The techiaith-g2p installation is incomplete."
        )
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise RuntimeError(
            f"Package data file is empty: {path}\n"
            f"The techiaith-g2p installation is incomplete."
        )
    table = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        cps, _, name = line.partition("\t")
        if not name:
            continue
        table["".join(chr(int(c, 16)) for c in cps.split())] = name
    return table


_EMOJI = _load_emoji(_EMOJI_TSV)
# U+FE0F (variation selector-16) and U+200D (zero-width joiner) are presentation marks, not
# content: "❤️" is "❤" plus FE0F and must find the same name. Stripped before lookup so the
# table needs one entry per emoji rather than one per encoding.
_EMOJI_SKIP = "\ufe0f\u200d\ufe0e"
_EMOJI_SKIP_MAP = {ord(c): None for c in _EMOJI_SKIP}
# U+E0020-U+E007F, the TAG block. Used to build the national-flag sequences
# ("🏴" + "gbwls" + cancel = the Welsh flag). espeak does NOT know these -- it falls back to
# the bare "🏴", "chwifio baner ddu", and even leaks an English "black flag" -- so the three
# UK national flags are the ONLY hand-written entries in an otherwise extracted table:
#   baner Cymru, baner yr Alban, baner Lloegr.
# For a Welsh TTS, the Welsh flag reading "waving black flag" was the wrong default.
_TAG_CHARS = re.compile("[\U000e0020-\U000e007f]")
# Longest first, so a two-codepoint flag is matched before either half of it.
_EMOJI_RE = re.compile("|".join(re.escape(k) for k in
                                sorted(_EMOJI, key=len, reverse=True))) if _EMOJI else None


def _emoji_repl(m: re.Match) -> str:
    # Spaces on BOTH sides: an emoji sits directly against a word often enough ("Da iawn👍")
    # and without them the name would glue to it, the same nonword failure the symbol passes
    # were fixed for. The whitespace collapse at the end of normalize tidies the rest.
    return " " + _EMOJI[m.group(0)] + " "


# --- digit SEQUENCES (phone numbers, account numbers) vs digit QUANTITIES ---------------
#
# A phone number is not a quantity, and reading it as one destroys it: "01248 382000" read
# "un mil dau gant pedwar deg wyth tri chant wyth deg dau mil", and the LEADING ZERO was
# silently gone before anything could notice, because int("01248") is 1248.
#
# THE RULE COMES FROM THE piper-cy VOICE. espeak-ng's cy voice, which the other Piper voice
# on this service uses, reads a digit run digit-by-digit exactly when it starts with a zero,
# and as a cardinal otherwise -- verified against espeak-ng 1.50 in the running container:
#
#     123    -> "cant dau ddeg tri"      (cardinal)
#     0123   -> "nul un dau tri"         (digit by digit)
#     0800   -> "nul wyth nul nul"
#     007    -> "nul nul saith"
#
# A leading zero is the author saying "these are digits, not an amount", and it is the only
# signal in the text that says so. NOT A REGRESSION, and worth recording: 601be9c, the ref
# that ran in production for days, read phone numbers exactly as badly. Of 47 tricky inputs
# compared across the two refs, 5 differed and every one was a deliberate decision.
#
# We DO NOT copy espeak's word for the digit. It says "nul", which is not standard Welsh for
# zero; the owner chose "dim" (2026-07-28), the way a Welsh speaker reads a phone number
# aloud and the counterpart of English "oh". "sero", which the decimal pass uses for a bare
# 0, was the alternative and was rejected as too heavy six times in a row.
_DIGIT_NAMES = {"0": "dim", "1": "un", "2": "dau", "3": "tri", "4": "pedwar",
                "5": "pump", "6": "chwech", "7": "saith", "8": "wyth", "9": "naw"}
# Citation forms, unreduced: an isolated digit is not followed by a noun, so the connected
# forms ("pum", "chwe") that BTC gives for pre-nominal position do not apply here.

# A UK phone number: a leading-zero group, then 1-3 further groups, 9-11 digits in total.
# The whole thing reads digit-by-digit, not just its first group -- half a phone number read
# as digits and the rest as cardinals ("dim un dau pedwar wyth tri chant wyth deg dau mil")
# is no more usable than the original. The digit total is what distinguishes a phone number
# from prose that merely starts with a zero.
# The optional parentheses are the "(01248) 382000" style: a bare \b0... pattern stops at
# the ")" and leaves the rest to be read as a cardinal, which is WORSE than leaving the
# whole number alone -- half of it then sounds like an amount ("... tri chant wyth deg dau
# mil"). The separator class holds space, NBSP and hyphen: NBSP because web copy is full of
# it, and every other \s in this file is Unicode-aware for the same reason.
# `_D` not `\d` for every digit these two patterns CONSUME -- see the digit-class note at the
# top of the file for why, and for what the difference cost.
# The lookbehinds deliberately keep `\d`, and that asymmetry is not an oversight: a lookbehind
# is a GUARD, so narrowing it would widen what matches. `(?<![\d,.])` currently refuses a run
# preceded by any Unicode decimal digit; `(?<![0-9,.])` would let "٣05" start a sequence here.
# Conservative is the right side to err on for a guard, so it stays.
# Not every pass in this file was narrowed: `_DECIMAL`, `_CURRENCY`, `_PERCENT` and
# `_DATE_MONTH` still use `\d`, so "٣.٣", "£٣", "٣%" and "٣ Ionawr" remain Python/C divergent.
# Pre-existing, measured, and recorded in docs/FOLLOWUPS.md section G rather than fixed here.
_PHONE = re.compile(r"(?<![\d,.])\(?\b0" + _D + r"{1,4}\)?"
                    r"(?:[  -]?" + _D + r"{2,4}){1,3}(?!" + _D + ")")
# Any other leading-zero run: "007", "0044", an extension. Two digits minimum, so a bare
# "0" still reads "sero" through the ordinary number path.
# (?<![\d,.]) on BOTH patterns, and it is load-bearing: without it "\b0\d+\b" matched the
# "000" GROUP of "1,000" -- there is a word boundary after the comma -- and turned "un mil"
# into "un dim dim dim". The parity corpus caught it on the first regeneration, which is
# exactly what that corpus is for. A leading zero only means "sequence" at the START of a
# number: never after a digit, a thousands comma or a decimal point.
# (?<![\w,.]) not (?<![\d,.]): \w so a run INSIDE a word is left alone. With the looser
# class "a007" became "adim dim saith" and "x0800" became "xdim wyth dim dim", while C
# (whose guard tests word_before) correctly left both -- a C/Python divergence the
# differential caught. \w also matches Unicode letters, the same set as C's cp_is_word.
# (?!_D) not \b: the run ends where the DIGITS end, not where a word ends. With \b, "0800x"
# failed to match at all -- 0->x is word-to-word so there is no boundary -- and fell through
# to _INTEGER, where int("0800") is 800 and both leading zeros vanished. The lookbehind stays
# \w so a run inside a word is still left alone (d27543e); only the trailing side changes.
_DIGIT_SEQ = re.compile(r"(?<![\w,.])0" + _D + r"+(?!" + _D + ")")


def _spell_digits(s: str) -> str:
    """Every digit in `s` as its own word; anything else in the run is dropped.

    `_norm_digit_value`, not `str.isdigit()`: the name is looked up BY VALUE, so a character
    this module's digit class does not recognise cannot reach `_DIGIT_NAMES` at all. It used
    to be `c.isdigit()` against a dict keyed by ASCII characters -- host-Unicode-wide test,
    ASCII-only table -- and `_DIGIT_SEQ`'s `0\\d+` duly fed it "0٣٣", which raised
    KeyError '٣'. Also stronger than a plain `"0" <= c <= "9"`: the pairing of value to word
    is now explicit rather than implicit in the key spelling.
    """
    return " ".join(_DIGIT_NAMES[str(v)] for v in map(_norm_digit_value, s) if v >= 0)


_LATIN_TAIL = re.compile(f"[{_C_LETTER_CLASS}]")


def _sep_if_latin_tail(out: str, m: re.Match) -> str:
    """Append one space to `out` if the character right after the match is a Latin letter
    or "_", so the verbalised replacement stays a separate word from what follows.

    The digit/letter splitter (see normalize()) cannot reach these: by the time it runs,
    the pass that owns the digits has already glued its REPLACEMENT to the tail ("£5x" ->
    "pum puntx" -- letters now, no boundary left). So the two passes that both run before
    the splitter AND write letter-adjacent replacements add the separator themselves.

    Latin-only (_C_LETTER_CLASS), NOT str.isalpha(): _sep_after_spelled_digits below keeps
    its wider Unicode class and its accepted divergence (FOLLOWUPS section G, "0800α");
    new separator sites must not widen that gap, so this one tests exactly what C's
    digit_seq_sep tests."""
    tail = m.string[m.end():m.end() + 1]
    return out + " " if tail and _LATIN_TAIL.match(tail) else out


def _sep_after_spelled_digits(spelled: str, m: re.Match) -> str:
    """Append one space to `spelled` if the character right after the match is a letter
    or "_", so the verbalised run stays a separate word from whatever follows.

    Without it "0800x" becomes "dim wyth dim dimx" -- the verbalised number fused into the
    letters, which the G2P then hands to LTS as one nonword. Same class as the
    word-internal punctuation fusion in FOLLOWUPS.md section G. Shared by _digit_seq_repl
    and _phone_repl: a leading-zero run reads digit by digit either way, and the "does it
    need separating from what follows" question does not depend on which of the two
    patterns happened to claim it. (It used to: _phone_repl had none of this and every
    9-11-digit phone-shaped run FUSED into a following letter -- "0800123456x" ->
    "...pump chwechx" -- while the same digits at length 8 or 12 correctly separated.
    Found 2026-07-29 during Task 4's C-port review, because the C/Python differential
    corpus has no leading-zero run abutting a letter at exactly the UK phone lengths.)
    """
    tail = m.string[m.end():m.end() + 1]
    return spelled + " " if tail and (tail.isalpha() or tail == "_") else spelled


def _percent_repl(m: re.Match) -> str:
    """"N%" -- and "50%x" stays "pum deg y cant x": the "%" sits between the digits and
    the letter, so the splitter never sees a digit|letter boundary there. Second of the
    two pre-splitter separator sites (see _sep_if_latin_tail)."""
    return _sep_if_latin_tail(num_to_welsh(int(m.group(1).replace(",", ""))) + " y cant", m)


def _digit_seq_repl(m: re.Match) -> str:
    """Spell the run, and keep it a separate word from whatever follows."""
    return _sep_after_spelled_digits(_spell_digits(m.group(0)), m)


def _phone_repl(m: re.Match) -> str:
    # Counted with the same digit class the pattern matched on (`_norm_digit_value`, see
    # `_D`), so "9 to 11 digits" means the same thing to the test as it does to the match.
    digits = [c for c in m.group(0) if _norm_digit_value(c) >= 0]
    if not 9 <= len(digits) <= 11:
        return m.group(0)      # not a phone shape: leave it to _DIGIT_SEQ / _INTEGER
    return _sep_after_spelled_digits(_spell_digits(m.group(0)), m)


def _pound_magnitude_token(tok: str, text: str, start: int) -> bool:
    """True for the "5M" of "£5M": a currency amount whose magnitude suffix happens to
    be upper case, so [A-Z0-9]{2,} claims it as a code before _CURRENCY ever sees it.

    Without this the case-insensitivity of _CURRENCY's suffix is only half real —
    "£5m" says five million pounds while "£5M", which the same headline writes, says
    "£pump m" (the amount spelled as a number, "M" as a letter, £ left dangling). The
    test is deliberately narrow: digits, then exactly one magnitude suffix, and the £
    (with at most the single space _CURRENCY itself allows) directly before. "£5MB"
    and a bare "5M" are still codes. A comma inside the amount already breaks the
    [A-Z0-9] run, so "£1,500M" is out of reach here — the lower-case form is not."""
    for suf in _MAGNITUDE_ZEROS:
        if len(tok) > len(suf) and tok[-len(suf):].lower() == suf and tok[:-len(suf)].isdigit():
            break
    else:
        return False
    before = text[:start]
    return before.endswith("£") or before.endswith("£ ")


_ACRONYM_CLOCK_MARKERS = ("AM", "PM", "YB", "YP", "YH")


def _clock_marker_token(tok: str, text: str, start: int) -> bool:
    """True for the "7PM" of an upper-case clock form: digits plus a bare marker, which
    [A-Z0-9]{2,} would otherwise claim as a code before the time passes ever run --
    "7PM" spelled out as "saith p·m", and "3:00PM" collapsing outright because the
    acronym pass ate its "00PM". Same stand-aside shape as _pound_magnitude_token.

    Two admissions, mirroring pound's narrowness. A 1-2 digit run <= 23 is a colonless
    hour ("7PM", "10YB" -- and "00PM", the minute fragment of "3:00PM", is 0). A run of
    24-59 stands aside only as a minute field: exactly two digits, [0-5]\\d, directly
    after "digit:" or "digit." ("3:45PM", "7.30PM"). Everything else stays a code:
    standalone "PM" (the Prime Minister) has no digits, "45PM" alone fails both tests,
    and the UPPERCASE DOTTED forms ("7P.M.") never reach here at all -- the [A-Z0-9]
    token there is "7P", not marker-shaped, so they stay spelled out: a recorded
    limitation, identical in both implementations."""
    if len(tok) < 3 or tok[-2:] not in _ACRONYM_CLOCK_MARKERS:
        return False                         # standalone "PM" (no digits) stays a code
    digits = tok[:-2]
    if not digits.isdigit() or len(digits) > 2:
        return False
    if int(digits) <= 23:
        return True                          # a colonless hour: "7PM", "10YB", "00PM"
    before = text[:start]                    # minute field 24-59: "45PM" in "3:45PM"
    return (len(digits) == 2 and digits[0] in "012345"
            and len(before) >= 2 and before[-1] in ":." and before[-2].isdigit())


# --- the acronym vocabulary gate ---------------------------------------------------------
# Letter-spelling is an OOV fallback, not the reading of every all-caps token: an all-caps
# token whose lowercase form the G2P's own dictionaries know is a real word (or a lexicalised
# acronym -- the dictionaries carry "bbc", "nato", "dvla" with their spoken forms), and the
# right reading is the word itself. Only a token the dictionaries do NOT know keeps the
# letter-by-letter spell-out (HMS, WJEC, USB). Decided 2026-08-25; before this, "ADRODDIAD"
# alone in a sentence was spelled a·d·r·o·d·d·i·a·d because _deshout's >=2-caps-words
# threshold never fires on a single word.
#
# Membership rule, mirrored EXACTLY by cyp_normalize_load_vocab in c/cy_normalize.c: a
# dictionary line's leading run of ASCII letters, length >=2, terminated by space, tab, \r
# or end-of-line, lowercased. ASCII-only on purpose -- _ACRONYM itself is [A-Z0-9]{2,}, so
# no other headword can ever be queried. Digit-bearing tokens (S4C, A55) never reach the
# gate: they are codes, unpronounceable as words, and stay with the speller.
_VOCAB_DICTS = ("bangordict.dict", "bangordict.xx.dict", "bangordict.en.dict", "cmudict.dict")
_VOCAB_HEADWORD = re.compile(r"[A-Za-z]{2,}(?=[ \t\r]|$)")
_ACRO_VOCAB: "set[str] | None" = None


def _acronym_vocab() -> "set[str]":
    """Lazy-loaded headword set from the packaged pronunciation dictionaries.

    Loaded here rather than shared with BangorLexicon because the normalizer is
    standalone (no id map, no phone validation): membership means "the dictionaries
    name this word", not "this word survived phone-id mapping"."""
    global _ACRO_VOCAB
    if _ACRO_VOCAB is None:
        base = Path(__file__).parent / "data" / "geiriadur-ynganu-bangor"
        vocab = set()
        for name in _VOCAB_DICTS:
            for line in (base / name).read_text(encoding="utf-8").splitlines():
                hw = _VOCAB_HEADWORD.match(line)
                if hw:
                    vocab.add(hw.group(0).lower())
        _ACRO_VOCAB = vocab
    return _ACRO_VOCAB


def _spell_acronym(m: re.Match) -> str:
    tok = m.group(0)
    if tok.isdigit():                        # pure number -> leave to number pass
        return tok
    if _pound_magnitude_token(tok, m.string, m.start()):
        return tok                           # "£5M" belongs to _CURRENCY, not here
    if _clock_marker_token(tok, m.string, m.start()):
        return tok                           # "7PM" belongs to the time passes, not here
    if not any(c.isdigit() for c in tok) and tok.lower() in _acronym_vocab():
        return tok.lower()                   # a known word merely capitalised: read it
    caps = sum(c.isupper() for c in tok)
    # An acronym needs >=2 caps (BBC, HMS) — or one cap plus a digit, which covers
    # road/format codes read letter-by-letter (A55 -> "a pum deg pump", 3D -> "tri d").
    if caps < 2 and not (caps >= 1 and any(c.isdigit() for c in tok)):
        return tok
    parts: list = []       # space-separated output pieces, in source order
    letters: list = []     # the run of consecutive letters being accumulated
    digits = ""

    def flush_letters():
        if letters:
            parts.append(ACRONYM_JOIN.join(letters))
            letters.clear()

    for c in tok:
        if c.isdigit():
            flush_letters()                  # a digit ends the letter run (S4C -> "s pedwar c")
            digits += c                      # consecutive digits read as one number (A55 -> pum deg pump)
            continue
        if digits:
            parts.append(num_to_welsh(int(digits)))
            digits = ""
        letters.append(c.lower())
    flush_letters()
    if digits:
        parts.append(num_to_welsh(int(digits)))
    return " ".join(parts)


def _decimal_repl(m: re.Match) -> str:
    """BTC excepts "rhifau cyn ac ar ol pwyntiau degol" from the vigesimal rule -- numbers
    BEFORE AND AFTER a decimal point are decimal. The guide's own example is
    "20.15" -> "dau ddeg pwynt un pump", and it names "ugain pwynt pymtheg" as wrong."""
    whole = _cardinal_dec(int(m.group(1)))
    frac = " ".join(_UNITS[int(d)] if int(d) else "sero" for d in m.group(2))
    return f"{whole} pwynt {frac}"


def _amp_repl(m: re.Match) -> str:
    nxt = m.group(1)
    conj = "ac" if nxt.lower() in _VOWELS else "a"
    return f"{conj} {nxt}"


def _is_caps_word(w: str) -> bool:
    """A fully-uppercase token with >=2 letters (candidate acronym / shouted word).

    Tokens containing digits (S4C, A55) are never "shouting" — they are codes that
    the acronym pass must still see in caps, so they don't count here and don't get
    lower-cased by _deshout."""
    return w.isupper() and sum(c.isalpha() for c in w) >= 2 and not any(c.isdigit() for c in w)


def _deshout(text: str) -> str:
    """Lower-case an ALL-CAPS / shouted phrase so it is read as words, not spelled out.

    An isolated all-caps token in normal-case text goes to the acronym pass instead —
    which since 2026-08-25 spells it by letter only when the dictionaries do not know
    it as a word (see _acronym_vocab). But a run of mostly-uppercase words is emphasis
    ("CROESO I GYMRU"), not a string of acronyms — folding the whole run here reads
    every word as a word, in-vocabulary or not, which is what shouting means. Heuristic:
    if the caps words are >=2 AND at least half of the alphabetic words, treat the whole
    thing as shouted and lower-case those words before the acronym pass. A single
    acronym (minority) is left alone."""
    words = text.split()
    caps = [w for w in words if _is_caps_word(w)]
    alpha = [w for w in words if any(c.isalpha() for c in w)]
    if len(caps) >= 2 and 2 * len(caps) >= len(alpha):
        return " ".join(w.lower() if _is_caps_word(w) else w for w in words)
    return text


# --- fractions and units -------------------------------------------------------
# NOT from the verified reference set: docs/NORMALIZATION.md has no fraction or unit
# data. These forms are derived from standard Welsh mutation rules and are pending
# sign-off. docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md is the reviewable surface: it
# spells out all 115 forms (45 fractions, 70 units) for the native speaker to correct.
# The table in tests/test_normalize.py pins a SAMPLE of them (23 of the 115) plus the
# fall-through cases — enough to catch a broken rule, not enough to review the wording.

# hanner/traean/chwarter are irregular and displace the general pattern.
_FRACTION_SPECIAL = {(1, 2): "hanner", (1, 3): "traean", (1, 4): "chwarter"}

# Pre-nominal numeral forms. "rhan" is feminine, so 2/3/4 take feminine forms; pump
# and chwech reduce before a noun.
_FEM_BEFORE_NOUN = {1: "un", 2: "dwy", 3: "tair", 4: "pedair", 5: "pum",
                    6: "chwe", 7: "saith", 8: "wyth", 9: "naw", 10: "deg"}
# Feminine numerals after the preposition "o", which causes soft mutation.
# ch/s/n/w do not soft-mutate, so those forms are unchanged.
_FEM_AFTER_O = {1: "un", 2: "ddwy", 3: "dair", 4: "bedair", 5: "bump",
                6: "chwech", 7: "saith", 8: "wyth", 9: "naw", 10: "ddeg"}
_FRACTION = re.compile(r"\b([0-9]+)/([0-9]+)\b")


def _fraction_repl(m: re.Match) -> str:
    num, den = int(m.group(1)), int(m.group(2))
    if den == 0:
        return m.group(0)                       # leave a division by zero alone
    if (num, den) in _FRACTION_SPECIAL:
        return _FRACTION_SPECIAL[(num, den)]
    if den == 4 and num == 3:
        return "tri chwarter"
    if num not in _FEM_BEFORE_NOUN or den not in _FEM_AFTER_O or num >= den:
        return m.group(0)                       # outside 1-10, or improper: leave to the digit pass
    numerator = _FEM_BEFORE_NOUN[num]
    rhan = "ran" if num == 2 else "rhan"        # soft mutation after "dwy"
    return f"{numerator} {rhan} o {_FEM_AFTER_O[den]}"


# Units: (plain, soft, aspirate). Soft follows dau/dwy; aspirate follows tri/chwe and
# applies only to c/p/t, so units not starting with those repeat the plain form.
_UNITS_SPOKEN = {
    "km": ("cilomedr", "gilomedr", "chilomedr"),
    "kg": ("cilogram", "gilogram", "chilogram"),
    "cm": ("centimetr", "gentimetr", "chentimetr"),
    "mm": ("milimetr", "filimetr", "milimetr"),
    "m": ("metr", "fetr", "metr"),
    "g": ("gram", "ram", "gram"),
    "l": ("litr", "litr", "litr"),
}
_MASC_BEFORE_NOUN = {1: "un", 2: "dau", 3: "tri", 4: "pedwar", 5: "pum",
                     6: "chwe", 7: "saith", 8: "wyth", 9: "naw", 10: "deg"}
# The alternation is built from the table so the two cannot drift. "mm" is listed before
# "m", but that order is NOT what makes "5mm" millimetres — the trailing \b is: "m"
# matches first and is then rejected because a word char follows, and re backtracks into
# "mm" (the C port's alternation loop does the same by skipping a failed boundary). The
# order is belt-and-braces; the boundary is the rule. Both are pinned by the mm rows in
# tests/test_normalize.py.
_UNIT_ALT = "|".join(_UNITS_SPOKEN)
# The optional decimal part is a FIX, 2026-07-28. _UNIT runs before _DECIMAL (units have
# to claim their own digits first, the same reason currency does), so with an integer-only
# pattern "3.5kg" had its "5kg" eaten here and the orphaned "3." never reached _DECIMAL:
# the result was "tri.pum cilogram", and since "." is not a phone the model heard the
# NONWORD "tripum cilogram". Owner: "Tri pwynt pum cilogram".
_UNIT = re.compile(r"\b([0-9][0-9,]*(?:\.[0-9]+)?)\s?(" + _UNIT_ALT + r")\b")
# _UNIT's tail, anchored where a currency amount ends: see _currency_repl, which uses it
# to yield digits that the (now later) unit pass is entitled to.
_UNIT_TAIL = re.compile(r"\s?(?:" + _UNIT_ALT + r")\b")


# The connected forms, applied to the LAST word of a numeral phrase rather than looked up by
# value. A decimal numeral has no single value to look up: "3.5 kg" ends in "pump", which
# reduces before a noun exactly as a bare 5 would ("pum cilogram"). BTC's "Y ffurfiau cyswllt"
# gives pum (5), chwe (6) and can (100) "yn gyffredinol", so the rule is positional -- it is
# about the word that touches the noun, which is precisely what _reduce_cant already does for
# "cant". This is the same rule for the other two words in that list.
_CONNECTED_TAIL = {"pump": "pum", "chwech": "chwe"}


def _reduce_connected(numeral: str) -> str:
    """Trailing pump/chwech/cant -> pum/chwe/can, for a numeral directly before a noun."""
    head, _, last = numeral.rpartition(" ")
    if last in _CONNECTED_TAIL:
        return (head + " " if head else "") + _CONNECTED_TAIL[last]
    return _reduce_cant(numeral)


def _unit_repl(m: re.Match) -> str:
    raw = m.group(1).replace(",", "")
    if "." in raw:
        # Decimal + unit. No 2/3/6 mutation branch can apply -- the value is not 2, 3 or 6 --
        # and the numeral's TAIL takes the connected form: "3.5kg" -> "tri pwynt pum cilogram".
        whole, frac = raw.split(".", 1)
        words = _cardinal_dec(int(whole)) + " pwynt " + " ".join(
            _UNITS[int(d)] if int(d) else "sero" for d in frac)
        plain_u = _UNITS_SPOKEN[m.group(2)][0]
        return f"{_reduce_connected(words)} {plain_u}"
    n = int(raw)
    plain, soft, aspirate = _UNITS_SPOKEN[m.group(2)]
    numeral = _MASC_BEFORE_NOUN.get(n, _reduce_cant(num_to_welsh(n)))
    if n == 2:
        return f"{numeral} {soft}"
    if n in (3, 6):
        return f"{numeral} {aspirate}"
    # Through the same helper the pence path uses. What this actually buys is that
    # _SAITH_WYTH_SOFT is AUTHORITATIVE for units too: add a unit noun to that table and
    # "7 kg" changes, so the table alone decides which nouns mutate.
    #
    # It does NOT make removing this call visible -- no unit noun is in the table, so the
    # call is a no-op today and deleting it passes the whole suite. An earlier version of
    # this comment claimed otherwise. The negative half of the BTC rule is pinned by the
    # structural assertion in test_cant_punt_ceiniog_soft_mutate_after_saith_and_wyth
    # instead: no unit noun may appear in _SAITH_WYTH_SOFT.
    return f"{numeral} {_soft_after_saith_wyth(numeral, plain)}"


# ---------------------------------------------------------------------------
# Nasal mutation before "blynedd" / "blwydd".
#
# piper-lleol issue #1: "mae treiglad trwynol yn digwydd ar ol 10 (ac mae'r
# ffurf yn newid i 'deng') pan fo 'blynedd' neu 'blwydd' dan sylw e.e. 'deng mlynedd'
# a 'deng mlwydd oed'".
#
# This is a CLOSED IDIOM, not an instance of the decimal-vs-traditional register choice
# settled in issue #6. Nobody says "dau ddeg blynedd"; the numeral-plus-blynedd phrase
# keeps its traditional form, exactly as "deng munud" does in _MINUTE_STANDALONE. So the
# decimal decision does not reach in here and the two never conflict -- a numeral that
# reads "dau ddeg pump" on its own still reads "ugain mlynedd" in front of this noun.
#
# NOW BACKED BY THE BTC STYLE GUIDE, "Treiglo ai peidio": "Mae 'blwydd' a 'blynedd' yn
# treiglo'n drwynol ar ol pob rhifolyn ar wahan i 2, 3, 4 a 6." That is a general RULE
# where this table was a hand-enumerated list, and the two agree: every entry below is
# nasal except 2, 3, 4 and 6. The list stays a table rather than becoming a rule because
# each row also fixes the numeral's own form (deng, pymtheng, hanner can) and the 2/3/4/6
# exceptions still differ from each other -- 2 soft-mutates after the feminine "dwy",
# 3/4/6 leave the noun alone.
#
# The guide also records that grammarians DISAGREE about 6 ("6 blynedd" vs "6 mlynedd"),
# particularly in speech. We follow the guide's own exception list and leave 6 unmutated;
# flagged here because it is the one row the published source itself calls contested.
#
# CONFIRMED: the 10 row (quoted above); the nasal/no-nasal split for all rows
# (BTC, quoted above).
# STILL PROPOSED (docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md §6): the numeral forms
# themselves for 15/20/50/100 (pymtheng, ugain, hanner can, can), and the 1 row, which
# BTC's rule does not settle -- it names blwydd/blynedd, and for 1 the singular
# "blwyddyn" is the noun in play instead, so "un flwyddyn" comes from the singular rule
# ("Gyda ffigurau a rhifolion hyd at ddeg, defnyddir yr unigol"), not from this one.
#
# A number absent from the table falls through to the plain cardinal and an unmutated
# noun -- the pre-existing behaviour. That way an unlisted number can be wrong-but-plain,
# never wrong-and-confidently-mutated.
_BLYNEDD_NOUNS = {
    #  radical     nasal      soft
    "blynedd": ("mlynedd", "flynedd"),
    "blwydd":  ("mlwydd",  "flwydd"),
}
# n -> (numeral form, mutation applied to the noun)
_BLYNEDD_NUM = {
    1:   ("un",         "soft"),    # + singular noun, see _BLYNEDD_SINGULAR
    2:   ("dwy",        "soft"),
    3:   ("tair",       "none"),
    4:   ("pedair",     "none"),
    5:   ("pum",        "nasal"),
    6:   ("chwe",       "none"),
    7:   ("saith",      "nasal"),
    8:   ("wyth",       "nasal"),
    9:   ("naw",        "nasal"),
    10:  ("deng",       "nasal"),
    15:  ("pymtheng",   "nasal"),
    20:  ("ugain",      "nasal"),
    50:  ("hanner can", "nasal"),
    100: ("can",        "nasal"),
}
# "blynedd" is the after-a-numeral plural; one of them is the singular "blwyddyn".
# "blwydd" (as in "blwydd oed") has no separate singular.
_BLYNEDD_SINGULAR = {"blynedd": "flwyddyn"}
# Accepts the noun already mutated, so "10 mlynedd" in the source still gets its digits
# expanded to the correct "deng mlynedd" rather than a stranded "deg mlynedd".
# re.I because normalize() lowercases only at the END of the pipeline, so a
# sentence-initial "10 Blynedd o brofiad" reached this pass still capitalised and missed
# the rule entirely ("deg blynedd"). NOTE the numeric passes above (_UNIT in particular)
# have the same pre-existing gap -- "10 Km" does not match either -- deliberately left
# alone here rather than widened into an unreviewed change.
_BLYNEDD = re.compile(
    r"\b([0-9][0-9,]*)\s+(blynedd|mlynedd|flynedd|blwydd|mlwydd|flwydd)\b", re.I)


def _blynedd_repl(m: re.Match) -> str:
    n = int(m.group(1).replace(",", ""))
    written = m.group(2).lower()          # re.I above: match the table case-insensitively
    radical = next(r for r, forms in _BLYNEDD_NOUNS.items()
                   if written == r or written in forms)
    if n not in _BLYNEDD_NUM:
        numeral = num_to_welsh(n)
        # BTC "Treiglo ai peidio": "Mae 'blwydd' a 'blynedd' yn treiglo'n drwynol ar ol pob
        # rhifolyn ar wahan i 2, 3, 4 a 6" -- after EVERY numeral bar those four. The table
        # above covers the values it lists; this fallback covers the rest, and used to emit
        # the radical unmutated. Compound numerals take the plural instead (BTC's other
        # rule, see _counted_noun) so the nasal never applies to them, but the NON-compound
        # 11+ values fell between the two: 12, 18, 40, 60 and 80 read "deuddeg blynedd",
        # "deugain blynedd" and so on, with neither the plural nor the mutation.
        if n not in (2, 3, 4, 6) and not _is_compound_numeral(numeral):
            nasal, _soft = _BLYNEDD_NOUNS[radical]
            return f"{numeral} {nasal}"
        return _counted_noun(numeral, n, radical)
    numeral, mutation = _BLYNEDD_NUM[n]
    if n == 1 and radical in _BLYNEDD_SINGULAR:
        return f"{numeral} {_BLYNEDD_SINGULAR[radical]}"
    nasal, soft = _BLYNEDD_NOUNS[radical]
    noun = {"nasal": nasal, "soft": soft, "none": radical}[mutation]
    return f"{numeral} {noun}"


class WelshNormalizer:
    @staticmethod
    def num_to_welsh_public(n: int) -> str:
        """Cardinal verbaliser, for callers that need numbers without full normalization."""
        return num_to_welsh(n)

    def normalize(self, text: str) -> str:
        text = text.translate(_TYPOGRAPHIC)
        # Emoji first: their names are ordinary Welsh words and should go through every
        # pass below exactly as typed text would. Presentation marks are dropped before
        # the lookup so "❤" and "❤️" find the same name.
        if _EMOJI_RE is not None:
            text = _EMOJI_RE.sub(_emoji_repl, text.translate(_EMOJI_SKIP_MAP))
            # TAG characters AFTER matching, not before: they are PART of the tag-sequence
            # flags ("🏴" + gbwls + cancel), which are in the table and sort longest-first, so
            # stripping them early would destroy the very sequences that need them. Whatever
            # survives is a tag flag we have no name for, and would otherwise reach the phone
            # layer as raw codepoints.
            text = _TAG_CHARS.sub("", text)
        for rx, repl in _ABBREV:
            text = rx.sub(repl, text)
        text = _deshout(text)
        # ROMAN NUMERALS BEFORE _ACRONYM, which is [A-Z0-9]{2,} and would otherwise claim
        # "IV" as a code and spell it "i·v". After _deshout, so an all-caps sentence has
        # already been folded and only genuine capitals reach the pattern.
        text = _ROMAN.sub(_roman_repl, text)
        text = _ACRONYM.sub(_spell_acronym, text)
        text = _DATE_NUM.sub(_date_num_repl, text)
        text = _DATE_MONTH.sub(_date_month_repl, text)
        text = _ORDINAL_RE.sub(_ordinal_repl, text)
        text = _FRACTION.sub(_fraction_repl, text)
        # CURRENCY BEFORE UNIT, and the order is load-bearing. With _UNIT first, the unit
        # pass ate the digits out of a currency amount: "£5m" -> "£pum metr" (five metres,
        # £ left dangling), "£2.5m" -> "dwy bunt.pum metr", "mae £3m yn y gronfa" ->
        # "mae £tri metr yn y gronfa". Currency has to claim its own amount, decimal and
        # all, before anything else reads the digits. _currency_repl yields back to _UNIT
        # for any amount a unit would legitimately follow (see _UNIT_TAIL there), so
        # "£5kg" still reads as it always did.
        text = _CURRENCY.sub(_currency_repl, text)
        text = _UNIT.sub(_unit_repl, text)
        # Before _INTEGER, which would otherwise turn "10 blynedd" into a flat
        # "deg blynedd" and lose both the nasal mutation and the "deng" form.
        text = _BLYNEDD.sub(_blynedd_repl, text)
        text = _TIME.sub(_time_repl, text)
        # Emails and URLs BETWEEN the two clock passes, and the position is load-bearing
        # twice over. Their dots and @ must not be seen by any number or symbol pass ("@"
        # is the SCHWA in the phone inventory, so anything left of it is read as a vowel
        # rather than dropped). And they must run BEFORE _TIME_NOCOLON, mirroring C's
        # pass order (pass_email_url runs early there): "post@7pm.com" is an address
        # whose "7pm" is then read INSIDE the verbalised form -- identically in both
        # implementations. With the old order the colonless pass would eat the "7pm" out
        # of the RAW address and leave a bare "@" behind.
        text = _EMAIL_OR_URL.sub(_email_url_repl, text)
        # After email/URLs (above); before _PENCE, or "7p.m." is stolen back by the pence
        # rule the moment the colonless match is unavailable.
        text = _TIME_NOCOLON.sub(_time_repl, text)
        text = _PENCE.sub(_pence_repl, text)
        # The digit/letter splitter -- placement is load-bearing on both edges; the full
        # reasoning lives at _DIGIT_LETTER_BOUNDARY's definition. C mirror:
        # pass_digit_letter_split, at the same point in its driver.
        text = _DIGIT_LETTER_BOUNDARY.sub(" ", text)
        # Operators and the degree sign BEFORE EVERY number pass, so their operands are
        # still DIGITS when the lookarounds run. Placing them after _DECIMAL silently
        # broke "98.6°F": by then the text read "...pwynt chwech°F" and the (?<=\d)
        # lookbehind saw an "h". It also means no unverbalised character is left sitting
        # between two words for the phone layer to glue into a nonword.
        for rx, rep in _DEGREE:
            text = rx.sub(rep, text)
        for rx, rep in _MATH_OPS:
            text = rx.sub(rep, text)
        text = _PERCENT.sub(_percent_repl, text)
        text = _DECIMAL.sub(_decimal_repl, text)
        # DIGIT SEQUENCES BEFORE _INTEGER, and after the time/date/currency passes so a
        # "07:00" or "01/01/1980" is claimed by the pass that understands it first. _DECIMAL
        # is also already done, so "0.5" is "sero pwynt pump" and never reaches these.
        # _PHONE before _DIGIT_SEQ: the phone pattern spans the whole grouped number, and
        # _DIGIT_SEQ would otherwise consume its first group and leave the rest as cardinals.
        text = _PHONE.sub(_phone_repl, text)
        text = _DIGIT_SEQ.sub(_digit_seq_repl, text)
        text = _INTEGER.sub(lambda m: num_to_welsh(int(m.group(0).replace(",", ""))), text)
        text = _AMPERSAND.sub(_amp_repl, text)
        text = _symbols(text)
        text = text.lower()
        text = re.sub(r"\s+", " ", text).strip()
        return text


if __name__ == "__main__":
    wn = WelshNormalizer()
    for s in ["25", "2026", "50%", "3.14", "1,000", "BBC", "S4C", "e.e.", "Dr Jones",
              "Mae 234 o bobl yn y BBC"]:
        print(f"  {s!r} -> {wn.normalize(s)!r}")
