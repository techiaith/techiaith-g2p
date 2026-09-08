"""Tests for the Welsh text normalizer (Workstream P, task P2).

Cardinal cases are the VERIFIED worked examples from the reference data
(decimal register, standalone/masculine). RED until techiaith/g2p/welsh_normalize.py
exists and is correct.
"""
import sys
from pathlib import Path

from techiaith.g2p.welsh_normalize import num_to_welsh, WelshNormalizer

REPO = Path(__file__).resolve().parent.parent

# Verified concatenated-decimal cardinals (reference §1.4).
# VIGESIMAL, per the BTC style guide ("Degol ynteu ugeiniol": figures read as "ffurfiau
# clasurol neu ugeiniol", "ac un ar hugain" and not "a dau ddeg un"). This REPLACES the
# decimal values that previously carried the "verified reference" label; the owner ruled
# that BTC wins a conflict, and that the change is reversible.
#
# The rows marked (corroborated) are independently attested by data already in
# welsh_normalize.py -- _HOUR_TRAD (masculine 1-12), _MINUTE_TRAD (feminine 1-29, read
# masculine), _ORDINAL (1-31) -- and 21 is BTC's own worked example. The rest are DERIVED
# from the same rule and pending sign-off; the decades deugain/trigain/pedwar ugain and
# their joiners have no independent attestation in this repo at all.
# DECIMAL, the register chosen on issue #6 ("degol yn haws i bawb ei ddeall") and the
# one the owner confirmed after hearing the vigesimal alternative. The vigesimal forms these
# replace lasted one day; see welsh_normalize._two_digit for why they were reverted. The
# CLOCK is a separate register and stays traditional -- "10:25" is still
# "pump ar hugain munud wedi deg".
CARDINALS = {
    0: "sero",
    1: "un",
    2: "dau",
    3: "tri",
    4: "pedwar",
    5: "pump",
    6: "chwech",
    7: "saith",
    8: "wyth",
    9: "naw",
    10: "deg",
    11: "un deg un",
    12: "un deg dau",
    15: "un deg pump",
    16: "un deg chwech",
    18: "un deg wyth",
    20: "dau ddeg",
    21: "dau ddeg un",
    25: "dau ddeg pump",
    30: "tri deg",
    31: "tri deg un",
    40: "pedwar deg",
    41: "pedwar deg un",
    42: "pedwar deg dau",
    50: "pum deg",
    60: "chwe deg",
    61: "chwe deg un",
    70: "saith deg",
    80: "wyth deg",
    81: "wyth deg un",
    90: "naw deg",
    99: "naw deg naw",
    100: "cant",
    101: "cant un",
    110: "cant deg",
    111: "cant un deg un",
    200: "dau gant",
    234: "dau gant tri deg pedwar",
    500: "pum cant",
    999: "naw cant naw deg naw",
    1000: "un mil",
    1001: "un mil un",
    2000: "dwy fil",
    2026: "dwy fil dau ddeg chwech",
    1234: "un mil dau gant tri deg pedwar",
    10000: "deg mil",
    100000: "can mil",
    999999: "naw cant naw deg naw mil naw cant naw deg naw",
}

# (input, expected normalized text)
NORMALIZE = [
    ("25", "dau ddeg pump"),
    ("2026", "dwy fil dau ddeg chwech"),
    ("mae 100 o bobl", "mae cant o bobl"),
    ("50%", "pum deg y cant"),
    ("3.5", "tri pwynt pump"),
    ("3.14", "tri pwynt un pedwar"),
    # language decision (2026-07-26): "un" before mil/miliwn ("un mil", not bare "mil").
    ("1,000", "un mil"),
    ("ci & chath", "ci a chath"),
    ("ci & aderyn", "ci ac aderyn"),
    ("e.e.", "er enghraifft"),
    ("h.y.", "hynny yw"),
    ("ayb", "ac yn y blaen"),
    ("Dr Jones", "doctor jones"),
    # The acronym pass gates on the dictionary headword set (2026-08-25): an all-caps
    # token the dictionaries know — as a word (ADRODDIAD) or a lexicalised acronym with
    # its own spoken form (BBC, NATO) — reads as that word; only an OOV token spells out
    # as ACRONYM_JOIN-ed letters (the G2P names them, so the spelling is language-aware
    # there). Consecutive digits read as one number and break the join; digit-bearing
    # tokens (S4C, A55) are codes, never words, and always stay with the speller.
    ("BBC", "bbc"),                              # in cmudict: "bi bi si", not b·b·c
    ("NATO", "nato"),                            # in bangordict as a word
    ("ADRODDIAD", "adroddiad"),                  # a shouted single word is not an acronym
    ("HMS", "h·m·s"),                            # OOV: keeps the letter spelling
    ("WJEC", "w·j·e·c"),                         # OOV: keeps the letter spelling
    ("US", "us"),                                # ACCEPTED COLLISION: vocab word wins
    ("S4C", "s pedwar c"),
    ("S4C a'r BBC.", "s pedwar c a'r bbc."),     # _deshout must not swallow S4C; pence must not read "4c"
    ("A55", "a pum deg pump"),
    ("OK", "ok"),                                # in cmudict: read as the word
    # 1.3.1 gate (see welsh_normalize._VOCAB_DICTS_EN): short Welsh words read, unknown
    # pronounceable names read, listed initialisms and vowel-less codes still spell.
    ("CAU", "cau"), ("AGOR", "agor"), ("IAWN", "iawn"), ("WEDI", "wedi"),
    ("DWP", "d·w·p"), ("NHS", "n·h·s"),              # Welsh headwords that are initialisms: listed
    ("HMRC", "h·m·r·c"), ("GDPR", "g·d·p·r"),          # no vowel: spell
    ("HDMI", "h·d·m·i"), ("GCSE", "g·c·s·e"),          # vowel-bearing initialisms: listed
    ("README", "readme"), ("CHANGELOG", "changelog"), ("OFCOM", "ofcom"),   # unknown, pronounceable
    ("WHATSAPP", "whatsapp"), ("SPOTIFY", "spotify"), ("LOGIN", "login"),   # cmudict_native joins the pool
    ("ESTYN", "estyn"),                              # said as the word, so NOT listed
    ("OS", "os"), ("AR", "ar"),                      # two letters: English tables carry the letter names
    ("CI", "c·i"),                                   # two-letter Welsh-only headword: an initialism
    ("EU", "eu"),                                    # cmudict_native: "eu  ˈ ii j uu" -- the letter names
    ("Set up CI/CD", "set up c·i cd"),
    # a comma belongs to a number only when a digit follows (2026-09-07): the pause survives
    ("1, 1", "un, un"), ("Rhif 1, Rhif 2", "rhif un, rhif dau"), ("1,000, 2,000", "un mil, dwy fil"),
    ("£5, diolch", "pum punt, diolch"), ("1,,2", "un,dau"),          # two pauses collapse to one
    # a one-letter Welsh word beside an acronym token must stay its own token
    ("y BBC", "y bbc"),
    ("i BBC Cymru", "i bbc cymru"),
    ("BBC y dydd", "bbc y dydd"),
    ("y CD", "y cd"),                            # cmudict carries "cd" with letter-name phones
    ("Mae'r tywydd yn braf", "mae'r tywydd yn braf"),
    # typographic apostrophes fold to ASCII so clitics still hit the lexicon
    ("Mae’r tywydd yn braf", "mae'r tywydd yn braf"),
    ("Dw i’n mynd", "dw i'n mynd"),
    ("i’w dŷ", "i'w dŷ"),
    ("ʼn awr", "'n awr"),
    # the ratio and fullwidth colons fold to ASCII so a clock time is still a clock time
    ("15∶45", "chwarter i bedwar y prynhawn"),
    # abbreviated UI dates: title-case weekday and month abbreviations (2026-09-08)
    ("Maw 8 Medi", "mawrth yr wythfed o fedi"), ("8 Maw", "yr wythfed o fawrth"),
    ("Llun 1 Ion 2026", "llun y cyntaf o ionawr dwy fil a dau ddeg chwech"),
    ("Iau 4 Gorff", "iau y pedwerydd o orffennaf"), ("Sul 7 Chwef", "sul y seithfed o chwefror"),
    ("5 hyd 7", "pump hyd saith"),                    # lower-case "hyd" is the preposition, not Hydref
    ("1af Ionawr 2026", "y cyntaf o ionawr dwy fil a dau ddeg chwech"), ("Gwe 31ain Rhag", "gwener yr unfed ar ddeg ar hugain o ragfyr"),
    ("am 9：30", "am hanner awr wedi naw"),
    # dates & ordinals
    ("17/07/2026", "yr ail ar bymtheg o orffennaf dwy fil a dau ddeg chwech"),
    ("1/1/2000", "y cyntaf o ionawr dwy fil"),
    ("3ydd", "trydydd"),
    ("3edd", "trydedd"),
    ("1af", "cyntaf"),
    ("21ain", "unfed ar hugain"),
    ("17 Gorffennaf 2026", "yr ail ar bymtheg o orffennaf dwy fil a dau ddeg chwech"),
    ("25 Rhagfyr", "y pumed ar hugain o ragfyr"),
    # currency, time, symbols
    ("£5", "pum punt"),
    ("£1", "un bunt"),
    ("£5.99", "pum punt naw deg naw ceiniog"),
    ("£100", "can punt"),
    ("50p", "pum deg ceiniog"),
    # magnitude suffixes: in "£5m" the m is MILLION, not metres. _CURRENCY runs before
    # _UNIT so it claims its whole amount (decimal included) first; before that,
    # "£5m" read as "£pum metr" and "£2.5m" as "dwy bunt.pum metr".
    # The wording ("<cardinal> o bunnoedd", and "biliwn" for bn) is PENDING SIGN-OFF --
    # docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md section 3 lists every one of these.
    # "pum miliwn"/"un miliwn" (not "pump miliwn"/bare "miliwn") follow straight from the
    # 2026-07-26 _MIL_SPECIAL/_MILIWN_SPECIAL decision -- num_to_welsh(5_000_000) and
    # num_to_welsh(1_000_000) changed, and this is the same cardinal verbaliser unchanged.
    ("£5m", "pum miliwn o bunnoedd"),
    # BTC style-guide decision (2026-07-27): "miliwn"/"biliwn" are never mutated, to
    # avoid the "filiwn" ambiguity between the two (m and b both soft-mutate to f).
    # "dwy" (feminine 2) stays -- only the mutation on "miliwn" itself drops.
    ("£2.5m", "dwy miliwn pum can mil o bunnoedd"),
    ("£10k", "deg mil o bunnoedd"),
    ("£3bn", "tri biliwn o bunnoedd"),
    ("mae £3m yn y gronfa", "mae tair miliwn o bunnoedd yn y gronfa"),
    ("£1m", "un miliwn o bunnoedd"),       # 1 now takes "un" (2026-07-26 decision)
    ("£2m", "dwy miliwn o bunnoedd"),      # feminine "dwy", but NOT mutated (2026-07-27)
    ("£1,500m", "un biliwn pum can miliwn o bunnoedd"),
    # upper case reaches _CURRENCY only because _spell_acronym stands aside for it:
    # "£5M" is [A-Z0-9]{2,} and used to be spelled out as a code ("£pump m")
    ("£5M", "pum miliwn o bunnoedd"),
    ("£3BN", "tri biliwn o bunnoedd"),
    # ...and a code that only looks like one still spells out
    ("£5MB", "£pump m·b"),
    ("5M", "pump m"),
    # currency yields the digits back whenever a real unit follows, so putting the
    # currency pass first did not turn "£5kg" into the glued nonword "pum puntkg"
    ("£5kg", "£pum cilogram"),
    ("£5 kg", "£pum cilogram"),
    # idiomatic clock (language decision, 2026-07-26: chosen over the previous digital
    # default). "o'r gloch"/"wedi"/"i"+mutation/"chwarter"/"hanner awr wedi" are the
    # VERIFIED reference (docs/NORMALIZATION.md); the individual hour/minute words are
    # DERIVED and pending sign-off (docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md §5).
    ("3:00", "tri o'r gloch"),
    ("10:30", "hanner awr wedi deg"),
    ("9:05", "pum munud wedi naw"),
    # minutes use TRADITIONAL numerals, not num_to_welsh's decimal register -- this is a
    # deliberate split. "pump ar hugain" (unreduced), not the pre-nominal "pum", because
    # "munud" does not directly follow the leading digit ("ar hugain" intervenes).
    ("10:25", "pump ar hugain munud wedi deg"),
    # "i" (to) soft-mutates the hour (t -> d): "chwarter i dri", not "*chwarter i tri".
    ("2:45", "chwarter i dri"),
    # "wedi" (past) does NOT mutate the hour: "dau", not "*ddau".
    ("2:15", "chwarter wedi dau"),
    ("11:45", "chwarter i ddeuddeg"),      # "i" wraps to the next hour (11 -> 12) and mutates it
    ("12:00", "deuddeg o'r gloch"),        # hour <=12, no marker: NEVER an invented qualifier
    ("23:59", "un funud i ddeuddeg yr hwyr"),  # unambiguous 24h hour (>=13) MAY take one
    ("14:45", "chwarter i dri y prynhawn"),
    ("3:00pm", "tri o'r gloch y prynhawn"),    # explicit marker: qualifier even though hour <=12
    ("3:00am", "tri o'r gloch y bore"),
    ("3:00 y.p.", "tri o'r gloch y prynhawn"),  # Welsh-style dotted marker
    ("2 + 2 = 4", "dau plws dau yn hafal i pedwar"),
    # fractions. hanner/traean/chwarter are irregular; everything else is the
    # "N rhan o M" register the user chose (2026-07-26). "rhan" is feminine, so the
    # numerator takes feminine forms and the denominator follows "o" (soft mutation).
    ("1/2", "hanner"),
    ("1/4", "chwarter"),
    ("3/4", "tri chwarter"),
    ("1/3", "traean"),
    ("2/3", "dwy ran o dair"),        # rhan -> ran after dwy; tair -> dair after o
    ("5/8", "pum rhan o wyth"),       # pump -> pum before a noun
    ("7/8", "saith rhan o wyth"),
    ("3/5", "tair rhan o bump"),      # pump -> bump after o
    ("4/9", "pedair rhan o naw"),
    ("3/10", "tair rhan o ddeg"),     # deg -> ddeg after o
    ("5/6", "pum rhan o chwech"),     # ch does not soft-mutate
    # units. Numerals take their pre-nominal forms (pum, chwe), and the unit takes
    # soft mutation after dau/dwy and aspirate mutation after tri/chwe.
    ("5km", "pum cilomedr"),
    ("3kg", "tri chilogram"),         # aspirate after tri, cf. the verified "tri chant"
    ("10cm", "deg centimetr"),
    ("2m", "dau fetr"),               # soft after dau
    ("6km", "chwe chilomedr"),        # aspirate after chwe
    ("2kg", "dau gilogram"),          # soft after dau
    ("1l", "un litr"),
    # mm had no coverage at all -- not here and not in normalize_golden.tsv -- while a
    # comment in cy_normalize.c claimed the km|kg|cm|mm|m|g|l alternation order was what
    # kept "5mm" millimetres. It is not (the trailing \b is; see the comment there now),
    # but mm was still the one unit nothing pinned.
    ("5mm", "pum milimetr"),
    ("2mm", "dau filimetr"),          # soft after dau: m -> f
    ("3mm", "tri milimetr"),          # m does not aspirate, so tri leaves it plain
    ("6mm", "chwe milimetr"),
    ("10mm", "deg milimetr"),
    # above 10 the numeral is num_to_welsh's own output: 1,500 -> "un mil pum cant"
    # since the 2026-07-26 decision (was "mil pum cant" when 1000 was bare "mil").
    # BTC connected form ("can metr"): the hundred touches the noun, so it reduces.
    ("1,500mm", "un mil pum can milimetr"),
    # pass-ordering check: a fraction inside a sentence that also contains a separate
    # bare integer. If _FRACTION ran after _INTEGER (or after the bare-integer pass),
    # the "3" and "4" either side of the slash would be digit-converted independently
    # (e.g. "tri/pedwar") instead of "tri chwarter", and/or "20" would be consumed
    # wrong. This is not covered by the brief's standalone-fraction cases above.
    ("mae 3/4 o'r 20 disgybl", "mae tri chwarter o'r dau ddeg disgybl"),
    # improper fractions (numerator >= denominator) are deliberately NOT verbalised as
    # "N rhan o M" -- docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md:13 says these are left
    # to the digit pass rather than guessed at. Each side of the slash is converted
    # independently, and the slash becomes a SPACE (_symbols): leaving it in place fused
    # the two sides into one word that letter-to-sound then mangled. It is still not a
    # fraction reading -- how to say "/" is an open convention -- just not garbage.
    ("5/4", "pump pedwar"),
    ("4/4", "pedwar pedwar"),
    ("9/2", "naw dau"),
    ("6/3", "chwech tri"),
]


def test_cardinals():
    bad = {n: num_to_welsh(n) for n, exp in CARDINALS.items() if num_to_welsh(n) != exp}
    assert not bad, f"cardinal mismatches: {bad}"


def test_normalize():
    n = WelshNormalizer()
    bad = [(i, e, n.normalize(i)) for i, e in NORMALIZE if n.normalize(i) != e]
    assert not bad, "normalize mismatches:\n" + "\n".join(f"  {i!r} -> {g!r} (want {e!r})" for i, e, g in bad)


# --- C parity for the same two tables ---------------------------------------------
# The C port ships on-device, so every normalization decision pinned above is also a C
# requirement. techiaith/g2p/c/normalize_golden.tsv covers a wide corpus but reaches
# only SIX plain clock inputs and no am/pm-style marker at all -- so the qualifier logic,
# the marker spellings and the [0-5] minute restriction had no C coverage, while the
# tables here already spell out exactly what they should do. Driving the same rows
# through cyp_normalize costs no new corpus rows and makes each future wording decision
# a C-parity requirement automatically.


def _c_normalizer():
    """ctypes handles for cyp_normalize / cyp_num_to_welsh, or skip if unbuilt."""
    import ctypes
    so = REPO / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
    if not so.exists():
        import pytest
        pytest.skip("libcy_phonemize.so not built (make -C techiaith/g2p/c libcy_phonemize.so)")
    lib = ctypes.CDLL(str(so))
    lib.cyp_normalize.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_int]
    lib.cyp_num_to_welsh.argtypes = [ctypes.c_long, ctypes.c_char_p, ctypes.c_int]
    # The acronym pass gates on the dictionary headword set; a bare-cyp_normalize
    # harness must load it itself (cyp_create does it for phonemize callers).
    lib.cyp_normalize_load_vocab.argtypes = [ctypes.c_char_p]
    lib.cyp_normalize_load_vocab.restype = ctypes.c_long
    n = lib.cyp_normalize_load_vocab(str(REPO / "techiaith" / "g2p").encode())
    assert n > 0, "cyp_normalize_load_vocab failed -- dictionary files missing?"

    def norm(s):
        buf = ctypes.create_string_buffer(65536)
        lib.cyp_normalize(s.encode(), buf, 65536)
        return buf.value.decode()

    def num(n):
        buf = ctypes.create_string_buffer(512)
        lib.cyp_num_to_welsh(n, buf, 512)
        return buf.value.decode()

    return norm, num


def test_c_normalize_matches_the_python_table():
    norm, _ = _c_normalizer()
    bad = [(i, e, norm(i)) for i, e in NORMALIZE if norm(i) != e]
    assert not bad, "C normalize mismatches:\n" + "\n".join(
        f"  {i!r} -> {g!r} (want {e!r})" for i, e, g in bad)


def test_c_cardinals_match_the_python_table():
    _, num = _c_normalizer()
    bad = {n: num(n) for n, e in CARDINALS.items() if num(n) != e}
    assert not bad, f"C cardinal mismatches: {bad}"


def test_c_clock_rejects_an_out_of_range_minute():
    """The minute class is [0-5]\\d, not \\d\\d, in BOTH implementations.

    Read as \\d\\d the C port fed 99 to the minute tables; Python simply does not see a
    time there and the digits fall to the number pass. No corpus row has an invalid
    minute, and the table above cannot carry one without asserting the digit pass's
    output, so pin the shape here: no clock vocabulary, and the two implementations agree.
    """
    norm, _ = _c_normalizer()
    py = WelshNormalizer()
    for text in ("3:99", "3:60", "12:75", "3:99pm"):
        assert norm(text) == py.normalize(text), f"C/Python disagree on {text!r}"
        for word in ("o'r gloch", "wedi", "chwarter", "hanner awr", "munud"):
            assert word not in py.normalize(text), (
                f"{text!r} is not a valid time but read as one: {py.normalize(text)!r}")


def test_c_clock_sweep_matches_python_for_every_hour_minute_and_marker():
    """Every clock cell, C against Python, across all hours x minutes x markers.

    The C clock tables are 57 hand-transcribed cells and only about nine of them are
    touched by any corpus row or literal test, so a transcription slip in the rest was
    invisible: `make check` stayed 8/8 and pytest stayed at its two known failures with a
    gender error injected into MINUTE_TRAD[17] ("dau ar bymtheg" for "dwy ar bymtheg",
    reachable as 8:17) and with "yb" deleted from TIME_MARKERS (3:00yb losing its
    qualifier). Both are one-line edits to a table nothing else reads.

    A sweep is the right shape here rather than more corpus rows: the corpus row counts are
    pinned by enums in the C test files, and the cells are generated by a rule, so
    enumerating them costs nothing and covers all of it.
    """
    norm, _ = _c_normalizer()
    py = WelshNormalizer()
    # yh/y.h. (yr hwyr) included: the marker set is three-way, not two, and no corpus row
    # carries any marker at all, so this sweep is the only thing covering them.
    # MIXED case, not upper: an all-caps marker ("PM", "YB") is consumed by the acronym
    # pass before pass_time ever sees it, so those never reached TIME_MARKERS and the
    # case-insensitive compare was untested -- C strncasecmp -> strncmp passed the whole
    # suite. "Pm"/"yB"/"Y.b." do reach it.
    # UPPERCASE bare markers ("PM", "YB") now reach the clock via the acronym stand-aside
    # (clock_marker_token, both implementations), so they are swept too. The uppercase
    # DOTTED forms ("P.M.") stay excluded from the marker tuple's expectations the same
    # way they stay broken in both engines: the [A-Z0-9] acronym token there is "00P",
    # not marker-shaped, so the stand-aside never fires -- broken-but-agreeing, and the
    # sweep only checks agreement, so they are swept for parity anyway (see "P.M." below).
    markers = ("", "yb", "y.b.", "yp", "y.p.", "yh", "y.h.", "am", "pm",
               "a.m.", "p.m.", "A.m.", "p.M.", "P.M.",
               "Pm", "pM", "Yb", "yB", "Y.b.", "yH", "AM", "PM", "YB", "YP", "YH")
    bad = []
    for hour in range(0, 24):
        for minute in range(0, 60):
            for marker in markers:
                # the colon form, every cell
                texts = [f"{hour}:{minute:02d}{marker}"]
                if marker:
                    # the dotted-hour form ("7.30pm") -- marker REQUIRED, so only when
                    # one is present; and the hour-only form ("7pm"), once per hour
                    texts.append(f"{hour}.{minute:02d}{marker}")
                    if minute == 0:
                        texts.append(f"{hour}{marker}")
                for text in texts:
                    if norm(text) != py.normalize(text):
                        bad.append((text, py.normalize(text), norm(text)))
                        if len(bad) > 8:
                            break
                if len(bad) > 8:
                    break
            if len(bad) > 8:
                break
        if len(bad) > 8:
            break
    assert not bad, f"C/Python clock divergence ({len(bad)} shown): {bad[:8]}"


def test_clock_vocabulary_is_actually_exercised_by_the_sweep():
    """Guard for the sweep above: it must produce real clock readings, not a wall of
    unparsed digits that trivially agree. Without this, changing the minute class to
    something that never matches would leave the sweep green."""
    py = WelshNormalizer()
    seen = set()
    for hour in (0, 1, 3, 9, 12, 13, 15, 23):
        for minute in (0, 1, 15, 17, 25, 30, 35, 45, 59):
            out = py.normalize(f"{hour}:{minute:02d}")
            for word in ("o'r gloch", "wedi", "chwarter", "hanner awr", "munud", "i "):
                if word in out:
                    seen.add(word)
    assert seen >= {"o'r gloch", "wedi", "chwarter", "hanner awr", "munud"}, (
        f"the clock sweep is not reaching the clock vocabulary; only saw {sorted(seen)}")


def test_g2p_applies_normalization():
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P()
    assert g.normalize("25") == "dau ddeg pump"        # decimal register
    # text_to_ids must normalize first: "1" and "un" yield identical ids.
    assert g.text_to_ids("1", on_oov="skip") == g.text_to_ids("un", on_oov="skip")


def test_one_letter_welsh_words_survive_an_adjacent_acronym():
    """"y HMS" must be the article plus HMS, not a four-letter English spelling.

    The G2P used to infer acronyms from runs of adjacent single letters, so the normalized
    "y h m s" swallowed the article and read it as the English letter Y. The acronym
    boundary is now marked by welsh_normalize instead of guessed at. HMS carries this
    test since the 2026-08-25 vocabulary gate: BBC, the previous example, is in the
    dictionaries ("bi bi si") and now reads as that word, while HMS is OOV and still
    letter-spells -- exactly the case whose boundary must not swallow its neighbour.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P, _CY_LETTER_NAMES, _EN_LETTER_NAMES
    g = BangorG2P(english_mode="native")

    # the acronym's own letters: English names, one spoken word each
    assert g.phonemize(g.normalize("HMS")) == (
        list(_EN_LETTER_NAMES["h"]) + [" "] + list(_EN_LETTER_NAMES["m"])
        + [" "] + list(_EN_LETTER_NAMES["s"]))

    # the function word keeps its lexicon pronunciation, whichever side it sits on
    hms = [" "] + list(_EN_LETTER_NAMES["h"]) + [" "] + list(_EN_LETTER_NAMES["m"]) \
        + [" "] + list(_EN_LETTER_NAMES["s"])
    assert g.phonemize(g.normalize("y HMS")) == ["@"] + hms
    assert g.phonemize(g.normalize("a HMS")) == ["a"] + hms
    assert g.phonemize(g.normalize("o HMS")) == ["o"] + hms
    assert g.phonemize(g.normalize("i HMS")) == ["i"] + hms
    assert g.phonemize(g.normalize("HMS y dydd")) == hms[1:] + [" ", "@", " "] \
        + g.phonemize("dydd")

    # vowels are absent from the letter tables on purpose — they are real Welsh words
    for vowel in "aeiouwy":
        assert vowel not in _CY_LETTER_NAMES

    # S4C keeps WELSH letter names: its digit breaks the run, leaving the letters isolated
    assert g.phonemize(g.normalize("S4C"))[:3] == list(_CY_LETTER_NAMES["s"])


def test_curly_apostrophe_reaches_the_lexicon():
    """A curly apostrophe must phonemize identically to a straight one.

    Without the fold, "i’w" missed the lexicon (no U+2019 headwords exist) and LTS read
    it as two syllables /ˈiː.u/ instead of the diphthong /ɪu/.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    for straight, curly in [("i'w dŷ", "i’w dŷ"), ("dw i'n mynd", "dw i’n mynd"),
                            ("mae'r tywydd", "mae’r tywydd"), ("o'r blaen", "o’r blaen")]:
        assert g.text_to_ids(straight) == g.text_to_ids(curly), f"{curly!r} != {straight!r}"


def test_a_typed_middle_dot_never_deletes_text():
    """A literal U+00B7 in user input must not make words disappear.

    ACRONYM_JOIN is U+00B7, a character users can type -- Catalan punt volat, Greek ano
    teleia, a stray keystroke. _acronym_tokens used to split the core on it and SKIP every
    part that was not a single letter it had a name for, so anything else was silently
    deleted: "mae 5.5 yma" with a middle dot normalized to "mae pump<U+00B7>pump yma" and
    spoke "mae yma" -- the number simply gone -- and "pris<U+00B7>da" produced no tokens at
    all, which the API returned as HTTP 200 with ~58 ms of silence.

    A core is an acronym only if EVERY marker-separated part is a single letter with a
    name; otherwise the marker is the author's own text and is read as a word separator.
    Nothing may ever be dropped.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    dot = "\u00b7"

    def spoken(text):
        return g.phonemize(g.normalize(text), on_oov="lts")

    # the reported cases: the content survives
    assert spoken(f"mae 5{dot}5 yma") == spoken("mae pump pump yma")
    assert spoken(f"pris{dot}da") == spoken("pris da")
    assert spoken(f"1{dot}2") == spoken("un dau")
    # a marker at either edge is just a separator with nothing on one side
    assert spoken(f"{dot}da") == spoken("da")
    assert spoken(f"da{dot}") == spoken("da")
    assert spoken(f"cath{dot}{dot}ci") == spoken("cath ci")
    # multi-character parts stay whole words, not letter names
    assert spoken(f"ab{dot}cd") == spoken("ab cd")

    # ...and none of them is empty, which was the actual bug
    for text in (f"mae 5{dot}5 yma", f"pris{dot}da", f"1{dot}2", f"{dot}da", f"da{dot}",
                 f"cath{dot}{dot}ci", f"ab{dot}cd"):
        assert spoken(text), f"{text!r} produced no tokens -- silent deletion has returned"


def test_single_letter_parts_still_read_as_an_acronym():
    """"j<U+00B7>w" keeps the acronym reading, and that is forced, not merely preferred.

    welsh_normalize normalizes an OOV acronym like "JW" to exactly "j<U+00B7>w", so the
    two are indistinguishable by the time the G2P sees them. Reading a marker between
    single letters as anything other than an acronym would therefore break every OOV
    two-letter acronym. The collision is real but it can only be resolved this way.
    (The example was "AB" until the 2026-08-25 vocabulary gate: "ab" is a dictionary
    headword -- the patronymic -- so "AB" now reads as that word and never meets the
    marker at all.)
    """
    from techiaith.g2p.bangor_g2p import BangorG2P, _EN_LETTER_NAMES
    g = BangorG2P(english_mode="native")
    dot = "\u00b7"

    assert g.normalize("JW") == f"j{dot}w"
    assert g.text_to_ids(f"j{dot}w") == g.text_to_ids("JW")
    assert g.phonemize(g.normalize("JW")) == (
        list(_EN_LETTER_NAMES["j"]) + [" "] + list(_EN_LETTER_NAMES["w"]))
    # and a genuine (OOV) acronym is untouched by the stricter rule
    assert g.phonemize(g.normalize("HMS")) == (
        list(_EN_LETTER_NAMES["h"]) + [" "] + list(_EN_LETTER_NAMES["m"])
        + [" "] + list(_EN_LETTER_NAMES["s"]))


def test_marker_is_safe_in_the_other_two_entry_points():
    """letter_tokens and tokens_from_phones must not drop content on the marker either.

    letter_tokens spells characters, so the marker has no letter name and is skipped like
    any other punctuation -- but every letter and digit around it must still be spelled.
    tokens_from_phones takes author-supplied phones, where the marker is not a phone: it
    must be REJECTED, never quietly swallowed.
    """
    import pytest
    from techiaith.g2p.bangor_g2p import BangorG2P, PhoneError
    g = BangorG2P(english_mode="native")
    dot = "\u00b7"

    assert g.letter_tokens(f"a{dot}b") == g.letter_tokens("ab")
    assert g.letter_tokens(f"pris{dot}da") == g.letter_tokens("prisda")
    assert g.letter_tokens(f"5{dot}5") == g.letter_tokens("5 5")

    for alphabet, phones in (("bangor", f"b {dot} ii"), ("bangor", f"b{dot}ii"),
                             ("bangor", dot), ("ipa", f"b{dot}i\u02d0"), ("ipa", dot)):
        with pytest.raises(PhoneError):
            g.tokens_from_phones(phones, alphabet=alphabet)


def _run():
    fails = []
    for n, exp in CARDINALS.items():
        got = num_to_welsh(n)
        if got != exp:
            fails.append((f"num {n}", exp, got))
    wn = WelshNormalizer()
    for i, e in NORMALIZE:
        got = wn.normalize(i)
        if got != e:
            fails.append((repr(i), e, got))
    return fails


if __name__ == "__main__":
    fails = _run()
    total = len(CARDINALS) + len(NORMALIZE)
    print(f"{total - len(fails)}/{total} pass")
    for name, exp, got in fails:
        print(f"  FAIL {name}: want {exp!r} got {got!r}")
    sys.exit(1 if fails else 0)


# --- BTC style guide alignment (Phase 1) -------------------------------------------

def test_connected_form_can_before_any_noun_we_emit():
    """BTC, "Y ffurfiau cyswllt ynteu'r ffurfiau dyfynnol": "Defnyddir y ffurfiau cyswllt
    'pum' (5), 'chwe' (6) a 'can' (100) yn gyffredinol ee 'pum arth', 'pum dyn', 'chwe
    adroddiad', 'chwe menyw', 'can metr', 'can merch'."

    "can metr" is the guide's own example and we read "cant metr" before this. Only
    reachable where WE emit the noun -- a symbol unit, currency, pence, blynedd. A noun
    written out as a word ("100 metr") is not detectable by a regex normaliser and is
    deliberately left alone, asserted below so the limit is explicit rather than assumed.
    """
    N = WelshNormalizer()
    assert N.normalize("100 m") == "can metr"           # the guide's example
    assert N.normalize("100 km") == "can cilomedr"
    assert N.normalize("£100") == "can punt"
    assert N.normalize("100c") == "can ceiniog"
    assert N.normalize("100 blynedd") == "can mlynedd"
    # The reduction is not limited to exactly 100.
    assert N.normalize("200 km") == "dau gan cilomedr"
    assert N.normalize("300 kg") == "tri chan cilogram"
    assert N.normalize("£200") == "dau gan punt"
    assert N.normalize("500g") == "pum can gram"
    # Only a TRAILING hundred reduces: in 150 the hundred does not touch the noun.
    assert N.normalize("150 m") == "cant pum deg metr"
    assert N.normalize("100") == "cant"                 # no noun at all
    # Not detectable, and must stay untouched rather than be guessed at.
    assert N.normalize("100 metr") == "cant metr"


def test_yh_marker_reads_as_yr_hwyr():
    """"yh"/"y.h." (yr hwyr) alongside yb/yp. BTC names them in order to recommend AGAINST
    writing them ("10am hyd 4pm, nid ... '10yb hyd 4yh'") -- advice to writers, not to a
    reader, and a TTS reads what is in front of it.

    Before this the failure was not a missing qualifier but a collapsed match: the trailing
    (?!\\w) failed on the unrecognised "yh", so the WHOLE time match failed and the digits
    fell through to the integer pass, colon and all.
    """
    N = WelshNormalizer()
    assert N.normalize("16:00yh") == "pedwar o'r gloch yr hwyr"
    assert N.normalize("16:00y.h.") == "pedwar o'r gloch yr hwyr"
    assert N.normalize("10:30yh") == "hanner awr wedi deg yr hwyr"
    # yr hwyr, not y prynhawn -- the two must not collapse.
    assert N.normalize("16:00yp") == "pedwar o'r gloch y prynhawn"
    assert "prynhawn" not in N.normalize("16:00yh")
    # "pm" deliberately stays y prynhawn: English pm spans both halves of the day, and
    # choosing a side would invent information the author did not give.
    assert N.normalize("16:00pm") == "pedwar o'r gloch y prynhawn"
    # The dotted English forms ("a.m."/"p.m.") repeat the yh story with a nastier fall:
    # the collapsed match handed the MINUTE digits to _PENCE, so a time read as money
    # ("7:00p.m." -> "saith sero ceiniog.m."). The marker alternation must claim them.
    assert N.normalize("7:00p.m.") == "saith o'r gloch y prynhawn"
    assert N.normalize("16:00p.m.") == "pedwar o'r gloch y prynhawn"
    assert N.normalize("3:00a.m.") == "tri o'r gloch y bore"
    # The existing \s? means the SPACED dotted forms come along for free.
    assert N.normalize("3:00 a.m.") == "tri o'r gloch y bore"
    assert N.normalize("7:00 p.m.") == "saith o'r gloch y prynhawn"
    for text in ("7:00p.m.", "16:00p.m.", "3:00 a.m."):
        assert "ceiniog" not in N.normalize(text), text
    # Absolute and dict-driven: every form _TIME's alternation matches must map to its
    # qualifier through _MARKER_QUALIFIER -- a marker present in the regex but missing
    # from the dict matches and then silently drops its qualifier, which this catches.
    from techiaith.g2p.welsh_normalize import _MARKER_QUALIFIER
    assert len(_MARKER_QUALIFIER) == 10
    for marker, qualifier in _MARKER_QUALIFIER.items():
        assert N.normalize(f"16:00{marker}") == f"pedwar o'r gloch {qualifier}", marker
        # No raw colon survives into the output for any marker form.
        assert ":" not in N.normalize(f"16:00{marker}"), marker


def test_colonless_glued_marker_reads_as_clock():
    """The colonless clock forms BTC tells Welsh authors to WRITE ("10am hyd 4pm, nid ...
    '10yb hyd 4yh'") previously fused into LTS nonwords ("7pm" -> "saithpm") or, dotted,
    fell to _PENCE as money ("7p.m." -> "saith geiniog.m."). FOLLOWUPS section H.

    The marker is REQUIRED and GLUED: "am" is a Welsh preposition, so the spaced forms
    must never become clock readings -- pinned below alongside the accepted limitations.
    """
    N = WelshNormalizer()
    assert N.normalize("7pm") == "saith o'r gloch y prynhawn"
    assert N.normalize("7am") == "saith o'r gloch y bore"
    assert N.normalize("2yh") == "dau o'r gloch yr hwyr"
    assert N.normalize("7p.m.") == "saith o'r gloch y prynhawn"      # was seven PENCE
    assert N.normalize("10am hyd 4pm") == \
        "deg o'r gloch y bore hyd pedwar o'r gloch y prynhawn"
    assert N.normalize("12pm") == "deuddeg o'r gloch y prynhawn"
    assert N.normalize("12am") == "deuddeg o'r gloch y bore"
    # Absolute and dict-driven, like the colon-form loop: regex/dict drift is caught.
    from techiaith.g2p.welsh_normalize import _MARKER_QUALIFIER
    for marker, qualifier in _MARKER_QUALIFIER.items():
        assert N.normalize(f"7{marker}") == f"saith o'r gloch {qualifier}", marker
    # Uppercase reaches the clock via the acronym stand-aside (_clock_marker_token).
    assert N.normalize("7PM") == "saith o'r gloch y prynhawn"        # was 'saith p·m'
    assert N.normalize("10YB") == "deg o'r gloch y bore"
    assert N.normalize("3:00PM") == "tri o'r gloch y prynhawn"       # was 'tri sero p·m'
    assert N.normalize("3:45PM") == "chwarter i bedwar y prynhawn"   # minute-field rule
    assert N.normalize("AR AGOR 9AM HYD 5PM") == \
        "ar agor naw o'r gloch y bore hyd pump o'r gloch y prynhawn"
    # The preposition "am" must NEVER become a clock: spaced forms stay words.
    assert N.normalize("5 am ddim") == "pump am ddim"
    assert N.normalize("2 am 1") == "dau am un"
    assert N.normalize("talu £5 am bob un") == "talu pum punt am bob un"
    assert N.normalize("7 pm") == "saith pm"        # ACCEPTED LIMITATION, pinned
    assert N.normalize("7") == "saith"              # bare hour unreachable without marker
    # Standalone "PM" is a dictionary word since the 2026-08-25 vocabulary gate: it reads
    # as the lexicon's "pm" ("pi em" — the Prime Minister), no longer the spelled p·m.
    assert N.normalize("the PM said") == "the pm said"
    assert N.normalize("45PM") == "pedwar deg pump p·m"    # not a valid hour: stays a code
    # (?<![:.,]): a failed context must not have its tail digits read as a plausible time.
    for text in ("25:00pm", "99.15pm", "1,23pm"):
        out = N.normalize(text)
        for word in ("o'r gloch", "wedi", "chwarter"):
            assert word not in out, (text, out)
    # Addresses: email/URLs run BETWEEN the clock passes (mirroring C's order), so the
    # time is read INSIDE the verbalised address, not carved out of the raw one.
    assert N.normalize("post@7pm.com") == "post at saith o'r gloch y prynhawn dot com"


def test_dotted_hour_with_glued_marker_reads_as_clock():
    """"7.30pm" -- the common British-style dotted hour. The marker is REQUIRED: a bare
    "7.30" belongs to _DECIMAL and must stay there."""
    N = WelshNormalizer()
    assert N.normalize("7.30pm") == "hanner awr wedi saith y prynhawn"
    assert N.normalize("16.30yh") == "hanner awr wedi pedwar yr hwyr"
    assert N.normalize("2.50pm") == "deng munud i dri y prynhawn"
    assert N.normalize("7.30") == "saith pwynt tri sero"     # no marker -> _DECIMAL's
    # currency wins the amount (pass order, load-bearing); its trailing separator keeps
    # the leftover "pm" a separate word rather than the old glued "ceiniogpm"
    assert N.normalize("£2.50pm") == "dwy bunt pum deg ceiniog pm"
    for word in ("o'r gloch", "wedi", "chwarter"):           # 3-digit tail is not a time
        assert word not in N.normalize("7.300pm")


def test_cant_punt_ceiniog_soft_mutate_after_saith_and_wyth():
    """BTC, "Treiglo ai peidio": "Ni threiglir enwau heblaw 'cant', 'punt' a 'ceiniog' yn
    feddal ar ol 'saith' ac 'wyth'."

    The rule has two halves and both are asserted: those three nouns DO mutate, and
    everything else does NOT. Testing only the positive half would pass an implementation
    that mutated every noun after saith/wyth.

    This overrides two rows that previously carried the "verified reference" label
    ("saith cant"/"wyth cant"); the owner's ruling is that BTC wins a conflict.
    """
    N = WelshNormalizer()

    # cant
    assert N.normalize("700") == "saith gant"
    assert N.normalize("800") == "wyth gant"
    assert N.normalize("1700") == "un mil saith gant"
    assert N.normalize("750") == "saith gant pum deg"
    # ...and only after saith/wyth. 6 keeps its aspirate, 9 stays bare.
    assert N.normalize("600") == "chwe chant"
    assert N.normalize("900") == "naw cant"
    assert N.normalize("400") == "pedwar cant"

    # punt
    assert N.normalize("£7") == "saith bunt"
    assert N.normalize("£8") == "wyth bunt"
    assert N.normalize("£9") == "naw punt"
    assert N.normalize("£6") == "chwe phunt"

    # ceiniog
    assert N.normalize("7c") == "saith geiniog"
    assert N.normalize("8c") == "wyth geiniog"
    assert N.normalize("9c") == "naw ceiniog"
    # 17 is "dau ar bymtheg" in the vigesimal register, so the word touching "ceiniog"
    # is "bymtheg", not "saith" -- no mutation. Under the old decimal register 17 was
    # "un deg saith" and this DID mutate. The rule is unchanged; what reaches it moved.
    # 17 >= 11 with a COMPOUND numeral, so BTC's third branch applies and the noun goes
    # to "o" + plural. The saith/wyth question does not arise: "ceiniog" is not adjacent.
    assert N.normalize("17c") == "un deg saith geiniog"

    # THE NEGATIVE HALF, structurally: the rule names exactly three nouns, so no unit
    # noun may be in the table. This is what actually pins "everything else stays put" --
    # the _unit_repl call site alone cannot, because deleting it is invisible while the
    # table holds no unit noun.
    from techiaith.g2p.welsh_normalize import _SAITH_WYTH_SOFT, _UNITS_SPOKEN
    assert set(_SAITH_WYTH_SOFT) == {"cant", "punt", "ceiniog"}, (
        f"BTC names exactly cant/punt/ceiniog; got {sorted(_SAITH_WYTH_SOFT)}")
    unit_nouns = {form for forms in _UNITS_SPOKEN.values() for form in forms}
    assert not (unit_nouns & set(_SAITH_WYTH_SOFT)), (
        f"a unit noun leaked into the saith/wyth table: "
        f"{sorted(unit_nouns & set(_SAITH_WYTH_SOFT))}")

    # ...and observably, on the unit path.
    assert N.normalize("7 kg") == "saith cilogram"     # not "gilogram"
    assert N.normalize("7 m") == "saith metr"          # not "fetr"
    assert N.normalize("8 km") == "wyth cilomedr"
    assert N.normalize("7 blynedd") == "saith mlynedd"  # nasal, a different rule entirely

    # The mutation needs saith/wyth IMMEDIATELY before the noun. In "700c" the word
    # touching "ceiniog" is "gan", so ceiniog stays unmutated even though the numeral
    # contains "saith".
    assert N.normalize("700c") == "saith gan ceiniog"
    # Same shape for the connected form before a unit noun (phase 1 interaction).
    assert N.normalize("700 m") == "saith gan metr"
    assert N.normalize("800 km") == "wyth gan cilomedr"

    # And C agrees on every one of them. make check's corpus covers the cant rows, but
    # only there -- reverting C's HUNDREDS alone passed the whole pytest suite, so the
    # rule's parity was visible in one harness and invisible in the other.
    norm, _ = _c_normalizer()
    for text in ("700", "800", "600", "900", "1700", "750", "£7", "£8", "£9", "£6",
                 "7c", "8c", "9c", "17c", "700c", "7 kg", "7 m", "8 km", "700 m",
                 "800 km", "7 blynedd"):
        assert norm(text) == N.normalize(text), (
            f"C/Python disagree on {text!r}: {norm(text)!r} vs {N.normalize(text)!r}")


def test_an_unverbalised_slash_does_not_fuse_two_words_into_one():
    """A "/" between word characters becomes a space, so the two sides stay two words.

    Leaving it in place was not "unhandled", it was corrupting: the G2P has no "/" token
    and does not treat it as a boundary, so the sides fused and went to letter-to-sound as
    a nonword -- "1/20" spoke as "y-nyy-gain", "5/100" as "pym-pkant". Silent garbage with
    a 200, the same failure shape as the U+00B7 deletion that shipped.

    This is NOT a fraction reading. _FRACTION verbalises the denominators it can and bails
    out for the rest, which is the only reason anything reaches _symbols at all.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P
    N = WelshNormalizer()
    g = BangorG2P(english_mode="native")

    assert N.normalize("1/20") == "un dau ddeg"
    assert N.normalize("5/100") == "pump cant"
    # The real property: no fused nonword survives to the G2P. A word separator must sit
    # between the two numbers' tokens.
    for text in ("1/20", "5/100", "9/2", "11/7/8"):
        toks = g.phonemize(N.normalize(text), on_oov="lts")
        assert " " in toks, f"{text!r} produced one fused word: {toks}"

    # What still works, unchanged: the fractions that DO verbalise, and dates.
    assert N.normalize("1/2") == "hanner"
    assert N.normalize("3/4") == "tri chwarter"
    assert N.normalize("7/8") == "saith rhan o wyth"
    assert N.normalize("17/07/2026").startswith("yr ail ar bymtheg o orffennaf")

    # Only BETWEEN word characters, and only the class the C port can express (its
    # cp_is_word is Latin-only, so matching Python's wider \w here would add a fresh
    # Python/C divergence rather than inherit the disclosed one).
    assert N.normalize("x/") == "x/"
    assert N.normalize("/x") == "/x"
    assert N.normalize("a//b") == "a//b"
    assert N.normalize("â/ê") == "â ê"          # Welsh accents are in the C class
    assert N.normalize("α/β") == "α/β"          # non-Latin is not, in EITHER implementation


def test_years_have_their_own_register_and_decimals_use_the_general_one():
    """Years are NOT read as general cardinals; decimals now are.

    This test was originally about BTC excepting decimals and years from its vigesimal
    rule. Cardinals are decimal again (see welsh_normalize._two_digit), so the "exception"
    framing is moot for decimals -- they simply agree with the general register now. The
    YEAR register is still genuinely separate and is what remains worth pinning: BTC's own
    four worked examples, and a bare "mil", never "un mil".
    """
    from techiaith.g2p.welsh_normalize import year_words
    N = WelshNormalizer()

    # BTC's four worked examples, verbatim from its blynyddoedd entry.
    assert year_words(1980) == "mil naw wyth deg"
    assert year_words(2011) == "dwy fil ac un deg un"      # vowel -> ac
    assert year_words(2023) == "dwy fil a dau ddeg tri"    # consonant -> a
    assert year_words(2002) == "dwy fil a dau"
    assert not year_words(1980).startswith("un mil")
    # "a" aspirate-mutates c/p/t, as BTC's classical examples show.
    assert year_words(2030) == "dwy fil a thri deg"
    assert year_words(2040) == "dwy fil a phedwar deg"

    # A DATE's year slot takes that register; a bare cardinal does not (it cannot be known
    # to be a year -- "mae 1984 o bobl yma" is a quantity).
    assert N.normalize("17/07/1984").endswith("mil naw wyth deg pedwar")
    assert N.normalize("1/1/2000").endswith("dwy fil")
    assert N.normalize("1984") == "un mil naw cant wyth deg pedwar"

    # Decimals: BTC's own example, which the general register now produces anyway.
    assert N.normalize("20.15") == "dau ddeg pwynt un pump"
    assert N.normalize("25.5") == "dau ddeg pump pwynt pump"

    norm, _ = _c_normalizer()
    for t in ("20.15", "25.5", "17/07/1984", "1/1/2000", "1/1/2011", "1/1/2023",
              "1/1/1980", "3/3/2033", "1984", "25"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_connected_forms_and_saith_wyth_reach_both_pence_paths():
    """BTC "Y ffurfiau cyswllt" gives pum (5), chwe (6), can (100) "yn gyffredinol" -- the
    first pass of this work applied only `can`. And the currency path built its own pence
    string, so the saith/wyth soft mutation never reached it: a bare "7c" said "saith
    geiniog" while "£1.07" said "saith ceiniog".
    """
    N = WelshNormalizer()
    assert N.normalize("5c") == "pum ceiniog"        # was "pump ceiniog"
    assert N.normalize("6c") == "chwe ceiniog"       # was "chwech ceiniog"
    assert N.normalize("5p") == "pum ceiniog"
    assert N.normalize("100c") == "can ceiniog"
    # ...and the same forms through the currency path, which had none of them.
    assert N.normalize("£1.05") == "un bunt pum ceiniog"
    assert N.normalize("£1.06") == "un bunt chwe ceiniog"
    assert N.normalize("£1.07") == "un bunt saith geiniog"   # was "saith ceiniog"
    assert N.normalize("£1.08") == "un bunt wyth geiniog"
    # Untouched: ceiniog's feminine agreement is deferred item 7, not this rule's business.
    assert N.normalize("2c") == "dau ceiniog"
    norm, _ = _c_normalizer()
    # £200/£300 included deliberately: the connected form on the POUNDS fallback had no
    # corpus row and no C differential, so deleting reduce_cant there passed everything.
    for t in ("5c", "6c", "7c", "100c", "£1.05", "£1.07", "£1.08", "2c",
              "£100", "£200", "£300", "£700", "500g", "100 m", "150 m"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_out_of_range_hours_do_not_read_as_a_plausible_time():
    """The minute class was tightened to [0-5]\\d but the hour left \\d{1,2} while an
    h % 12 reduction was added, which turned nonsense into a plausible-sounding lie:
    "90:00" read as "chwech o'r gloch" and "99:59" as "un funud i bedwar".

    Out of range must now fail the match so the digits fall to the number pass -- audibly
    wrong rather than silently wrong.
    """
    N = WelshNormalizer()
    for bad in ("90:00", "24:15", "25:00", "99:59"):
        out = N.normalize(bad)
        for word in ("o'r gloch", "wedi", "chwarter", "hanner awr", "munud", "funud"):
            assert word not in out, f"{bad!r} still read as a time: {out!r}"
    # In range, unaffected.
    assert N.normalize("23:59") == "un funud i ddeuddeg yr hwyr"
    assert N.normalize("0:00") == "deuddeg o'r gloch"
    assert N.normalize("13:00") == "un o'r gloch y prynhawn"
    norm, _ = _c_normalizer()
    for t in ("90:00", "24:15", "99:59", "23:59", "0:00", "13:00", "12:00"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_word_internal_punctuation_does_not_fuse_two_words():
    """":" joins "/" in the fusing class. The G2P peels punctuation only from a token's
    EDGES, so an internal one is neither peeled nor spoken -- the sides fuse into one word
    for letter-to-sound and the character is silently dropped. Bounding the hour created
    the ":" path ("90:00" -> "...ugain:sero" -> one LTS'd nonword).

    "-" is deliberately excluded: the hyphen rule needs it to tell "b-a-ch" from
    "gogledd-ddwyrain".
    """
    from techiaith.g2p.bangor_g2p import BangorG2P
    N = WelshNormalizer()
    g = BangorG2P(english_mode="native")
    for text in ("90:00", "24:15", "1/20", "5/100"):
        toks = g.phonemize(N.normalize(text), on_oov="lts")
        assert " " in toks, f"{text!r} fused into one word: {toks}"
        assert ":" not in N.normalize(text) and "/" not in N.normalize(text)
    # Not between word characters, so untouched.
    assert N.normalize("Nodyn: dyma") == "nodyn: dyma"
    # Compounds and keyboard echo must survive.
    assert N.normalize("gogledd-ddwyrain") == "gogledd-ddwyrain"
    assert N.normalize("b-a-ch") == "b-a-ch"
    # The class is meant to be an EXACT mirror of the C port's cp_is_word, so the
    # boundaries are what matter and only C can confirm them. Without these the mirror was
    # asserted on the Python side alone: dropping Latin Extended Additional from the class
    # passed the whole suite while "ḍ/ḍ" diverged.
    norm, _ = _c_normalizer()
    for t in ("90:00", "1/20", "Nodyn: dyma", "gogledd-ddwyrain", "b-a-ch", "23:59",
              "ḍ/ḍ",      # U+1E0D, Latin Extended Additional: IN the class
              "Ā/ā",      # U+0100, first of Latin Extended-A
              "ɏ/ɏ",      # U+024F, last of Latin Extended-B
              "Ö/ö", "ÿ/ÿ",          # C0-FF band
              "×/÷",      # excluded from C0-FF by cp_is_word
              "α/β", "字/字",         # not Latin: excluded in BOTH implementations
              "_/_", "1/2x"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_btc_counted_noun_branches():
    """BTC "Y lluosog ynteu'r unigol" has three branches; under the DECIMAL register only
    the first two can fire.

      "hyd at ddeg, defnyddir yr unigol"  /  "o 11 i fyny, defnyddir yr unigol pan fo'r hyn
      a gyfrifir yn dod ar ol y rhif ee '18 mis'"  /  "...y lluosog... pan ddefnyddir y
      system ugeiniol a phan fo'n arferol rhoi'r hyn a gyfrifir yn y canol -- '11 o
      filltiroedd'"

    The third is conditional on the VIGESIMAL system, and a decimal numeral has no middle
    for the noun to sit in ("dau ddeg pump" contains no joiner), so it is dormant by
    construction rather than removed. The code is kept because the rule is BTC's and would
    fire again if cardinals were ever made vigesimal; this test pins that it does NOT fire
    today, which is the property that would otherwise regress silently.
    """
    N = WelshNormalizer()

    # BRANCH 1: up to ten, singular.
    assert N.normalize("2 m") == "dau fetr"
    assert N.normalize("£5") == "pum punt"
    assert N.normalize("£7") == "saith bunt"        # the saith/wyth mutation still fires
    assert N.normalize("5 blynedd") == "pum mlynedd"

    # BRANCH 2: 11+ with the noun after the numeral, singular -- BTC's "18 mis" shape.
    assert N.normalize("18 m") == "un deg wyth metr"
    assert N.normalize("£20") == "dau ddeg punt"
    assert N.normalize("£100") == "can punt"          # the connected form, BTC
    # _BLYNEDD_NUM hand-cases these as fixed idioms, so they keep their traditional
    # numeral even though the general register is decimal. Flagged in §6 as an
    # inconsistency worth a native speaker's eye: "15 blynedd" is "pymtheng mlynedd" while its
    # neighbour "14 blynedd" is "un deg pedwar mlynedd".
    assert N.normalize("20 blynedd") == "ugain mlynedd"
    assert N.normalize("100 blynedd") == "can mlynedd"
    assert N.normalize("15 blynedd") == "pymtheng mlynedd"
    assert N.normalize("14 blynedd") == "un deg pedwar mlynedd"

    # BRANCH 3 is DORMANT: no decimal numeral is compound, so nothing takes "o" + plural.
    from techiaith.g2p.welsh_normalize import _is_compound_numeral, num_to_welsh
    assert not any(_is_compound_numeral(num_to_welsh(n)) for n in range(0, 1000)), (
        "a decimal cardinal came out compound; branch 3 would start firing")
    for t in ("£11", "£25", "£99", "11c", "25c", "11 blynedd", "25 blynedd"):
        assert " o " not in N.normalize(t), f"{t!r} took the plural: {N.normalize(t)!r}"
    assert N.normalize("£25") == "dau ddeg pump punt"
    assert N.normalize("11 blynedd") == "un deg un mlynedd"

    norm, _ = _c_normalizer()
    for t in ("2 m", "£5", "£7", "5 blynedd", "18 m", "£20", "£100", "20 blynedd",
              "100 blynedd", "£11", "£25", "11c", "11 blynedd", "25 blynedd", "25 km",
              "£1234.56", "50p"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_decimal_above_999_does_not_crash_or_lose_its_leading_digits():
    """A decimal with an integer part >= 1000. Was an uncaught crash in BOTH languages.

    _cardinal_dec / cardinal_dec were HUNDREDS[n // 100] plus the last two digits -- correct
    only below 1000 -- and nothing bounded the caller, the integer part of a decimal. So:

        Python   "1000.5"  -> KeyError: 10        (uncaught, out of normalize())
                 "1234.56" -> KeyError: 12
        C        "1000.5"  -> SIGSEGV             (HUNDREDS has 10 entries)
                 "1234.56" -> "tri deg pedwar pwynt pump chwech"

    That last one is the dangerous one: no crash, just 34.56 read out for 1234.56, with the
    leading "12" silently gone. Both now route through the full verbaliser.

    Invisible to `make check` for as long as it existed: no parity corpus row has a decimal
    at or above 1000. This test is the corpus row that was missing.
    """
    N = WelshNormalizer()
    assert N.normalize("1000.5") == "un mil pwynt pump"
    assert N.normalize("1234.56") == "un mil dau gant tri deg pedwar pwynt pump chwech"
    assert N.normalize("1000000.5") == "un miliwn pwynt pump"
    # The leading digits must be THERE, not merely non-crashing.
    assert N.normalize("1234.56").startswith("un mil dau gant")
    assert "tri deg pedwar pwynt" not in N.normalize("1234.56")[:10]
    # In a sentence, i.e. reachable from ordinary prose and not just a bare token.
    assert N.normalize("Mae 1234.56 yn y ffeil") == (
        "mae un mil dau gant tri deg pedwar pwynt pump chwech yn y ffeil")
    # Unchanged below 1000, where the old code was right.
    assert N.normalize("20.15") == "dau ddeg pwynt un pump"
    assert N.normalize("999.5") == "naw cant naw deg naw pwynt pump"

    norm, _ = _c_normalizer()
    for t in ("1000.5", "1234.56", "1000000.5", "999.5", "20.15", "0.5",
              "Mae 1234.56 yn y ffeil", "£1234.56", "1000.5%", "12,345.67"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_billions_are_named_however_the_amount_is_written():
    """"£3bn" and "£3000000000" are the same amount and must read the same.

    num_to_welsh digit-spelled everything above 999,999,999, and the ONLY thing that named
    billions was the currency path's _scaled_cardinal -- reachable solely via a magnitude
    suffix. So the suffix spelling said "tri biliwn" while the full-digits spelling of the
    identical amount said "tri dim dim dim dim dim dim dim dim dim": nine "dim"s in a row.
    """
    N = WelshNormalizer()
    assert N.normalize("1000000000") == "un biliwn"
    assert N.normalize("3000000000") == "tri biliwn"
    assert N.normalize("1500000000") == "un biliwn pum can miliwn"
    assert "dim dim" not in N.normalize("1000000000")
    # Every route to a billion, not just the one that used to work.
    assert N.normalize("£3bn").startswith("tri biliwn")
    assert N.normalize("£3000000000").startswith("tri biliwn")
    assert N.normalize("5000000000%") == "pum biliwn y cant"
    assert N.normalize("3000000000.5") == "tri biliwn pwynt pump"
    # Below a billion is the verified reference range and must be untouched.
    assert N.normalize("999999999") == (
        "naw cant naw deg naw miliwn naw cant naw deg naw mil naw cant naw deg naw")

    norm, _ = _c_normalizer()
    for t in ("1000000000", "3000000000", "£3000000000", "£3bn", "1500000000",
              "999999999", "5000000000%", "3000000000.5", "1,000,000,000"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_biliwn_multiplier_takes_the_same_reductions_as_miliwn():
    """"pum biliwn", not "pump biliwn" -- owner 2026-07-28.

    The billion multiplier was built as num_to_welsh(billions) + " biliwn", which skipped
    _scale and therefore missed BOTH corrections mil/miliwn get from it. 5 is the same defect
    piper-lleol issue #3 raises against "pump miliwn" in data marked verified: fixed for
    miliwn at the time, missed for biliwn because that path did not share the code.

    Owner: "Mae angen newid 'pump' i 'pum' o flaen enw fel 'biliwn' assume for rest."
    """
    from techiaith.g2p.welsh_normalize import num_to_welsh
    assert num_to_welsh(5 * 10**9) == "pum biliwn"          # was "pump biliwn"
    assert num_to_welsh(6 * 10**9) == "chwe biliwn"         # was "chwech biliwn"
    assert num_to_welsh(100 * 10**9) == "can biliwn"        # was "cant biliwn"
    assert num_to_welsh(200 * 10**9) == "dau gan biliwn"    # was "dau gant biliwn"
    assert num_to_welsh(300 * 10**9) == "tri chan biliwn"   # was "tri chant biliwn"

    # The whole point: the biliwn multiplier now matches the miliwn one word for word,
    # apart from the scale word itself and biliwn's accepted masculine gender.
    N = WelshNormalizer()
    for mult in (5, 6, 7, 10, 11, 20, 100, 200, 300, 999):
        bn = num_to_welsh(mult * 10**9).removesuffix(" biliwn")
        m = num_to_welsh(mult * 10**6).removesuffix(" miliwn")
        if mult not in (2, 3, 4):          # gender differs there by design: dau/dwy etc.
            assert bn == m, f"{mult}: biliwn says {bn!r}, miliwn says {m!r}"
    # biliwn is masculine where miliwn is feminine -- deliberate, closed by the owner.
    assert num_to_welsh(2 * 10**9) == "dau biliwn" and num_to_welsh(2 * 10**6) == "dwy miliwn"
    # No mutation on either, so 2m and 2bn stay distinguishable (BTC).
    assert "filiwn" not in N.normalize("£2bn") and "filiwn" not in N.normalize("£2m")

    norm, num = _c_normalizer()
    for mult in (1, 2, 3, 4, 5, 6, 7, 10, 11, 20, 100, 200, 300, 999):
        n = mult * 10**9
        assert num(n) == num_to_welsh(n), f"C/Python disagree on {n}"
    for t in ("£5bn", "£6bn", "£100bn", "£200bn", "£300bn"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_long_digit_runs_do_not_overflow_the_c_long():
    """19+ digits. C built a `long` from the run and wrapped it; Python never can.

    The C percent/decimal/integer passes went through parse_int_strip_commas, which formed
    an integer BEFORE cyp__num_words_for_run's >18-digit guard could apply -- so the guard
    could not save them. "9999999999999999999" wrapped negative and read "minws wyth pedwar
    pedwar chwech saith..." where Python says nineteen "naw"s. A silent parity break that no
    corpus row was long enough to catch.
    """
    N = WelshNormalizer()
    norm, _ = _c_normalizer()
    assert N.normalize("9" * 19) == " ".join(["naw"] * 19)
    assert not N.normalize("9" * 19).startswith("minws")
    for w in range(1, 41):
        for t in ("9" * w, "1" + "0" * (w - 1)):
            assert norm(t) == N.normalize(t), f"C/Python disagree on {w}-digit {t!r}"
            assert not norm(t).startswith("minws"), f"{t!r} wrapped negative: {norm(t)!r}"
    # 18 digits is the last width still verbalised as a number; 19 is digit-by-digit.
    assert N.normalize("9" * 18).startswith("naw cant naw deg naw miliwn")
    assert N.normalize("9" * 19) == " ".join(["naw"] * 19)
    # Commas must not change the answer, on either side.
    for t in ("1,000,000,000", "12,345,678,901,234,567,890", "1,234.56"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


# test_review_doc_tables_match_the_code is omitted from this public mirror: it
# asserts against a native-speaker review document kept in the internal repo, so
# it has nothing to check against here. It was not failing, and the tables it
# covers are settled.
def test_mil_and_fil_take_the_long_vowel_everywhere_they_appear():
    """"mil" is /miːl/, not /mɪl/ -- and the Bangor dictionary has it short.

    Found by the owner BY EAR on the live service, 2026-07-28, and narrowed by them from
    "the cost file sounds like gibberish" to "234.56 works fine it's the mil that's the
    problem" to "anything above 999 is gibberish; everything below is almost perfect".
    That boundary is exactly the scale-word tier: no cardinal below 1000 uses a scale word.

    It was NOT a length or prosody problem, which is what I chased first and wrongly: the
    owner's working "234.56" is SEVEN words ("dau gant tri deg pedwar pwynt pump chwech"),
    more than the broken SIX-word "un mil dau gant tri deg pedwar". One phone was the defect.

    Fixed in CODE (bangor_g2p._CY_PRON_OVERRIDE), not by editing the vendored dictionary,
    because data_version hashes the dictionary FILES -- see the data_version assertion at
    the end of this test, which is the whole reason the fix lives where it does.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P, _CY_PRON_OVERRIDE
    g = BangorG2P()

    # The decision itself: long vowel, and the two forms it covers.
    assert _CY_PRON_OVERRIDE["mil"] == ["ˈ", "m", "ii", "l"]
    assert _CY_PRON_OVERRIDE["fil"] == ["ˈ", "v", "ii", "l"]
    assert g.phonemize("mil", on_oov="lts") == ["ˈ", "m", "ii", "l"]
    assert g.phonemize("fil", on_oov="lts") == ["ˈ", "v", "ii", "l"]
    # It must be a real override, not a no-op that happens to agree with the dictionary.
    # Counted against the table rather than a literal: brand-name entries were added
    # 2026-09-04, and a hardcoded number turns every future addition into a failure here,
    # which says nothing about mil/fil.
    assert g.lexicon.stats.get("overridden") == len(_CY_PRON_OVERRIDE)

    N = WelshNormalizer()

    def phones(text):
        return " ".join(g.phonemize(N.normalize(text), on_oov="lts"))

    # Every route that reaches a scale word. The year register matters most: it is bare
    # "mil", so before this EVERY year from 1000 to 2099 was affected.
    # NB "£1,500m" is deliberately NOT here: that is 1.5 BILLION, so it reads "un biliwn
    # pum can miliwn" and contains no mil at all. It was in this list on the first pass and
    # failed -- the test case was wrong, not the code.
    for text in ("1000", "1234.56", "50000", "1500", "17/07/1984", "1 Ionawr 1980"):
        assert "m ii l" in phones(text) or "v ii l" in phones(text), (
            f"{text!r} still has a short mil/fil: {phones(text)}")
    assert " m i l" not in phones("1234.56"), "short mil survived in 1234.56"
    # 2000-2099 go through the mutated form.
    assert "v ii l" in phones("2000") and "v ii l" in phones("1/1/2026")

    # NOT extended past what was auditioned. "miliwn"/"biliwn"/"miloedd" are polysyllabic
    # (ˈm i | l iu n): the syllable is open and their short "i" is correct. "cil"/"hil" are
    # the same closed-monosyllable rhyme class and are probably wrong too, but no number or
    # year reaches them and the owner scoped the fix to mil/fil.
    assert g.phonemize("miliwn", on_oov="lts") == ["ˈ", "m", "i", "|", "l", "iu", "n"]
    assert g.phonemize("biliwn", on_oov="lts") == ["ˈ", "b", "i", "|", "l", "iu", "n"]
    assert g.phonemize("miloedd", on_oov="lts") == ["ˈ", "m", "i", "|", "l", "oy", "dh"]
    assert g.phonemize("cil", on_oov="lts") == ["ˈ", "k", "i", "l"]
    assert g.phonemize("hil", on_oov="lts") == ["ˈ", "hh", "i", "l"]
    # This guard exists so nobody adds a pronunciation without the owner hearing it. Keep it
    # that way: widen the set ONLY alongside a recorded sign-off. The vowel-length pair is
    # separated from the brand names so a regression in one cannot be masked by the other.
    _VOWEL_LENGTH = {"mil", "fil"}
    # Brand names, owner-approved by ear 2026-09-04 (see docs/brand-pronunciation-overrides.md).
    # bangordict.dict records these with Welsh phonology, which is right for Welsh speech and
    # wrong for a screen reader on an English UI, where labels are too short for the sentence
    # router to reach its ~5-English-word threshold.
    _BRANDS = {
        "youtube", "google", "twitter", "adobe", "photoshop", "powerpoint", "ebay",
        "iphone", "ipad", "android",
        # concatenated, in no dictionary, emitted as two words
        "onedrive", "chromebook", "firestick", "fitbit", "tiktok", "deliveroo",
        # developer / interface vocabulary in no dictionary (1.3.1, docs/brand-pronunciation-overrides.md 3c)
        "readme", "changelog", "devops", "gitlab", "kubernetes",
        "techiaith",   # the organisation's name (3d)
    }
    assert set(_CY_PRON_OVERRIDE) == _VOWEL_LENGTH | _BRANDS, (
        "the override table changed without a recorded sign-off; if that is intended, update "
        "this set AND docs/brand-pronunciation-overrides.md")
    # camera/signal/telegram are mispronounced by the same mechanism but are ordinary Welsh
    # loanwords too, so an override would break Welsh prose. Owner ruled them out; assert it.
    assert not ({"camera", "signal", "telegram"} & set(_CY_PRON_OVERRIDE)), (
        "camera/signal/telegram must NOT be overridden -- they are real Welsh words")

    # THE POINT OF PUTTING THE FIX IN CODE. data_version hashes the emission policy, the id
    # map, the dictionary BYTES and (since 2026-09-04) the native English lexicon -- but
    # never this table. Editing bangordict.dict would change it, and the API's
    # models/piper/bangor.py hard-fails when it disagrees with the model config, so the
    # container would refuse to start until the HF config moved in lockstep.
    #
    # The pin moved once, deliberately, on 2026-09-07: b1edc63e35bb7a6f -> e015a51f4373ef2b.
    # _EMISSION_POLICY went v3 -> v4 (pos=on: heteronyms resolved from a POS tag, so one
    # spelling can emit different phones in different sentences), and two data files entered
    # the hash -- pos_{cy,en}.bin, which choose those readings, and cmudict_native.dict, which
    # had been OUTSIDE the hash while determining how every English word is pronounced. The
    # lexicon itself is unchanged: a same-week attempt to re-derive it as "Welsh English" was
    # measured 19 points further from Bangor's own transcriptions and audibly worse than the
    # deployed API, and was withdrawn before release.
    #
    # If this assertion fires again, it is a regression unless you meant it: an override
    # leaking into the hashed dictionary files, or a hashed data file regenerated without the
    # model configs (HF, API, every distro) being bumped in the same move.
    # 1.4.0 (2026-09-08): the per-word language prior data/lang/lang_prior.tsv joined the hash and
    # the emission policy went to v5 (route=prior) -- a deliberate bump, moved in lockstep with
    # the HF model config and the app configs. Before: e015a51f4373ef2b (1.2.0-1.3.x).
    assert g.data_version() == "718542836d1dcbdd", (
        "data_version moved: either the override has leaked into the hashed dictionary "
        "files, or the hashed English lexicon changed without a deliberate bump. The API "
        "will hard-fail at startup until the model config's phonemizer block matches")


def test_c_agrees_with_python_on_the_long_mil():
    """The C port must apply the same override, or the two diverge on every year.

    C inserts the override BEFORE loading the dictionaries and relies on wmap_put's
    keep-first rule; Python replaces the entry in the loaded table. Different mechanisms, so
    this differential is the only thing proving they agree. Only one parity corpus row
    ("yn 2026") contains a scale word, so `make check` alone barely exercises this.
    """
    import ctypes
    so = REPO / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
    if not so.exists():
        import pytest
        pytest.skip("libcy_phonemize.so not built")
    from techiaith.g2p.bangor_g2p import BangorG2P
    # cyp_create takes TWO arguments -- (core_dir, english_mode), see cy_phonemize.h -- and
    # BOTH must be declared and passed. This test used to declare argtypes with only ONE
    # c_char_p and call cyp_create with only ONE argument. ctypes then passed a single
    # argument into a two-parameter C function; the second parameter (english_mode) read
    # whatever was left in that register, and cyp_create's `strcmp(english_mode, ...)`
    # dereferenced it -- undefined behaviour. On x86-64 the leftover register contents vary
    # per process, which is why this crashed non-deterministically (ASLR/heap-layout
    # dependent, not input-dependent) instead of failing the same way every run. A one-arg
    # ctypes call against a two-arg C function fails silently on some interpreters and
    # segfaults on others -- the worst possible failure mode -- so always declare and pass
    # every parameter the header lists. Stated explicitly on both sides here, matching
    # BangorG2P's own default ("accented"), rather than relying on that default silently:
    # bindings/python/cy_phonemize.py's CyPhonemizer -- used by the (never-crashing)
    # differential fuzzers -- has always declared both, which is why only this one hand-
    # rolled ctypes call site was affected.
    g = BangorG2P(english_mode="accented")
    lib = ctypes.CDLL(str(so))
    lib.cyp_create.restype = ctypes.c_void_p
    lib.cyp_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.cyp_text_to_ids.argtypes = [ctypes.c_void_p, ctypes.c_char_p,
                                    ctypes.POINTER(ctypes.c_int32), ctypes.c_int]
    h = lib.cyp_create(str(REPO / "techiaith" / "g2p").encode(), b"accented")
    assert h, "cyp_create failed"
    buf = (ctypes.c_int32 * 4096)()

    def c_ids(text):
        n = lib.cyp_text_to_ids(h, text.encode(), buf, 4096)
        return list(buf[:n])

    for text in ("mil", "fil", "1000", "2000", "1234.56", "50000", "miliwn", "biliwn",
                 "miloedd", "cil", "hil", "1 Ionawr 1980", "17/07/1984", "yn 2026",
                 "1000000", "3000000000", "999"):
        assert c_ids(text) == g.text_to_ids(text), f"C/Python diverge on {text!r}"


def test_pounds_take_o_bunnoedd_from_a_thousand_up():
    """"Mil o bunnoedd" -- owner, 2026-07-28, answering with the phrase itself.

    What this settles was NOT a matter of taste. The SAME amount read two ways, decided only
    by how the author had typed it, which nobody had chosen:

        £1000000  ->  "un miliwn punt"        (digits)
        £1m       ->  "un miliwn o bunnoedd"  (magnitude suffix)

    The threshold is the scale-word tier, the owner's pick of three offered: at 1000 and
    above the plural, below it the singular. No corpus row exercises the DIGITS path over the
    threshold -- the only rows are "£1k" and "£1.5k" -- so make check cannot catch a
    regression here and this test is the coverage.
    """
    N = WelshNormalizer()

    # Below the threshold: untouched, including the hand-cased and mutated forms.
    for text, want in (("£1", "un bunt"), ("£5", "pum punt"), ("£7", "saith bunt"),
                       ("£11", "un deg un punt"), ("£25", "dau ddeg pump punt"),
                       ("£100", "can punt"), ("£200", "dau gan punt"),
                       ("£999", "naw cant naw deg naw punt")):
        assert N.normalize(text) == want, f"{text}: {N.normalize(text)!r}"

    # At and above it: the plural, and a BARE "mil".
    assert N.normalize("£1000") == "mil o bunnoedd"
    assert N.normalize("£1,000") == "mil o bunnoedd"
    assert N.normalize("£2000") == "dwy fil o bunnoedd"
    assert N.normalize("£1234") == "mil dau gant tri deg pedwar o bunnoedd"
    assert N.normalize("£100000") == "can mil o bunnoedd"

    # "cant" stops reducing to "can" above the threshold, and that is CORRECT rather than a
    # regression: _reduce_cant fires only where the numeral directly touches the noun, and
    # "o" now sits between them. £100 is below the threshold, noun still touching, so "can".
    assert N.normalize("£1500") == "mil pum cant o bunnoedd"
    assert "pum can o bunnoedd" not in N.normalize("£1500")

    # THE DEFECT ITSELF: the two spellings of one amount must now agree.
    for digits, suffix in (("£1000", "£1k"), ("£2000", "£2k"), ("£1000000", "£1m"),
                           ("£3000000000", "£3bn")):
        assert N.normalize(digits) == N.normalize(suffix), (
            f"{digits} and {suffix} are the same amount but read differently: "
            f"{N.normalize(digits)!r} vs {N.normalize(suffix)!r}")

    # "un miliwn"/"un biliwn" KEEP their "un". The owner's ruling was about "mil"; this is
    # what the suffix path has always shipped, so it is left alone rather than changed by
    # inference. A prefix test would have broken it -- "un miliwn".startswith("un mil").
    assert N.normalize("£1m") == "un miliwn o bunnoedd"
    assert N.normalize("£1000000") == "un miliwn o bunnoedd"
    assert N.normalize("£1bn") == "un biliwn o bunnoedd"
    assert not N.normalize("£1m").startswith("miliwn")

    # PENCE KEEP THE SINGULAR (owner): "o bunnoedd" mid-phrase is clumsy.
    assert N.normalize("£1234.56") == (
        "un mil dau gant tri deg pedwar punt pum deg chwech ceiniog")
    assert N.normalize("£1000.50") == "un mil punt pum deg ceiniog"
    assert "o bunnoedd" not in N.normalize("£1234.56")
    # ... and a .00-style zero pence is a pounds-only amount, so it takes the plural.
    assert N.normalize("£25.50") == "dau ddeg pump punt pum deg ceiniog"

    norm, _ = _c_normalizer()
    for t in ("£1", "£5", "£7", "£100", "£200", "£999", "£1000", "£1,000", "£1500",
              "£2000", "£1234", "£100000", "£1000000", "£1k", "£2k", "£1m", "£1bn",
              "£3bn", "£3000000000", "£1234.56", "£1000.50", "£25.50", "£1.07",
              "£999.99", "£1000000.99", "Mae'r gost yn £1000.", "£1000000000000"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_a_leading_zero_makes_a_digit_run_a_sequence_not_a_quantity():
    """Phone numbers. "01248 382000" read "un mil dau gant pedwar deg wyth tri chant...".

    Reported by the owner from the live service, 2026-07-28. NOT a regression, and that
    matters for anyone reading this later: 601be9c, the ref that ran in production for days,
    read phone numbers exactly as badly. Of 47 tricky inputs diffed across the two refs, 5
    differed and every one was a deliberate decision (un mil, saith gant/wyth gant, the
    idiomatic clock).

    THE RULE IS TAKEN FROM THE piper-cy VOICE, the other Piper voice on this service, which
    phonemizes through espeak-ng. Verified against espeak-ng 1.50 in the running container:
    it reads a digit run digit-by-digit exactly when it starts with a zero, and as a cardinal
    otherwise ("123" -> cardinal, "0123" -> "nul un dau tri"). A leading zero is the only
    signal in the text that says "these are digits, not an amount", and int() destroys it.

    We keep espeak's RULE and reject its WORD: it says "nul", which is not standard Welsh for
    zero. The owner chose "dim" -- how a Welsh speaker reads a phone number aloud, the
    counterpart of English "oh". "sero" was the alternative, rejected as too heavy repeated.

    NO PARITY CORPUS ROW HAS A LEADING-ZERO SEQUENCE, so `make check` cannot catch a
    regression in any of this. This test is the entire coverage.
    """
    N = WelshNormalizer()

    # A whole phone number, digit by digit -- including the groups after the first. Half a
    # number read as digits and the rest as a cardinal is no more usable than the original.
    assert N.normalize("01248 382000") == "dim un dau pedwar wyth tri wyth dau dim dim dim"
    assert N.normalize("01248 382 000") == "dim un dau pedwar wyth tri wyth dau dim dim dim"
    assert N.normalize("029 2018 0000") == "dim dau naw dau dim un wyth dim dim dim dim"
    assert N.normalize("0800 80 80 80") == "dim wyth dim dim wyth dim wyth dim wyth dim"
    # Separators are dropped, and the parenthesised and hyphenated styles behave the same.
    for style in ("01248 382000", "01248382000", "01248-382000", "(01248) 382000",
                  "(01248) 382 000"):
        assert N.normalize(style) == "dim un dau pedwar wyth tri wyth dau dim dim dim", style
    # In a sentence.
    assert N.normalize("Ffoniwch 01248 382000 heddiw.") == (
        "ffoniwch dim un dau pedwar wyth tri wyth dau dim dim dim heddiw.")

    # Shorter leading-zero runs are still sequences, just not phone-shaped.
    assert N.normalize("007") == "dim dim saith"
    assert N.normalize("0044") == "dim dim pedwar pedwar"
    assert N.normalize("00") == "dim dim"
    # A BARE zero is not a sequence: it keeps the numeral the decimal pass uses.
    assert N.normalize("0") == "sero"

    # A LEADING ZERO ONLY COUNTS AT THE START OF A NUMBER. Without the (?<![\w,.]) guard the
    # "000" GROUP of "1,000" matched -- there is a word boundary after a comma -- and "un mil"
    # became "un dim dim dim". The parity corpus caught that on the first regeneration.
    assert N.normalize("1,000") == "un mil"
    assert N.normalize("1,000,000") == "un miliwn"
    assert N.normalize("£1,000") == "mil o bunnoedd"
    assert N.normalize("1.0005") == "un pwynt sero sero sero pump"
    # ... nor FUSED inside a word: "a007" must never become "adim dim saith". Since the
    # digit/letter splitter closed the section-G mirror gap, the run reads -- as its own,
    # SEPARATED word: the splitter's space is what lets _DIGIT_SEQ's untouched (?<![\w,.])
    # guard see a real boundary.
    assert N.normalize("a007") == "a dim dim saith"
    assert N.normalize("x0800") == "x dim wyth dim dim"
    assert "adim" not in N.normalize("a007")
    assert "xdim" not in N.normalize("x0800")

    # The passes that understand these shapes must claim them first.
    assert N.normalize("07:00") == "saith o'r gloch"
    assert N.normalize("01/01/1980") == "y cyntaf o ionawr mil naw wyth deg"
    assert N.normalize("0.5") == "sero pwynt pump"
    # No leading zero: still a cardinal, unchanged.
    assert N.normalize("999") == "naw cant naw deg naw"
    assert N.normalize("123") == "cant dau ddeg tri"

    norm, _ = _c_normalizer()
    for t in ("01248 382000", "01248 382 000", "(01248) 382000", "01248-382000", "01248382000",
              "029 2018 0000", "0800 80 80 80", "07700 900123", "007", "0044", "00", "0",
              "1,000", "1,000,000", "£1,000", "1.0005", "0.5", "07:00", "01/01/1980", "999",
              "123", "a007", "x0800", "abc0800", "90:00", "99:59", "tud. 007",
              "Ffoniwch 01248 382000 heddiw.", "Ffoniwch (029) 2018 0000."):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_characters_that_used_to_glue_words_into_nonwords():
    """Unhandled characters did not drop cleanly -- they MERGED their neighbours.

    Found by comparing against the piper-cy voice (espeak-ng), 2026-07-28. A character we did
    not verbalise stayed in the text, and because it is not a phone it vanished at the phone
    layer, leaving its two neighbours as one token for LTS to guess at:

        3.5kg  -> "tri.pum cilogram"   -> the model heard  "tripum cilogram"
        5+3    -> "pump+tri"           ->                   "pumptri"
        2x3    -> "dauxtri"            ->                   "docstri"
        5°C    -> "pump°c"             ->                   "pumpc"

    Worse for "@", which IS a phone in the Bangor inventory -- the schwa -- so an email
    address was read as a vowel rather than dropped.

    Wording all from the owner, 2026-07-28: "Tri pwynt pum cilogram", "Pump plws tri",
    "dau lluosi tri", "Pump gradd celsiws", "Post at bangor dot ac dot wc", "Penod pedwar".

    NO PARITY CORPUS ROW CONTAINS ANY OF THESE, so make check is byte-identical before and
    after the whole change and cannot catch a regression in it. This test is the coverage.
    """
    N = WelshNormalizer()

    # Decimal + unit. This was a PASS-ORDER bug: _UNIT runs before _DECIMAL (units must claim
    # their own digits first), so it ate the "5kg" and orphaned the "3.".
    assert N.normalize("3.5kg") == "tri pwynt pum cilogram"
    assert N.normalize("3.5 kg") == "tri pwynt pum cilogram"
    assert N.normalize("0.5l") == "sero pwynt pum litr"
    assert N.normalize("1.5km") == "un pwynt pum cilomedr"
    # The TAIL takes the connected form: a decimal numeral has no single value to look up, so
    # the rule has to be positional -- about the word that touches the noun.
    assert N.normalize("6.5kg").endswith("pum cilogram")
    assert "." not in N.normalize("3.5kg")
    # Integers unchanged, including the 2/3/6 mutation branches.
    for text, want in (("5kg", "pum cilogram"), ("2kg", "dau gilogram"),
                       ("3kg", "tri chilogram"), ("6kg", "chwe chilogram"),
                       ("100m", "can metr")):
        assert N.normalize(text) == want, text

    # Operators and degrees.
    assert N.normalize("5+3") == "pump plws tri"
    assert N.normalize("5 + 3") == "pump plws tri"
    assert N.normalize("2x3") == "dau lluosi tri"
    assert N.normalize("2×3") == "dau lluosi tri"          # U+00D7 as well as ASCII x
    assert N.normalize("5°C") == "pump gradd celsiws"      # Welsh "celsiws", not "Celsius"
    assert N.normalize("20°C") == "dau ddeg gradd celsiws"
    assert N.normalize("90°") == "naw deg gradd"
    # The degree pass must run BEFORE _DECIMAL, or the digit before "°" is already a word.
    assert N.normalize("98.6°F") == "naw deg wyth pwynt chwech gradd fahrenheit"
    assert N.normalize("Mae'n 20°C heddiw.") == "mae'n dau ddeg gradd celsiws heddiw."
    for t in ("5+3", "2x3", "5°C", "3.5kg", "98.6°F"):
        for ch in "+x×°.":
            assert ch not in N.normalize(t), f"{ch!r} survived in {t!r}: {N.normalize(t)!r}"

    # Emails and URLs.
    assert N.normalize("post@bangor.ac.uk") == "post at bangor dot ac dot wc"
    # "www" spells letter by letter -- read as a word it is unpronounceable. Owner
    # 2026-07-28: "We should fix www". "·" is the acronym pass's own letter separator, so
    # this routes into the existing letter-naming path rather than a new one.
    assert N.normalize("www.bangor.ac.uk") == "w·w·w dot bangor dot ac dot wc"
    assert N.normalize("https://www.bangor.ac.uk") == "w·w·w dot bangor dot ac dot wc"
    assert "@" not in N.normalize("e-bost: post@bangor.ac.uk")
    # A bare dotted token with no @ and no www is left alone: it is indistinguishable from a
    # word followed by an abbreviation, and reading it would be a guess.
    assert N.normalize("bangor.ac.uk") == "bangor.ac.uk"

    # Roman numerals -> the cardinal.
    assert N.normalize("Pennod IV") == "pennod pedwar"
    # (Harri VIII moved to the regnal-ordinal block below when the owner ruled on it the
    # same day: "Elisabeth yr ail is correct".)
    assert N.normalize("Pennod XII") == "pennod un deg dau"
    assert N.normalize("MCMLXXXIV") == "un mil naw cant wyth deg pedwar"
    # NOT converted: words that are also Roman letters, and non-canonical numerals. The
    # validator is a ROUND-TRIP -- int and back must be identical -- which is what rejects
    # these without a second grammar. An earlier regex-only version could match the EMPTY
    # string, and "DID" came out as "serodid".
    for t in ("MIX", "DID", "IIII", "VV", "IC", "XXXX"):
        assert "dim" not in N.normalize(t) and "sero" not in N.normalize(t), t
        assert not N.normalize(t)[0].isdigit(), t
    # A REGNAL number takes the ORDINAL with its article. Owner 2026-07-28: "Elisabeth yr ail
    # is correct". A structural noun keeps the cardinal, which the same owner confirmed for
    # "Pennod IV". Both are wanted, so the two have to be told apart, and since nothing
    # reliably says "personal name" the DEFAULT is the ordinal with a list of structural nouns
    # as the exception -- that vocabulary is small and nearly closed where names are not.
    assert N.normalize("Elizabeth II") == "elizabeth yr ail"
    assert N.normalize("Harri VIII") == "harri yr wythfed"      # "yr" before a vowel
    assert N.normalize("Edward VII") == "edward y seithfed"     # "y" before a consonant
    assert N.normalize("Sior III") == "sior y trydydd"
    assert N.normalize("Louis XIV") == "louis y pedwerydd ar ddeg"
    for structural in ("Pennod IV", "Rhan III", "Cyfrol II", "Tabl VI"):
        out = N.normalize(structural)
        assert not out.split()[1].startswith(("y ", "yr ")) and " yr " not in out, out
    assert N.normalize("Cyfrol II") == "cyfrol dau"
    assert N.normalize("Adran XII") == "adran un deg dau"

    # A single letter is never a numeral, and non-Roman tokens are untouched by this
    # pass (BBC reads as the dictionary word "bbc", HMS is OOV and letter-spells —
    # either way the Roman pass must not have claimed them).
    assert N.normalize("I") == "i"
    assert N.normalize("BBC") == "bbc"
    assert N.normalize("HMS") == "h·m·s"
    assert N.normalize("S4C") == "s pedwar c"
    # The owner confirmed these two read correctly as they were; they must not change.
    assert N.normalize("LL57 2DG") == "l·l pum deg saith dau d·g"
    assert N.normalize("A470") == "a pedwar cant saith deg"

    norm, _ = _c_normalizer()
    for t in ("3.5kg", "3.5 kg", "0.5l", "1.5km", "6.5kg", "5kg", "2kg", "3kg", "6kg", "100m",
              "5+3", "5 + 3", "2x3", "2×3", "5°C", "20°C", "90°", "98.6°F", "1.5+2.5",
              "Mae'n 20°C heddiw.", "post@bangor.ac.uk", "e-bost: post@bangor.ac.uk",
              "www.bangor.ac.uk", "https://www.bangor.ac.uk", "bangor.ac.uk", "Pennod IV",
              "Harri VIII", "Pennod XII", "MCMLXXXIV", "MIX", "DID", "IIII", "VV", "IC",
              "XXXX", "CCC", "BBC", "S4C", "I", "V", "LL57 2DG", "A470", "Elizabeth II",
              "Harri VIII", "Edward VII", "Sior III", "Louis XIV", "Pennod IV", "Rhan III",
              "Cyfrol II", "Adran XII", "PENNOD IV", "WWW.BANGOR.AC.UK", "3ydd",
              "1 Ionawr 1980", "17/07/1984"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_emoji_are_read_with_welsh_names_from_cldr():
    """Emoji were DROPPED: "Da iawn 👍" read "da iawn" and the emoji contributed nothing.

    Owner 2026-07-28: they should be read. The names come from the piper-cy voice, the same
    reference the phone-number rule came from -- espeak-ng's cy voice already carries a full
    Welsh emoji set (CLDR-derived), and `espeak-ng -v cy -q -X` prints the replacement as
    WORDS ("Replace: ❤   calon goch"), so the table is EXTRACTED rather than translated.
    1424 entries of existing idiomatic Welsh, 258 of them flags.

    The sweep was restricted to genuine emoji blocks on purpose. A first pass over a wider
    range pulled in espeak's ordinary symbol dictionary, which is not emoji and is partly
    ENGLISH -- "+" -> "plus", "₨" -> "rupee" -- and would have regressed the "plws" decision
    made hours earlier. The three assertions below are that guard.
    """
    from techiaith.g2p.welsh_normalize import _EMOJI
    N = WelshNormalizer()

    assert len(_EMOJI) > 1000, f"emoji table looks truncated: {len(_EMOJI)} entries"
    assert N.normalize("Da iawn 👍") == "da iawn bys bawd i fyny"
    assert N.normalize("Diolch ❤") == "diolch calon goch"
    assert N.normalize("😀") == "wyneb yn gwenu â cheg agored"
    assert N.normalize("🔥") == "tân"
    # A variation selector must find the SAME name: "❤️" is "❤" plus U+FE0F.
    assert N.normalize("Diolch ❤️") == N.normalize("Diolch ❤")
    # Flags are two codepoints and must beat either half of themselves -- the table is sorted
    # longest-first and the matcher takes the first hit, so that ORDER is the rule.
    assert N.normalize("🇬🇧") == "baner y deyrnas unedig"
    assert len([k for k in _EMOJI if len(k) == 2]) > 200, "flag sequences missing"
    # Directly against a word: the name must not glue to it.
    assert N.normalize("Da iawn👍") == "da iawn bys bawd i fyny"
    # Repeated emoji each read.
    assert N.normalize("🔥🔥🔥") == "tân tân tân"

    # THE ENGLISH-LEAKAGE GUARD. These three came through a wider first sweep and are NOT
    # emoji; "+" in particular already has a Welsh reading from the same day's work.
    for ch in "+€₨":
        assert ch not in _EMOJI, f"{ch!r} is in the emoji table: the sweep was too wide"
    assert N.normalize("5+3") == "pump plws tri"
    english = {"plus", "rupee", "face", "heart", "flag", "smiling", "hand", "dog"}
    leaked = [(c, n) for c, n in _EMOJI.items() if set(n.lower().split()) & english]
    assert not leaked, f"English names leaked from espeak's symbol dictionary: {leaked[:5]}"

    # THE WELSH FLAG. 🏴󠁧󠁢󠁷󠁬󠁳󠁿 is a TAG SEQUENCE: "🏴" plus "gbwls" in the tag block plus a
    # cancel. espeak does NOT know these -- it falls back to the bare "🏴", "chwifio baner
    # ddu" (waving black flag), and leaks an English "black flag" as a second replacement --
    # so the three UK national flags are the ONLY hand-written entries in an otherwise
    # extracted table. For a Welsh TTS, the Welsh flag reading "waving black flag" was the
    # wrong default to leave in place.
    WALES = "\U0001F3F4\U000e0067\U000e0062\U000e0077\U000e006c\U000e0073\U000e007f"
    assert N.normalize(WALES) == "baner cymru"
    assert N.normalize("Baner " + WALES) == "baner baner cymru"
    # Tag characters are stripped AFTER matching, never before: they are PART of the sequence,
    # and the table is sorted longest-first so the 7-codepoint flag beats the bare "🏴".
    # Anything left over is a tag flag with no name, which must not reach the phone layer raw.
    assert "\U000e0067" not in N.normalize(WALES)
    assert N.normalize("\U0001F3F4") == "chwifio baner ddu"      # the bare flag still works

    # Text with no emoji is untouched.
    assert N.normalize("dim emoji yma") == "dim emoji yma"

    norm, _ = _c_normalizer()
    for t in ("Da iawn 👍", "Diolch ❤", "Diolch ❤️", "😀", "🔥🔥🔥", "🇬🇧", "🇨🇾", "Da iawn👍",
              "Cacen 🎂!", "😂 a 🥰", "👨‍👩‍👧", "⚠ Rhybudd", "dim emoji yma", "5+3",
              "Mae'n heulog ☀", "Parti 🎉 heno", WALES, "Baner " + WALES,
              "\U0001F3F4", "\U0001F3F3",
              "\U0001F3F4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_leading_zero_run_keeps_its_zeros_when_glued_to_letters():
    """A leading zero means digits even when a letter follows the run.

    _DIGIT_SEQ ended in \\b, so a run followed by a letter failed to match at all and fell
    through to _INTEGER -- where int("0800") is 800. "0800x" read "wyth gantx": eight
    hundred, both zeros silently gone, and fused into the x so the whole thing went to LTS as
    one nonword. Measured 2026-07-29.
    """
    n = WelshNormalizer()
    out = n.normalize("0800x")
    assert out.split()[:4] == ["dim", "wyth", "dim", "dim"], out
    assert "wyth gant" not in out, f"still reading the run as a cardinal: {out!r}"
    assert "dimx" not in out and "dim dimx" not in out, f"still fused: {out!r}"
    assert out.startswith("dim wyth dim dim ")


def test_leading_zero_fix_does_not_touch_the_cases_that_already_worked():
    """The lookbehind is load-bearing; d27543e's regressions must not come back."""
    n = WelshNormalizer()
    # a thousands comma has a word boundary after it -- this must NOT become "un dim dim dim"
    assert n.normalize("1,000") == "un mil"
    # a real phone number, unchanged
    assert n.normalize("01248 382000") == (
        "dim un dau pedwar wyth tri wyth dau dim dim dim")
    # a run after a letter now reads through the splitter's space -- SEPARATED, never
    # fused ("adim dim saith" is d27543e's regression and must not come back)
    assert n.normalize("a007") == "a dim dim saith"
    assert "adim" not in n.normalize("a007")
    # a bare zero is not a sequence
    assert n.normalize("0") == "sero"


def test_letter_adjacent_symbols_take_their_approved_words_or_the_space_floor():
    """"+"/"="/"@" between word characters read their already-approved words ("a+b" ->
    "a plws b"); "*" joins the "/"/":" space floor (no approved word -- item 10 still
    owns the symbol registers). "C++"/"A+"/"A+ grade" stay codes: both sides must be
    word characters."""
    N = WelshNormalizer()
    for text, want in [
        ("a+b", "a plws b"), ("a=b", "a yn hafal i b"), ("a@b", "a at b"),
        ("a*b", "a b"), ("2*3", "dau tri"), ("5*5", "pump pump"),
        ("gôl*sgôr", "gôl sgôr"),
        ("2 + 2 = 4", "dau plws dau yn hafal i pedwar"),   # space-bounded, unchanged
        ("C++", "c++"), ("A+", "a+"), ("A+ grade", "a+ grade"), ("a+ b", "a+ b"),
    ]:
        assert N.normalize(text) == want, (text, N.normalize(text))
    norm, _ = _c_normalizer()
    for t in ("a+b", "a=b", "a@b", "a*b", "2*3", "5*5", "gôl*sgôr", "2 + 2 = 4",
              "C++", "A+", "A+ grade", "a+ b", "ẁ+ŷ", "α+β"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"


def test_digit_letter_splitter_separates_what_the_passes_then_verbalise():
    """FOLLOWUPS section G's "general digit/letter peeling job", closed: one splitter pass
    (both directions, ASCII digits <-> Latin letters/_) placed after every legitimate
    letter-adjacent-digit consumer and before the remaining number passes, plus a trailing
    separator inside the two passes that run BEFORE it and glue their REPLACEMENT
    (currency, percent). All nine measured glue shapes, one per number pass."""
    N = WelshNormalizer()
    for text, want in [
        ("800x", "wyth gant x"), ("5x", "pump x"), ("3.5x", "tri pwynt pump x"),
        ("50%x", "pum deg y cant x"), ("1/2x", "un dau x"), ("£5x", "pum punt x"),
        ("1,000x", "un mil x"), ("12:30x", "un deg dau tri deg x"),
        ("2026x", "dwy fil dau ddeg chwech x"),
        # the mirror direction (letter then digits) -- the old frozen Group-2 gap
        ("x05", "x dim pump"), ("0abc", "sero abc"), ("0d", "sero d"),
        ("05lhn0", "dim pump lhn sero"), ("00c3", "dim dim c tri"),
        # codes fixed for free
        ("covid19", "covid un deg naw"), ("h2o", "h dau o"), ("x800", "x wyth gant"),
        ("_05", "_ dim pump"), ("5_x", "pump _x"),
        ("£5million", "pum punt million"),
    ]:
        assert N.normalize(text) == want, (text, N.normalize(text))
    # "s4c" now reads like "S4C": the splitter runs AFTER _PENCE, whose (?<![A-Za-z])
    # lookbehind has already refused the "4c" -- so no fourpence, and the lower-case
    # code matches the upper-case one.
    assert N.normalize("s4c") == "s pedwar c" == N.normalize("S4C")
    assert "ceiniog" not in N.normalize("s4c")
    # The suffix consumers keep their claims: the splitter must run after ALL of them.
    for text, want in [("£5M", "pum miliwn o bunnoedd"), ("5km", "pum cilomedr"),
                       ("50p", "pum deg ceiniog"), ("3af", "trydydd"),
                       ("7pm", "saith o'r gloch y prynhawn")]:
        assert N.normalize(text) == want, (text, N.normalize(text))
    # The year-group guard (mirrors C's !word_after): letters after a year mean it is
    # NOT a date-with-year -- before the guard, Python read the YEAR register here and
    # C the plain cardinal, a live divergence the fuzzers never fed.
    assert N.normalize("1 Ionawr 2026x") == "y cyntaf o ionawr dwy fil dau ddeg chwech x"
    assert N.normalize("1 Ionawr 2026") == "y cyntaf o ionawr dwy fil a dau ddeg chwech"
    # Latin-only, both directions: the accepted section-G divergence is neither widened
    # nor fixed ("0800α" keeps Python's older Unicode-wide separator; "٣05" is invisible
    # to the splitter on both sides).
    assert N.normalize("0800α") == "dim wyth dim dim α"
    assert N.normalize("٣05") == "٣pump"
    # hyphens and compounds untouched
    assert N.normalize("b-a-ch") == "b-a-ch"
    assert N.normalize("gogledd-ddwyrain") == "gogledd-ddwyrain"

    norm, _ = _c_normalizer()
    # "٣05" is deliberately NOT in this loop: it is the recorded PRE-EXISTING divergence
    # (py "٣pump" vs C "٣dim pump" -- Python's \d-based lookbehinds see ٣ as a word char,
    # C's cp_is_word does not), untouched by the splitter and excluded from the fuzzers
    # for the same reason. The Python-only assert above pins our side of it.
    for t in ("800x", "5x", "3.5x", "50%x", "1/2x", "£5x", "1,000x", "12:30x", "2026x",
              "x05", "0abc", "0d", "05lhn0", "00c3", "covid19", "h2o", "x800", "_05",
              "5_x", "£5million", "s4c", "S4C", "£5M", "5km", "50p", "3af", "7pm",
              "1 Ionawr 2026x", "1 Ionawr 2026", "1 Ionawr 20261", "25 Rhagfyr 1999abc",
              "ê9p", "b-a-ch", "gogledd-ddwyrain", "ffon:01248", "01248-382000"):
        assert norm(t) == N.normalize(t), f"C/Python disagree on {t!r}"
