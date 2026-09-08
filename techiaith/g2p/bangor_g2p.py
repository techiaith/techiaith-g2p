"""Bangor Welsh G2P — Python reference implementation (Workstream P, task P1).

The single, authoritative reference for turning Welsh (and code-switched English)
text into the phoneme-id sequence the retrained Piper model consumes. The C port
(`libcy_phonemize`, P7) and the training `preprocess.py` path (P4) must reproduce
this byte-for-byte; the golden tests (tests/golden/) enforce it.

Scope of P1: dictionary-lookup G2P over the vendored Bangor dictionaries.
Out-of-vocabulary letter-to-sound (P3) and text normalization (P2) are NOT here
yet — OOV words raise by default so nothing is ever silently dropped.

Contract: docs/PARITY.md. Id-map: bangor_phoneme_id_map.json.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, NamedTuple

from .bangor_lts import lts
from .canonical import decimal_value
from .english_g2p import EnglishG2P, _LEX as _ENGLISH_LEXICON
from . import pos_tagger
from .lang_id import classify_word
from .welsh_normalize import ACRONYM_JOIN, WelshNormalizer, _pause_punct, _pause_punct_early

_HERE = Path(__file__).resolve().parent
_DEFAULT_IDMAP = _HERE / "bangor_phoneme_id_map.json"
_DEFAULT_DATA = _HERE / "data" / "geiriadur-ynganu-bangor"
_POS_DATA = _HERE / "data" / "pos"
_LANG_PRIOR = _HERE / "data" / "lang" / "lang_prior.tsv"

# Lookup priority: native Welsh, then proper nouns, then English, then CMUdict.
_DICT_ORDER = ["bangordict.dict", "bangordict.xx.dict", "bangordict.en.dict", "cmudict.dict"]

STRESS = "ˈ"
SYLLABLE = "|"
WORD_SEP = " "

# Punctuation marks emitted as their own pause/structural tokens (each already has an
# id in bangor_phoneme_id_map.json: . , ? ! ; : ( ) " … —). These are what let the
# model learn punctuation-conditioned pauses. Word-internal ' and - are deliberately
# NOT here — they stay inside the word as Welsh clitics/compounds (part of lexicon
# keys, e.g. "i'r", "gogledd-ddwyrain").
#
# INTERIOR members peel too (see _segment): "ie!na" used to fuse into one LTS nonword
# with the "!" silently dropped -- FOLLOWUPS section G's word-internal punctuation
# class. Peeling re-tokenises into ids the model already renders (the pause ids 7-19
# are trained, verified live on the deployed model -- docs/PARITY.md section 4), so
# _EMISSION_POLICY is deliberately NOT bumped and data_version must not move.
_PUNCT = ".,;:!?()\"…—"
# Alphabetic runs for _number_lang: str.isalpha() as a class -- letters only, so no digit
# or apostrophe can be part of a token. Mirrored in C by cyp__cp_is_alpha over code points.
_ALPHA_RUN = re.compile(r"[^\W\d_]+(?:['\u2019][^\W\d_]+)*")   # "mae'r", "o'clock" are one word
# Per-word language prior (data/lang/lang_prior.tsv, scripts/gen_lang_prior.py): how Welsh or how
# English each word is, as 16 x the log-odds of its frequency in Welsh text (corpws-brawddegau-
# tagiedig, CC0) versus English text (MASC 3.0.0, CC BY 3.0 US). Positive is Welsh. A sentence's
# language is the SIGN of the sum over its words; 0 is no evidence (Welsh, or the surrounding
# decision). This replaces the exclusive-word count and the hand-made function-word lists of 1.3.x
# (owner, 2026-09-08: "Learn more" read "mor-eh" because "more" is a Welsh-dictionary loan and one
# English-only word was not enough). Measured on held-out sentences: Welsh 99.6% / English 99.1%
# against 99.6% / 94.6% for the old rule; 18 of 26 everyday English labels that routed Welsh now
# route English. Details: docs/text-structure-programme.md §3.7.
_PRIOR_FALLBACK = 16       # a word in neither corpus: +-1 nat (x16) from dictionary exclusivity
_PRIOR_STRONG = 32         # |weight| from which a word is strong evidence (clause splitting)
_PRIOR_MIN = 8             # |score| below this (half a nat) is no decision: "ab" at -6 must not flip
_WELSH_LETTERS = frozenset({"ch", "dd", "ff", "ng", "ll", "ph", "rh", "th"})
_LETTER_WORDS = frozenset({"o", "y"})   # the letters that are words: Welsh "of", "the"
# Text STRUCTURE (docs/text-structure-programme.md §3). A sentence ends at a run of . ! ? … before
# whitespace when an upper-case letter, a digit, a quote or the end follows (the apps' guard); a
# newline is a LINE boundary, a blank line a PARAGRAPH. The model realises none of these as a pause
# (measured: a mid-utterance "." is 80 ms of silence, a plain space 124), so consumers render each
# segment as its own pass and insert silence by boundary kind -- these constants, shared by the API
# and the apps through cyp_boundary_gap_ms, so device and API sound the same. Tuned by ear.
BOUNDARY_GAP_MS = {"sentence": 250, "line": 350, "paragraph": 600, "end": 0}
_QUOTES = "\"'«‘“"
_SENT_END = ".!?…"
_NO_FULL_STOP_AFTER = ".!?…:;,"   # a heading or list line ending in one of these keeps its own pause
# A single newline after a LONG line with no terminal punctuation is a soft wrap (text copied
# from a phone-width layout), not a heading: "...or use the Live⏎Recognition Rotor." is one
# sentence. Headings and list lines are short; wrapped lines are not.
_SOFT_WRAP_MIN_CHARS = 40
_LINE_TERMINAL = ".!?…:;"


class Segment(NamedTuple):
    """One rendering unit of an utterance: a sentence, a heading, a list line."""
    text: str            # the segment as normalised (structure punctuation already applied)
    tokens: List[str]    # phones, WORD_SEP-separated, no BOS/EOS
    ids: List[int]       # the interleaved ids of THIS segment alone (BOS ... EOS)
    boundary: str        # what follows it: "sentence" | "line" | "paragraph" | "end"
    number_lang: str     # the language its digits were read in
    phone_lang: str      # the language its phones were routed to


def _load_lang_prior(path: Path) -> Dict[str, int]:
    table: Dict[str, int] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line or line[0] == "#":
            continue
        w, _, v = line.partition("\t")
        table[w] = int(v)
    return table
# Whitespace for the sentence/clause splitter: ASCII only, so the C mirror is exact.
_NL_WS = " \t\r\n"
_NL_MAX_SPANS = 2048
# Title abbreviations the normaliser expands with an optional dot: a "." after one is not a
# sentence end ("Dr. Jones"). Same set in cy_phonemize.c (nl_title_before).
_NL_TITLES = frozenset({"dr", "mr", "mrs", "ms"})
# An interior run of _PUNCT members, for _segment's split. The capturing group keeps
# the runs in re.split's output so they can be re-attached as lead/trail punctuation.
_INTERIOR_PUNCT = re.compile("([" + re.escape(_PUNCT) + "]+)")

# Policy string folded into data_version so any emission-policy change invalidates
# trained models (see docs/PARITY.md §4). v2 adds punctuation/pause emission (v1
# dropped all punctuation, so the model could not pause on it). v3 adds Welsh
# letter-name interception for isolated consonant letters and digraphs (previously
# a bare letter fell through the lexicon to an unpronounceable bare phone).
# v4 (2026-09-07) records the POS front end: heteronyms are resolved from a tag rather than
# from a single fixed reading per spelling, so the same word can now emit different phones in
# different sentences. The English LEXICON is unchanged from v3 -- a 2026-09-04 attempt to
# re-derive it as "Welsh English" by rule was measured 19 points further from Bangor's own
# transcriptions and audibly worse than the deployed API, and was withdrawn; the model was
# trained with these labels and they are what sounds right. The POS models and the lexicon
# are hashed below so a change to either moves data_version.
_EMISSION_POLICY = "v5:stress=on;syllable=on;wordsep=on;punct=on;letters=cy-names;acronyms=en-runs;pos=on;route=prior+excl;interleave=bos-pad-id-pad-eos"

# Welsh letter names for isolated consonant letters and digraphs, as phone tokens
# (sources: the dictionaries' shadowed (nmcy) entries + the reference alphabet in
# welsh_normalize's docs, both since confirmed against Tabl 1 of the techiaith verbatim
# transcription guidelines -- every entry matches, digraphs included). Vowels are absent
# from THIS table only because they need two forms, not because they have no letter name:
# see _CY_VOWEL_SOLO (a letter alone) and _CY_VOWEL_SPELLED (a letter inside a spell-out
# run) below. The claim that once stood here -- that a vowel's letter name is just the
# function word -- is what produced "llaw" -> "ell, a, double-you".
# In native english_mode an English-context sentence bypasses this table so single
# letters get their English names from CMUdict (b -> "bee"); digraphs are Welsh
# letters and always use it.
_CY_LETTER_NAMES: Dict[str, List[str]] = {
    "b": [STRESS, "b", "ii"],        # bî
    "c": [STRESS, "e", "k"],         # èc
    "d": [STRESS, "d", "ii"],        # dî
    "f": [STRESS, "e", "v"],         # èf
    "g": [STRESS, "e", "g"],         # èg
    "h": [STRESS, "aay", "ch"],      # aets
    "j": [STRESS, "jh", "ee"],       # jê
    "k": [STRESS, "k", "ee"],        # cê — K is absent from the traditional alphabet, so
                                     # Tabl 1 of the verbatim transcription guidelines has
                                     # no entry and it falls back to Tabl 2's "ke": the
                                     # same route that already gives q -> ciw, x -> ecs.
                                     # Confirmed on issue #5 and by ear.
    "l": [STRESS, "e", "l"],         # èl
    "m": [STRESS, "e", "m"],         # èm
    "n": [STRESS, "e", "n"],         # èn
    "p": [STRESS, "p", "ii"],        # pî
    "q": [STRESS, "k", "iu"],        # ciw
    "r": [STRESS, "e", "r"],         # èr
    "s": [STRESS, "e", "s"],         # ès
    "t": [STRESS, "t", "ii"],        # tî
    "v": [STRESS, "v", "ii"],        # fî
    "x": [STRESS, "e", "k", "s"],    # ècs
    "z": [STRESS, "z", "e", "d"],    # zèd
}
# Isolated-VOWEL keystroke names. Vowels are also real Welsh words (i="to", o="from",
# a="and", y="the"), so — unlike consonants — we only spell a vowel as a letter when it
# is the ENTIRE utterance (a single typed key), never a one-letter word inside a
# sentence. I and O came out as ultra-short /ɪ/,/ɔ/, and W resolved to the English
# "double-u"; here they get their long Welsh letter names /iː/, /oː/, /uː/.
# 2026-07-27: a native speaker listened to candidates for the
# remaining letters and picked long/held renderings for a/e/u/y too — the bare vowels
# were too short to read as letter names (y was the shortest of all 26 letters at
# 0.30s). â was also compared and REJECTED: the owner preferred the plain bare 'aa'
# already used for the â lexicon fallback, so â is deliberately NOT in this table.
_CY_VOWEL_SOLO: Dict[str, List[str]] = {
    "a": [STRESS, "aa", "aa"],           # long /aː/ hold (user-picked 2026-07-27)
    "e": [STRESS, "ee", "ee"],           # long /eː/ hold (user-picked 2026-07-27)
    "i": [STRESS, "i", "ii"],            # /ɪ iː/ short→long glide (user-picked)
    "o": [STRESS, "oo", "oo", "oo"],     # long /oː/ hold (user-picked; single was too short)
    "u": [STRESS, "iu", "iu"],           # /iu/ held twice, one token (user-picked 2026-07-27)
    "w": [STRESS, "uu"],                 # /uː/  (Welsh W, not "double-u")
    "y": [STRESS, "@", "@"],             # /@/ held twice (user-picked 2026-07-27)
}
# Vowel names for a letter inside a SPELL-OUT RUN ("kilo" -> cê; î; èl; ô), as distinct
# from _CY_VOWEL_SOLO above, which is one letter alone as the whole utterance.
#
# The two tables differ because the two contexts were auditioned separately and the owner
# preferred different lengths in each -- which is coherent: a letter alone has no
# neighbours to mark it, so it needs the extra hold that _CY_VOWEL_SOLO gives it, while
# inside a run the surrounding letters supply that context and the same hold drags.
# "o" is the clearest case: the single /oː/ was explicitly rejected as too short for the
# isolated keystroke, and preferred over the triple inside a run.
#
# Only i, o and y move; a, e, u and w keep the isolated forms, which were auditioned
# inside runs too (bach, cwm, llaw) and approved there. Chosen by ear across 31 words on
# 2026-07-27 -- see the comparison artifact referenced in that day's commit.
#
# NOTE: y is off the schwa entirely. A stressed isolated /@/ was heard as "yr": the phone
# inventory carries a dedicated @r (r-coloured schwa) beside @, and in a bilingual model
# the English NURSE/lettER vowels live there. "yy" also matches what the ACCENTED ŷ
# already renders as, so the plain and circumflexed letters now agree.
_CY_VOWEL_SPELLED: Dict[str, List[str]] = {
    **_CY_VOWEL_SOLO,
    "i": [STRESS, "ii"],                 # was ˈ i ii  -- the glide read as two letters
    "o": [STRESS, "oo"],                 # was ˈ oo oo oo (a triple) -- too slow in a run
    "y": [STRESS, "yy"],                 # was ˈ @ @    -- the schwa picked up an r
}
_CY_DIGRAPH_NAMES: Dict[str, List[str]] = {
    "ch": [STRESS, "e", "x"],        # èch
    "dd": [STRESS, "e", "dh"],       # èdd
    "ff": [STRESS, "e", "f"],        # èff
    "ng": [STRESS, "e", "ng"],       # èng
    "ll": [STRESS, "e", "lh"],       # èll
    "ph": [STRESS, "f", "ii"],       # ffi
    "rh": [STRESS, "rh", "ii"],      # rhi
    "th": [STRESS, "e", "th"],       # èth
}


def _is_solo_letter_unit(part: str) -> bool:
    """True if `part` is exactly one Welsh alphabet unit: a single letter, or one of
    the eight two-character digraphs that count as one letter in Welsh orthography
    (ch/dd/ff/ng/ll/ph/rh/th). Used only to recognise a hyphenated run of typed
    single letters (see _hyphen_letter_run); it does not check any name table, so it
    also matches the plain vowels (a/e/i/o/u/w/y), which is what we want here."""
    return (len(part) == 1 and part.isalpha()) or part in _CY_DIGRAPH_NAMES


def _hyphen_letter_run(core: str) -> Optional[List[str]]:
    """Split `core` on '-' iff it is a keyboard-echoed run of single letters joined
    by hyphens ("d-d-d", "b-a-ch") -- every hyphen-separated part is exactly one
    letter/digraph unit, and there are at least two of them. Returns None otherwise,
    in particular for any real word or compound: a word-internal hyphen whose parts
    are actual syllables/words ("gogledd-ddwyrain") always has at least one part
    longer than a single letter/digraph, so it is never touched and the lexicon key
    stays intact. A run that qualifies is meant to be treated exactly like the
    comma-separated letters in "c, a, th" -- see _segment, which is the only caller."""
    if "-" not in core:
        return None
    parts = core.split("-")
    if len(parts) < 2 or any(not _is_solo_letter_unit(p) for p in parts):
        return None
    return parts

# English letter names, for ACRONYM runs: Welsh speech reads acronyms with English
# letter names (API, TTS, BBC -> ay-pee-eye, tee-tee-ess...) with rare exceptions
# like S4C — whose digit splits the letter run, so its letters keep their Welsh
# names automatically. Includes vowels (an acronym's "a" is "ay", never the Welsh
# article). Tokens are drawn from the shared inventory (they're the Welsh-accented
# English names already in the xx dictionary), so they render in both english modes.
_EN_LETTER_NAMES: Dict[str, List[str]] = {
    "a": [STRESS, "ei"],
    "b": [STRESS, "b", "ii"],
    "c": [STRESS, "s", "ii"],
    "d": [STRESS, "d", "ii"],
    "e": [STRESS, "ii"],
    "f": [STRESS, "e", "f"],
    "g": [STRESS, "jh", "ii"],
    "h": [STRESS, "ei", "ch"],
    "i": [STRESS, "ai"],
    "j": [STRESS, "jh", "ei"],
    "k": [STRESS, "k", "ei"],
    "l": [STRESS, "e", "l"],
    "m": [STRESS, "e", "m"],
    "n": [STRESS, "e", "n"],
    "o": [STRESS, "ou"],
    "p": [STRESS, "p", "ii"],
    "q": [STRESS, "k", "iu"],
    "r": [STRESS, "aa", "r"],
    "s": [STRESS, "e", "s"],
    "t": [STRESS, "t", "ii"],
    "u": [STRESS, "j", "uu"],
    "v": [STRESS, "v", "ii"],
    "w": [STRESS, "d", "@", SYLLABLE, "b", "@", "l", SYLLABLE, "j", "uu"],
    "x": [STRESS, "e", "k", "s"],
    "y": [STRESS, "w", "ai"],
    "z": [STRESS, "z", "e", "d"],
}

_IPA_TAIL = re.compile(r"\s*/[^/]*/\s*$")
_CMU_VARIANT = re.compile(r"\(\d+\)$")


class OOVError(KeyError):
    """Raised when a word is not in the lexicon (no P3 fallback yet)."""


_IPA_MAP_PATH = _HERE / "ipa_map.json"

# Tokens an author may supply: phones plus the stress/syllable marks. The control tokens
# are structural — phonemes_to_ids owns those. WORD_SEP is deliberately absent: both
# alphabet paths split on or skip whitespace, so it can never survive as a token.
_AUTHOR_FORBIDDEN = {"_", "^", "$"}


class PhoneError(ValueError):
    """Raised when author-supplied phones are not in the Bangor inventory."""


def _tokenize_phone_column(phones: List[str]) -> List[str]:
    """Turn a dict ASCII phone column (already whitespace-split) into our tokens.

    '-' -> syllable boundary; a leading "'" -> primary stress then the phone.
    (Recognition of the resulting tokens is validated by the caller.)
    """
    toks: List[str] = []
    for raw in phones:
        if raw == "-":
            toks.append(SYLLABLE)
            continue
        t = raw
        if t.startswith("'"):
            toks.append(STRESS)
            t = t[1:]
        if t:
            toks.append(t)
    return toks


def _parse_line(line: str):
    """-> (headword, [phone tokens as written]) or None for blank/garbage lines."""
    line = line.strip()
    if not line:
        return None
    line = _IPA_TAIL.sub("", line)  # drop trailing /ipa/
    parts = line.split()
    if len(parts) < 2:
        return None
    hw = _CMU_VARIANT.sub("", parts[0])  # word(1) -> word
    rest = parts[1:]
    if rest and rest[0].startswith("("):  # skip a (tag) group, e.g. (foreign,en,cmu)
        i = 0
        while i < len(rest) and not rest[i].endswith(")"):
            i += 1
        rest = rest[i + 1:]
    if not rest:
        return None
    return hw, rest


# Pronunciation overrides applied to the loaded Welsh table. CODE, deliberately, not an
# edit to the vendored dictionary: _compute_data_version hashes the dictionary FILES, so
# patching them would change data_version and models/piper/bangor.py in the API hard-fails
# until the HF model config's phonemizer block is bumped in the same move. An override here
# costs nothing and needs no model change. Same reasoning as _CY_LETTER_NAMES.
#
# WHY THESE TWO. The Bangor dictionary has "mil" as 'm i l /'mɪl/ -- a SHORT vowel -- where
# standard Welsh "mil" is /miːl/. The owner found this by ear on 2026-07-28, on a live
# service, having narrowed it themselves from "the cost file sounds like gibberish" to
# "234.56 works fine it's the mil that's the problem" to "anything above 999 is gibberish;
# everything below is almost perfect". That boundary is exactly the scale-word tier: below
# 1000 no cardinal uses a scale word, so nothing was wrong there.
#
# It is NOT a length problem, which is what I wrongly chased first: the owner's working
# "234.56" is seven words ("dau gant tri deg pedwar pwynt pump chwech"), MORE than the
# broken six-word "un mil dau gant tri deg pedwar". One phone was the whole defect.
#
# Confirmed by substituting the long vowel and re-rendering: the full 1234.56 became
# intelligible with that single change and nothing else touched.
#
# BLAST RADIUS, which is wider than cardinals -- every one of these was affected:
#   1000-999999          "un mil", "pum deg mil"
#   years 1000-1999      "mil naw wyth deg"          <- the whole year register
#   years 2000-2099      "dwy fil a dau ddeg tri"    <- via the mutated form
#
# The dictionary is internally CONSISTENT here ("cil" 'k i l, "hil" 'hh i l, "fil" 'v i l
# all short), so this is a systematic treatment of closed monosyllables rather than a typo,
# and the open-syllable entries are right: "ci" 'k ii, "tri" 't r ii. Deliberately NOT
# extended to cil/hil -- no number or year reaches them and they were not auditioned. The
# durable fix is upstream in the dictionary; the owner chose the override to ship today and
# raise that separately (docs/FOLLOWUPS.md).
#
# "miliwn"/"biliwn"/"miloedd" are NOT here and must not be: they are polysyllabic
# ('m i | l iu n), the syllable is open, and their short "i" is correct. Verified unchanged.
# Override keys that are NOT expected to exist in bangordict.dict. Being absent is the
# whole reason they need an entry, so the "word must exist" assertion is relaxed for these
# and only these -- a typo anywhere else still fails loudly.
_CY_PRON_ADDITIONS = frozenset({
    "onedrive", "chromebook", "firestick", "fitbit", "tiktok", "deliveroo",
    "readme", "changelog", "devops", "gitlab", "kubernetes", "techiaith",
})

# --- HETERONYMS ---------------------------------------------------------------------------
# One spelling, two pronunciations chosen by GRAMMAR rather than spelling. Neither lexicon can
# express this: each holds exactly one reading per word, so the shipped voice says a single form
# in every context and is wrong whenever the other reading is meant. Both routes are affected --
# an English-context word resolves from cmudict_native.dict, a Welsh-context one from the Bangor
# tables -- so this sits ABOVE both rather than patching either.
#
# Measured against MASC gold POS (592,472 tokens, CC BY 3.0 US; see docs/bilingual-pos-
# programme.md): the shipped readings were right on only 38.7% of 933 real instances, because
# 9 of 15 words shipped the MINORITY reading -- "live" right 3.6% of the time (ships /laɪv/ where
# 96% of uses are the verb /lɪv/), "wind" 3.6%, "record" 5.3%, "read" 20.2%. Pointing each
# fallback at the majority reading lifts that to 74.1% with no tagger, no retrain and no new
# data; the POS branches earn the rest once the tagger lands. One table, filled in two stages.
#
# KEYED ON THE TAGGER'S OWN TAGSET, which is UD coarse with ONE split: VERB vs VPAST. "read"
# is why the split exists -- /rɛd/ (VBD, VBN) and /riːd/ (everything else) are both `VERB` in
# plain UD, so a purely coarse tag could not separate them at all. Everything else the
# heteronyms need is a coarse distinction, so the tagset stays at 17 tags rather than Penn's
# 45; that halves the exported model. See scripts/gen_pos_data.PENN_RED for the mapping from
# MASC's Penn tags. Flat (word, tag) -> phones, which is also the shape the C mirror needs.
#
# Phones are the other reading of a pair the lexicon already ships, built by swapping only the
# distinguishing segment: voice a final fricative, shift stress, reduce or unreduce a vowel.
# Nothing is invented.
#
# Phones are in the lexicon's own (General American-labelled) system: that is what the model was
# trained with, and what the deployed API speaks. A different accent is a retrain, not a table.
_VERB_FORMS = ("VERB",)              # base/finite/gerund
_VERB_ALL = ("VERB", "VPAST")        # ...plus past tense and past participle
_NOUN_FORMS = ("NOUN",)


def _het(**readings: object) -> Dict[Optional[str], List[str]]:
    """Expand {reading: (tags, phones)} into a flat {tag: phones} map plus a None fallback.
    The fallback is the reading named `default`, i.e. the majority reading in MASC."""
    out: Dict[Optional[str], List[str]] = {}
    default = readings.pop("default")
    for tags, phones in readings.values():          # type: ignore[misc]
        for t in tags:
            out[t] = list(phones)
    out[None] = list(readings[default][1])          # type: ignore[index]
    return out


_HETERONYM: Dict[str, Dict[Optional[str], List[str]]] = {
    # "read": the case that forces fine tags -- VBD/VBN /rɛd/ vs VB/VBP/VBZ/VBG /riːd/, both VERB.
    "read": _het(default="pres",
                 pres=(_VERB_FORMS, ["ɹ", STRESS, "ii", "d"]),
                 past=(("VPAST",), ["ɹ", STRESS, "e", "d"])),              # pres 130 / past 33
    "use": _het(default="verb",
                verb=(_VERB_ALL, ["j", STRESS, "uu", "z"]),
                noun=(_NOUN_FORMS, ["j", STRESS, "uu", "s"])),             # verb 167 / noun 130
    # A capitalised label-initial "Live" is tagged PROPN ("Live Recognition", "Live Text", "Live
    # Photos", "Live Captions" -- the owner heard /lɪv/ Recognition on VoiceOver, 2026-09-08), and
    # a proper-noun or adverbial "live" ("go live") is always the adjective sense: /laɪv/.
    "live": _het(default="verb",
                 verb=(_VERB_FORMS, ["l", STRESS, "i", "v"]),
                 adj=(("ADJ", "ADV", "PROPN"), ["l", STRESS, "ai", "v"])),  # verb 106 / adj 4
    "close": _het(default="verb",
                  verb=(_VERB_ALL, ["k", "l", STRESS, "ou", "z"]),
                  adj=(("ADJ", "ADV"), ["k", "l", STRESS, "ou", "s"])),      # verb 37 / adj 36
    "record": _het(default="noun",
                   noun=(_NOUN_FORMS, [STRESS, "ɹ", "e", "k", "@r", "d"]),
                   verb=(_VERB_ALL, ["ɹ", "@", "k", STRESS, "oo", "ɹ", "d"])),  # noun 54 / verb 3
    "object": _het(default="verb",
                   verb=(_VERB_ALL, ["@", "b", "jh", STRESS, "e", "k", "t"]),
                   noun=(_NOUN_FORMS, [STRESS, "aa", "b", "jh", "e", "k", "t"])),  # verb 37 / noun 7
    "separate": _het(default="adj",
                     adj=(("ADJ",), ["s", STRESS, "e", "p", "@r", "@", "t"]),
                     verb=(_VERB_ALL, ["s", STRESS, "e", "p", "@r", "ei", "t"])),  # adj 26 / verb 6
    "wind": _het(default="noun",
                 noun=(_NOUN_FORMS, ["w", STRESS, "i", "n", "d"]),
                 verb=(_VERB_FORMS, ["w", STRESS, "ai", "n", "d"])),       # noun 27 / verb 1
    "estimate": _het(default="verb",
                     verb=(_VERB_ALL, [STRESS, "e", "s", "t", "@", "m", "ei", "t"]),
                     noun=(_NOUN_FORMS, [STRESS, "e", "s", "t", "@", "m", "@", "t"])),  # verb 10 / noun 5
    # Already shipping the majority reading: fallback unchanged, POS branches added so the tagger
    # has something to select once it lands. No behaviour change today.
    "present": _het(default="noun",
                    noun=(_NOUN_FORMS + ("ADJ",), ["p", "ɹ", STRESS, "e", "z", "@", "n", "t"]),
                    verb=(_VERB_ALL, ["p", "ɹ", "@", "z", STRESS, "e", "n", "t"])),  # noun 66 / verb 16
    "desert": _het(default="noun",
                   noun=(_NOUN_FORMS, ["d", STRESS, "e", "z", "@r", "t"]),
                   verb=(_VERB_ALL, ["d", "@", "z", STRESS, "@r", "t"])),   # noun 20 / verb 0
    "refuse": _het(default="verb",
                   verb=(_VERB_ALL, ["ɹ", "@", "f", "j", STRESS, "uu", "z"]),
                   noun=(_NOUN_FORMS, [STRESS, "ɹ", "e", "f", "j", "uu", "s"])),  # verb 11 / noun 1
}

# Heteronyms POS CANNOT separate, recorded so nobody adds them above expecting a fix: both
# readings carry the SAME tag, so telling them apart needs word sense, not grammar.
#   lead (metal / to guide)   bow (ribbon / to bend)   tear (droplet / to rip)
#   sow  (to plant / a pig)   row (a line / a quarrel) bass (fish / low register)
# Out of scope for this mechanism and deliberately left alone.
_GO_FORMS = frozenset({"go", "goes", "went", "going", "gone"})   # "go live": see phonemize

_HETERONYM_NOT_POS_SEPARABLE = frozenset({
    "lead", "bow", "tear", "sow", "row", "bass", "wound",
})

_CY_PRON_OVERRIDE: Dict[str, List[str]] = {
    "mil": [STRESS, "m", "ii", "l"],   # was [STRESS, "m", "i", "l"]
    "fil": [STRESS, "v", "ii", "l"],   # soft-mutated, as in "dwy fil"

    # --- BRAND NAMES -----------------------------------------------------------------
    # bangordict.dict records these with Welsh phonology ("google" as g o-o g-l e), which
    # is a defensible editorial choice for Welsh conversation and wrong for a screen reader
    # reading an English interface. It only shows up on SHORT utterances: the sentence
    # router needs about five English words before it routes English, and a button label is
    # one to three, so "google" alone is Welsh while "Open the Google application now" is
    # already correct today. Screen readers emit almost entirely short labels.
    #
    # NB the syllable boundary "|" in those dictionary readings is NOT the defect -- ordinary
    # Welsh is full of it and sounds right. The defect is the PHONES: Welsh o/o/e where
    # English needs uu/@. Owner-confirmed by ear, 2026-09-04.
    #
    # Phones below are the existing cmudict_native entries verbatim -- nothing invented.
    "youtube":    ["j", STRESS, "uu", "t", "j", "uu", "b"],
    "google":     ["g", STRESS, "uu", "g", "@", "l"],
    "twitter":    ["t", "w", STRESS, "i", "t", "@r"],
    "adobe":      ["@", "d", STRESS, "ou", "b", "ii"],
    "photoshop":  ["f", STRESS, "ou", "t", "ou", "sh", "aa", "p"],
    "powerpoint": ["p", STRESS, "au", "@r", "p", "oi", "n", "t"],
    "ebay":       [STRESS, "ii", "b", "ei"],
    "iphone":     [STRESS, "ai", "f", "ou", "n"],
    "ipad":       [STRESS, "ai", "p", "æ", "d"],
    "android":    [STRESS, "æ", "n", "d", "ɹ", "oi", "d"],

    # Concatenated brands in NO dictionary, so they fell to Welsh letter-to-sound. Rendered
    # as TWO WORDS (WORD_SEP, id 3) rather than one, because the owner tested the spaced
    # forms by ear and preferred them -- these token lists are byte-identical to typing
    # "one drive", "chrome book" and so on. WORD_SEP, not the syllable boundary: "|" is what
    # makes bangordict's readings sound wrong, and is deliberately not used here.
    "onedrive":   ["w", STRESS, "ʌ", "n", WORD_SEP, "d", "ɹ", STRESS, "ai", "v"],
    "chromebook": ["k", "ɹ", STRESS, "ou", "m", WORD_SEP, "b", STRESS, "u", "k"],
    "firestick":  ["f", STRESS, "ai", "@r", WORD_SEP, "s", "t", STRESS, "i", "k"],
    "fitbit":     [STRESS, "f", "i", "t", WORD_SEP, "b", STRESS, "i", "t"],
    "tiktok":     ["t", STRESS, "i", "k", WORD_SEP, "t", STRESS, "aa", "k"],
    # "deliver" + "ww". Owner-chosen after testing: "deliver oo" gives Welsh ˈoo|o and
    # "deliver uu" gives ˈyy|y, both worse. It does carry a /w/ onset, so this is
    # "deliver-WOO" rather than "deliver-OO" -- accepted as the best this phoneset offers.
    "deliveroo":  ["d", "i", "l", STRESS, "i", "v", "@r", WORD_SEP, STRESS, "w", "uu"],
    # Developer / interface vocabulary in NO dictionary (2026-09-07; the owner heard a
    # GitLab project page). Same two-word convention as the brands above; "kubernetes" is
    # one word. Everything else on that page (login, wiki, wifi, whatsapp, gmail, github,
    # spotify, netflix...) is already in cmudict_native and needed only the acronym gate to
    # consult it.
    "readme":     ["ɹ", STRESS, "ii", "d", WORD_SEP, "m", STRESS, "ii"],
    "changelog":  ["ch", STRESS, "ei", "n", "jh", WORD_SEP, "l", STRESS, "oo", "g"],
    "devops":     ["d", STRESS, "e", "v", WORD_SEP, STRESS, "aa", "p", "s"],
    "gitlab":     ["g", STRESS, "i", "t", WORD_SEP, "l", STRESS, "æ", "b"],
    "kubernetes": ["k", "uu", "b", "@r", "n", STRESS, "e", "t", "ii", "z"],
    # The organisation's own name (owner heard "tetch-ee-ayth" when an English sentence
    # preceded it in one utterance, 2026-09-08). In no dictionary; the Welsh LTS reading,
    # pinned so it does not depend on which language the utterance around it routes to.
    "techiaith":  [STRESS, "t", "e", "x", "|", "j", "ai", "th"],

    # DELIBERATELY ABSENT: camera, signal, telegram. Mispronounced by the same mechanism,
    # but each is an ordinary Welsh loanword as well as a brand, and an override applies
    # everywhere -- fixing the English label would break Welsh prose. Owner confirmed these
    # "all work fine" as they are. Fixable only with context, which is separate work.
}


class BangorLexicon:
    def __init__(self, id_map: Dict[str, List[int]], data_dir: Path = _DEFAULT_DATA):
        self.data_dir = Path(data_dir)
        self.tables: List[Dict[str, List[str]]] = []
        self.stats = {"entries": 0, "skipped_unknown_phone": 0, "duplicates": 0}
        valid = set(id_map)
        for name in _DICT_ORDER:
            table: Dict[str, List[str]] = {}
            path = self.data_dir / name
            for raw in path.read_text(encoding="utf-8").splitlines():
                parsed = _parse_line(raw)
                if parsed is None:
                    continue
                hw, phones = parsed
                toks = _tokenize_phone_column(phones)
                if any(t not in valid for t in toks):
                    self.stats["skipped_unknown_phone"] += 1
                    continue
                key = hw.lower()
                if key in table:  # keep first pronunciation (deterministic)
                    self.stats["duplicates"] += 1
                    continue
                table[key] = toks
                self.stats["entries"] += 1
            self.tables.append(table)
        # Applied to the Welsh table only (bangordict.dict, index 0), which both lookup()
        # and lookup_welsh() consult first, so one patch covers every path. Asserted rather
        # than assigned blindly: an override for a word the dictionary does not have, or one
        # whose phones are not in the id map, is a silent no-op that would look like a fix.
        welsh = self.tables[0]
        for word, phones in _CY_PRON_OVERRIDE.items():
            # A word the dictionary lacks is normally a typo, but the concatenated brand
            # names (onedrive, tiktok…) are absent BY DEFINITION -- being absent is exactly
            # why they fell to Welsh letter-to-sound. Those are additions, not corrections,
            # so they are listed explicitly and everything else still has to exist.
            assert word in welsh or word in _CY_PRON_ADDITIONS, (
                f"override for {word!r}, which is not in bangordict.dict; if that is "
                f"intentional, add it to _CY_PRON_ADDITIONS")
            assert all(p in valid for p in phones), f"override for {word!r} has unknown phones"
            welsh[word] = list(phones)
            self.stats["overridden"] = self.stats.get("overridden", 0) + 1

    def lookup(self, word: str) -> Optional[List[str]]:
        for table in self.tables:
            hit = table.get(word)
            if hit is not None:
                return hit
        return None

    def lookup_welsh(self, word: str) -> Optional[List[str]]:
        """Welsh-only lookup: native Welsh words + proper nouns (not English tables)."""
        for table in self.tables[:2]:  # bangordict.dict, bangordict.xx.dict
            hit = table.get(word)
            if hit is not None:
                return hit
        return None


class BangorG2P:
    def __init__(self, id_map_path: Path = _DEFAULT_IDMAP, data_dir: Path = _DEFAULT_DATA,
                 english_mode: str = "accented"):
        # english_mode: "accented" (current Welsh-only model — English via the Bangor
        # Welsh-accented tables / folded) | "native" (native-English-trained model —
        # English via the CMUdict native lexicon, emitting English phones 78-84).
        self.id_map_path = Path(id_map_path)
        raw = self.id_map_path.read_text(encoding="utf-8")
        spec = json.loads(raw)
        self.id_map: Dict[str, List[int]] = spec["phoneme_id_map"]
        self.control = spec["control"]
        self.lexicon = BangorLexicon(self.id_map, data_dir)
        self.lang_prior = _load_lang_prior(_LANG_PRIOR)
        self.normalizer = WelshNormalizer()
        self.english_mode = english_mode
        self._english: Optional[EnglishG2P] = None
        self._pos: Dict[str, object] = {}
        self._ipa: Optional[Dict[str, str]] = None
        self._data_version = self._compute_data_version(raw)

    def _pos_tagger(self, lang: str):
        """The POS model for `lang`, or None if it is not installed.

        None is a supported state: a distro without the models still phonemizes, taking
        each heteronym's majority-reading fallback (74.1% correct, vs 38.7% before those
        fallbacks were fixed). Cached per instance because loading walks a ~2 MB blob."""
        if lang not in self._pos:
            self._pos[lang] = pos_tagger.load(lang, _POS_DATA)
        return self._pos[lang]

    @property
    def english(self) -> EnglishG2P:
        if self._english is None:
            self._english = EnglishG2P()
        return self._english

    @property
    def ipa_to_token(self) -> Dict[str, str]:
        if self._ipa is None:
            raw = json.loads(_IPA_MAP_PATH.read_text(encoding="utf-8"))
            self._ipa = raw["ipa_to_token"]
        return self._ipa

    def tokens_from_phones(self, phones: str, alphabet: str = "bangor") -> List[str]:
        """Author-supplied pronunciation -> validated tokens (SSML <phoneme ph="...">).

        "bangor": whitespace-separated ASCII tokens, exact and authoritative.
        "ipa":    an IPA string, segmented longest-match-first (every key is 1-2 chars).
        Anything outside the inventory raises, so a typo is a 400 rather than silent
        mangling — which is what the eSpeak "[[ ... ]]" escape used to produce here.
        """
        if alphabet == "bangor":
            out = phones.split()
        elif alphabet == "ipa":
            out, i, table = [], 0, self.ipa_to_token
            while i < len(phones):
                if phones[i].isspace():
                    i += 1
                    continue
                if phones[i] in (STRESS, "ˌ", SYLLABLE):
                    out.append(phones[i])
                    i += 1
                    continue
                two = phones[i:i + 2]
                if len(two) == 2 and two in table:
                    out.append(table[two])
                    i += 2
                    continue
                one = phones[i]
                if one in table:
                    out.append(table[one])
                    i += 1
                    continue
                raise PhoneError(
                    f"IPA symbol {one!r} has no Bangor equivalent; see phoneset.md")
        else:
            raise PhoneError(
                f"alphabet {alphabet!r} is not supported; use 'bangor' or 'ipa'")

        for t in out:
            if t in _AUTHOR_FORBIDDEN:
                raise PhoneError(f"token {t!r} is structural and cannot be supplied")
            if t not in self.id_map:
                raise PhoneError(
                    f"token {t!r} is not in the Bangor inventory; see phoneset.md")
        return out

    def letter_tokens(self, word: str) -> List[str]:
        """Spell a word out letter by letter, Welsh-alphabet style (SSML say-as characters).

        Longest-match so the eight digraphs count as single letters ("llan" -> ll, a, n).
        Digits become number words. Every letter gets a NAME: consonants and digraphs from
        _CY_LETTER_NAMES/_CY_DIGRAPH_NAMES, vowels from _CY_VOWEL_SPELLED. Only an
        accented vowel, which has no name entry, still falls back to its lexicon form.

        Spelled letters are separated by a semicolon pause token (";", not WORD_SEP and no
        longer a comma): the owner asked for spell-out slower than the original
        WORD_SEP-only pace ("commas will do"), then found the comma still too short to
        keep adjacent letter names apart and preferred the semicolon.

        Vowels use _CY_VOWEL_SPELLED, NOT _CY_VOWEL_SOLO -- the two hold different lengths
        for deliberately different contexts, see their definitions. An earlier rule sent
        spelled vowels to the lexicon instead, on the grounds that a vowel's letter name
        is the function word; it was reversed by ear across 31 words after it turned out to
        read "llaw" as "ell, a, double-you".

        The character test is `decimal_value(ch) >= 0 or ch.isalpha()`, NOT `isalnum()`,
        and the digit test is `decimal_value(ch) >= 0`, NOT `isdigit()`. The semantic
        contract is still "isdecimal(), not isdigit()": isalnum/isdigit are true for
        characters int() then rejects -- '²' (superscript two) and '①' (circled one) are
        isdigit but have no integer value -- so the old spelling raised ValueError out of
        int() on input reachable from SSML <say-as interpret-as="characters">, i.e. a 500
        from the API. Characters that are neither decimal digits nor letters are now
        skipped, which is also what the C port does with them. Genuine non-ASCII decimals
        are unaffected: '٣' (Arabic-Indic three) is isdecimal, int() reads it as 3,
        and it still spells out as "tri" in both implementations.

        `decimal_value()` (canonical.py), not the bare `str.isdecimal()` it replaced, is
        what actually runs the test: it is the same Unicode-13 digit table vendored for
        the general leading-zero fix, so this method classifies a digit identically on
        every host interpreter instead of following whichever Unicode version happens to
        be installed. See canonical.py's module docstring for why the digit class is
        vendored and the letter class (`ch.isalpha()`, just above) deliberately is not.
        """
        text = word.strip().lower()
        pieces: List[List[str]] = []
        i = 0
        while i < len(text):
            ch = text[i]
            if not (decimal_value(ch) >= 0 or ch.isalpha()):
                i += 1
                continue
            two = text[i:i + 2]
            if two in _CY_DIGRAPH_NAMES:
                pieces.append(list(_CY_DIGRAPH_NAMES[two]))
                i += 2
                continue
            if decimal_value(ch) >= 0:
                j = i
                while j < len(text) and decimal_value(text[j]) >= 0:
                    j += 1
                spoken = self.normalizer.num_to_welsh_public(int(text[i:j]))
                pieces.append(self.phonemize(spoken, on_oov="lts"))
                i = j
                continue
            if ch in _CY_LETTER_NAMES:
                pieces.append(list(_CY_LETTER_NAMES[ch]))
            elif ch in _CY_VOWEL_SPELLED:
                # A spelled vowel gets its LETTER NAME, same as a consonant does.
                #
                # This replaces a "plain vowels in spell-out" rule that routed vowels to
                # _word_tokens instead. That rule never delivered plain vowels: a/e/i/o/y
                # are real Welsh function words, so the lexicon returned the short
                # unstressed WORD, and w -- which is not a function word -- fell through
                # to English and came back as a three-syllable "double-you" in the middle
                # of a Welsh spelling ("llaw" -> "ell, a, double-you"). The rule had been
                # auditioned only on "bach", whose one vowel is the single vowel where
                # plain and long are near-indistinguishable, so nothing caught it.
                # Confirmed by ear across 31 words on 2026-07-27.
                pieces.append(list(_CY_VOWEL_SPELLED[ch]))
            else:
                # Accented vowels and anything else: no letter-name entry exists, so take
                # the lexicon/LTS reading. solo_vowel=False because a bare top-level
                # phonemize(ch) would re-derive solo_vowel from the single character and
                # be unable to tell a spelled letter from an isolated keystroke.
                pieces.append(self._word_tokens(ch, "lts", "cy", solo_vowel=False) or [])
            i += 1
        out: List[str] = []
        for k, piece in enumerate(pieces):
            if k:
                # Semicolon, not comma: the comma pause was too short to keep adjacent
                # letter names apart ("cê î" ran together as one "k...i"). Chosen by ear
                # over comma across the same 31 words.
                out.append(";")
            out.extend(piece)
        return out

    def normalize(self, text: str, lang: Optional[str] = None) -> str:
        """Normalise text, verbalising numbers in the utterance's language.

        `lang` is an explicit override ("cy"/"en": SSML <lang>, a client's requested voice
        language) and applies to the whole text. When None, the NUMBER language is detected
        per sentence -- and per clause inside a sentence that carries evidence for both
        languages -- from the letters of the raw text (see _number_spans), so
        "Home screen 1 of 3" says "one of three", "1 o 1. 1 of 1" says "un o un. one of one"
        and "Tudalen 1 o 3, Page 1 of 3" keeps each half in its own language. When every span
        agrees, the text is normalised in one pass exactly as before, so a single-language
        utterance is byte-identical to what it was. Detection here is a *number* decision
        only; phoneme routing in phonemize keeps its own, stricter rule, so the deployed
        voice's sound on shared words does not move."""
        return self._normalize_carry(text, lang)[0]

    def _normalize_carry(self, text: str, lang: Optional[str], default: str = "cy") -> Tuple[str, str]:
        """(normalised text, the number language in force at its end). `default` is the language
        a span with no evidence takes -- the previous segment's, when segments() calls this."""
        if lang:
            return self.normalizer.normalize(text, lang=lang), lang
        spans = self._number_spans(text, default=default)
        langs = {sp[3] for sp in spans}
        last = spans[-1][3] if spans else default
        if len(langs) <= 1:
            return self.normalizer.normalize(text, lang=next(iter(langs), default)), last
        out = []
        for start, end, dend, l in spans:
            out.append(self.normalizer.normalize(text[start:end], lang=l))
            out.append(text[end:dend])                  # the delimiter, verbatim ...
        # ... which the pause passes have not seen (a clause dash or bullet), so they run once
        # more here; both are idempotent on the already-normalised chunks.
        return re.sub(r"\s+", " ", _pause_punct(_pause_punct_early("".join(out)))).strip(), last

    def _number_weights(self, text: str) -> List[int]:
        """The prior's weight for each word of the RAW text (apostrophe-joined alphabetic runs,
        lowercased -- digits are not yet words here)."""
        return [self._word_weight(w) for w in _ALPHA_RUN.findall(text.lower())]

    def _number_lang(self, text: str) -> str:
        """Language for digit verbalisation over one span: one English-only word and no
        Welsh-only word is enough ("Page 3", "Tab 1 of 4"), because the cost of the two
        errors is asymmetric -- an English "three" inside Welsh is intelligible, a Welsh "tri"
        inside an English interface is not. No evidence: Welsh, the voice's own language."""
        return "en" if sum(self._number_weights(text)) <= -_PRIOR_MIN else "cy"

    @staticmethod
    def _split_sentences(text: str) -> List[Tuple[int, int, int, str]]:
        """[(start, end, delimiter_end, boundary)] over the raw text.

        A sentence ends at a run of . ! ? … followed by ASCII whitespace or the end, when what
        follows the whitespace is an upper-case letter, a digit, a quote or the end -- so
        "learn more... link" stays one sentence -- and not after a single-letter word ("e.e.",
        "y.b.", "a.m.", "U.S.A.") or a title (Dr., Mr.). A newline is a "line" boundary, a blank
        line a "paragraph"; a run of punctuation followed by a newline takes the newline's kind.
        Procedural, code point by code point, so cy_phonemize.c (nl_sentences) walks the same
        bytes to the same answer."""
        spans = []
        n = len(text)
        i = start = 0
        cls_prev = cls_prev2 = 0                 # 1 letter, 2 other alnum, 0 anything else

        def kind_of(a: int, c: int) -> str:
            nl = text.count("\n", a, c)
            return "paragraph" if nl >= 2 else "line" if nl == 1 else "sentence"

        while i < n:
            ch = text[i]
            if ch in _SENT_END:
                j = i
                while j < n and text[j] in _SENT_END:
                    j += 1
                single = cls_prev == 1 and cls_prev2 != 2 and cls_prev2 != 1
                k = i
                while k > start and text[k - 1].isalpha():
                    k -= 1
                title = text[k:i].lower() in _NL_TITLES and (k == start or not text[k - 1].isalnum())
                m = j
                while m < n and text[m] in _NL_WS:
                    m += 1
                nxt = text[m] if m < n else ""
                follows = (m == n or nxt.isdigit() or nxt in _QUOTES
                           or (nxt.isalpha() and nxt.lower() != nxt))
                if (j == n or text[j] in _NL_WS) and follows and not single and not title:
                    spans.append((start, i, m, kind_of(j, m)))
                    start = i = m
                    cls_prev = cls_prev2 = 0
                    if len(spans) == _NL_MAX_SPANS:
                        break
                    continue
                cls_prev2, cls_prev = cls_prev, 0
                i = j
                continue
            if ch == "\n":
                j = i
                while j < n and text[j] in _NL_WS:
                    j += 1
                line = text[start:i].rstrip(_NL_WS)
                if (kind_of(i, j) == "line" and len(line) >= _SOFT_WRAP_MIN_CHARS
                        and line and line[-1] not in _LINE_TERMINAL
                        and j < n and text[j].isalpha()):    # a wrap continues with a word, never
                    i = j                                    # "message\n15:44": a soft wrap is whitespace
                    cls_prev = cls_prev2 = 0
                    continue
                spans.append((start, i, j, kind_of(i, j)))
                start = i = j
                cls_prev = cls_prev2 = 0
                if len(spans) == _NL_MAX_SPANS:
                    break
                continue
            cls_prev2, cls_prev = cls_prev, (1 if ch.isalpha() else 2 if ch.isalnum() else 0)
            i += 1
        if start < n or not spans:
            spans.append((start, n, n, "end"))
        return spans

    @staticmethod
    def _split_clauses(text: str, start: int, end: int) -> List[Tuple[int, int, int]]:
        """Clause ends inside text[start:end]: , ; : followed by ASCII whitespace or the end,
        or a dash or bullet between spaces."""
        spans = []
        i = cstart = start
        while i < end:
            ch = text[i]
            if ch in ",;:" and (i + 1 == end or text[i + 1] in _NL_WS):
                j = i + 1
                while j < end and text[j] in _NL_WS:
                    j += 1
                spans.append((cstart, i, j))
                cstart = i = j
                continue
            if ch in "-\u2013\u2014•‣◦▪▫●■□" and i > cstart and text[i - 1] == " " and i + 1 < end and text[i + 1] == " ":
                j = i + 1
                while j < end and text[j] in _NL_WS:
                    j += 1
                spans.append((cstart, i - 1, j))
                cstart = i = j
                continue
            i += 1
        if cstart < end or not spans:
            spans.append((cstart, end, end))
        return spans

    def _number_spans(self, text: str, default: str = "cy") -> List[Tuple[int, int, int, str]]:
        """[(start, end, delimiter_end, lang)]: the number language of each sentence, or of
        each clause where a sentence carries evidence for BOTH languages ("Tudalen 1 o 3,
        Page 1 of 3"). A span with no evidence takes the language of the span before it
        (reading order); the first defaults to Welsh. Owner, 2026-09-07: "the language
        detection is not respecting sentence boundaries" -- it ran once over the utterance."""
        out = []
        lang = default
        for s_start, s_end, s_dend, _kind in self._split_sentences(text):
            ws = self._number_weights(text[s_start:s_end])
            # strong evidence for BOTH languages in one sentence: bilingual-signage style
            if any(w >= _PRIOR_STRONG for w in ws) and any(w <= -_PRIOR_STRONG for w in ws):
                clauses = self._split_clauses(text, s_start, s_end)
                for k, (c_start, c_end, c_dend) in enumerate(clauses):
                    s = sum(self._number_weights(text[c_start:c_end]))
                    if abs(s) >= _PRIOR_MIN:
                        lang = "en" if s < 0 else "cy"
                    out.append((c_start, c_end, s_dend if k == len(clauses) - 1 else c_dend, lang))
            else:
                s = sum(ws)
                if abs(s) >= _PRIOR_MIN:
                    lang = "en" if s < 0 else "cy"
                out.append((s_start, s_end, s_dend, lang))
        return out

    # --- normalization (minimal for P1; P2 adds the full verbaliser) ---
    def _segment(self, text: str):
        """Yield (leading_punct, core_word, trailing_punct) per whitespace token, in
        source order. Punctuation in _PUNCT is peeled off each token's edges AND out of
        its interior (emitted as standalone pause tokens by phonemize); word-internal '
        and - stay in the core so lexicon keys still match -- EXCEPT a hyphenated run of
        single letters ("d-d-d", "b-a-ch"), which is keyboard echo, not a compound: those
        hyphens are separators, spoken like the commas in "c, a, th" (see
        _hyphen_letter_run). A real compound's parts are never single letters
        ("gogledd-ddwyrain" is unaffected and still found as one lexicon key).

        The interior peel closes FOLLOWUPS section G's word-internal punctuation class:
        "ie!na" fused into one LTS nonword with the "!" silently dropped. Attachment side
        is the load-bearing detail. Within an interior run, marks BEFORE the first "("
        trail the left sub-word and marks FROM the first "(" lead the right one, which
        makes the invariant exact: for every member m, phonemize("a" + m + "b") equals
        phonemize("a" + m + " b") token for token -- the fused form becomes exactly the
        shape the model trained on ("ty(bach)" tokenises as "ty (bach)" does, "a!(b" as
        "a! (b"). Every emitted id is already trained (pause ids 7-19), so this is a
        re-tokenisation, not an emission-policy change -- see the note above _PUNCT."""
        for raw in text.strip().lower().split():
            i, j = 0, len(raw)
            while i < j and raw[i] in _PUNCT:
                i += 1
            while j > i and raw[j - 1] in _PUNCT:
                j -= 1
            lead, core, trail = list(raw[:i]), raw[i:j], list(raw[j:])
            # Interior split. The core's own edges are punct-free (just peeled), and the
            # runs are maximal, so the sub-cores are all non-empty and the pieces list
            # alternates word, run, word, ..., word.
            pieces = _INTERIOR_PUNCT.split(core) if core else [core]
            cores = pieces[0::2]
            leads: list = [lead] + [[] for _ in cores[1:]]
            trails: list = [[] for _ in cores[1:]] + [trail]
            for k, run in enumerate(pieces[1::2]):
                cut = run.find("(")
                if cut == -1:
                    cut = len(run)
                trails[k] = list(run[:cut])
                leads[k + 1] = list(run[cut:])
            for ld, c, tr in zip(leads, cores, trails):
                letters = _hyphen_letter_run(c)
                if letters is not None:
                    last = len(letters) - 1
                    for k, letter in enumerate(letters):
                        yield (ld if k == 0 else []), letter, ([","] if k < last else tr)
                    continue
                yield ld, c, tr

    def _known(self, word: str) -> bool:
        """True if ANY table can pronounce `word` — Welsh, Welsh-accented, or English."""
        return (self.lexicon.lookup(word) is not None
                or self.english.lookup(word) is not None)

    def _hyphen_parts(self, core: str) -> Optional[List[str]]:
        """Parts of a hyphenated core that NO dictionary knows, or None to leave it alone.

        Screen readers are full of hyphenated English compounds -- double-tap, drop-down,
        read-only, sign-in, scroll-bar, check-box, log-out -- and none of them is in any
        table. As one token they fall to Welsh letter-to-sound ("double-tap" ->
        d ou b|'l e|t a p) AND they starve _sentence_lang of English evidence, so
        neighbouring words that are also real Welsh words stay Welsh ("to" -> Welsh 'to',
        a roof). Splitting fixes both at once, which is why typing a space instead of a
        hyphen has always sounded right.

        THE GUARD, and why hyphenated compounds were deliberately left intact before this:
        a hyphenated form that IS in a table keeps winning, untouched. That protects all 511
        hyphenated Welsh entries (gogledd-ddwyrain, pen-blwydd, e-bost, ar-lein) plus the
        hyphenated English ones (wi-fi, built-in, e-mail) -- verified: splitting wi-fi would
        give 'w i v i', so this ordering is load-bearing, not a formality.

        Both parts must be independently pronounceable, or splitting buys nothing and we
        keep today's behaviour. Single characters are excluded so a keyboard-echoed letter
        run ("d-d-d") stays with _hyphen_letter_run, which _segment already handled.
        """
        if not core or "-" not in core:
            return None
        if self._known(core):          # a real hyphenated entry -- never split
            return None
        parts = [p for p in core.split("-") if p]
        if len(parts) < 2 or any(len(p) < 2 for p in parts):
            return None
        if not all(self._known(p) for p in parts):
            return None
        return parts

    def _split_unknown_hyphen_compounds(self, segments):
        """Expand unknown hyphenated cores into their parts BEFORE language routing.

        Done here rather than in _word_tokens on purpose: _sentence_lang runs on this word
        list, so splitting later would fix the compound's own pronunciation but leave the
        router still deciding from one unknown token.
        """
        out = []
        for lead, core, trail in segments:
            parts = self._hyphen_parts(core)
            if parts is None:
                out.append((lead, core, trail))
                continue
            last = len(parts) - 1
            for i, part in enumerate(parts):
                out.append((lead if i == 0 else "", part, trail if i == last else ""))
        return out

    def phonemize(self, text: str, on_oov: str = "raise",
                  lang: Optional[str] = None) -> List[str]:
        if lang not in (None, "cy", "en"):
            raise ValueError(f"lang {lang!r} is not supported; use 'cy' or 'en'")
        if lang is None:
            # Route per sentence. When every sentence agrees the whole text goes through in
            # one pass with that language, so single-sentence and single-language text is
            # byte-identical to a plain call; only a genuinely mixed utterance is phonemized
            # sentence by sentence (WORD_SEP between the pieces, as between any two words).
            spans = self._split_sentences(text)
            if len(spans) > 1:
                langs = self._route_sentences(text, spans)
                if len(set(langs)) > 1:
                    tokens = []
                    for (start, end, dend, _kind), l in zip(spans, langs):
                        chunk = text[start:dend].rstrip(_NL_WS)
                        piece = self.phonemize(chunk, on_oov, lang=l) if chunk else []
                        if piece and tokens:
                            tokens.append(WORD_SEP)
                        tokens.extend(piece)
                    return tokens
                lang = langs[0]
        segments = list(self._segment(text))
        segments = self._split_unknown_hyphen_compounds(segments)
        words = [core for _lead, core, _trail in segments if core]  # == the removed _words(text)
        # lang=None keeps the automatic sentence-level routing; an explicit value is an
        # author override (SSML <lang xml:lang="...">) and wins outright.
        # NATIVE MODE ONLY: _word_tokens' english_mode="accented" branch never reads
        # lang, so under the default accented mode the override is inert — accepted,
        # validated, and then ignored, because that mode has one set of tables and no
        # per-word language choice to make.
        # Routing counts WORDS: a core with no letter or digit (a dash between spaces, a lone
        # "/") is punctuation and must not dilute the one-third ratio. C never makes a token
        # for such a core, so this filter is what keeps the two sides on the same count
        # (found 2026-09-07 on "Croeso - Welcome, 1 o 3 – 1 of 3": two dashes flipped Python
        # to Welsh while C said English).
        lang = lang or self._sentence_lang(self._routing_words_of(segments))
        # a single isolated vowel keystroke (the whole utterance is one vowel letter)
        solo_vowel = len(words) == 1 and words[0] in _CY_VOWEL_SOLO

        # POS TAGGING, deliberately gated. The tagger is consulted ONLY when the
        # utterance actually contains a heteronym, which is the only thing that reads a
        # tag today. Two reasons, and the second is the important one:
        #   * cost -- most utterances contain no heteronym, and this skips ~19 blob
        #     lookups per word for them;
        #   * blast radius -- every utterance without a heteronym is provably unchanged
        #     by this feature, in Python and in C, so the parity surface is exactly the
        #     inputs the tagger can affect rather than all of them.
        # A missing model, or a tag with no branch, falls through to the majority
        # reading; nothing here can fail an utterance that used to work.
        pos_tags: Optional[List[str]] = None
        if any(w in _HETERONYM for w in words):
            # ALWAYS the English tagger: every _HETERONYM entry is an English word, so the
            # tag that selects its reading is an English tag whatever language the sentence
            # routed as. This matters because short English sentences ("I have read it")
            # route to Welsh -- the router wants ~5 English words -- and the Welsh tagger
            # cannot tag English, so the reading fell to the majority fallback exactly where
            # a screen reader most needs it. On a genuinely Welsh sentence with an embedded
            # heteronym the English tagger sees unknown context and lands near its bias,
            # which is no worse than the fallback it replaces.
            tagger = self._pos_tagger("en")
            if tagger is not None:
                pos_tags = tagger.tag(words)

        tokens: List[str] = []
        word_i = -1
        for lead, core, trail in segments:
            piece: List[str] = list(lead)
            if core:
                word_i += 1        # tracks `words`, which counted every non-empty core
            if core and any(c.isalpha() for c in core):
                pos = (pos_tags[word_i]
                       if pos_tags is not None and 0 <= word_i < len(pos_tags) else None)
                # "go live" is a fixed expression (a streaming UI's Go Live button): the tagger
                # calls both words verbs, but this "live" is the adjective /laɪv/.
                if core == "live" and word_i > 0 and words[word_i - 1] in _GO_FORMS:
                    pos = "ADJ"
                # "live" is intransitive: directly before a noun it is the attributive adjective
                # ("start Live Recognition", "live music"), whatever the tagger called it.
                elif (core == "live" and pos_tags is not None and word_i + 1 < len(pos_tags)
                      and pos_tags[word_i + 1] in ("NOUN", "PROPN")):
                    pos = "ADJ"
                word_toks = self._word_tokens(core, on_oov, lang, solo_vowel=solo_vowel,
                                              pos=pos)
                if word_toks:
                    piece.extend(word_toks)
            piece.extend(trail)
            if not piece:
                continue
            if tokens:
                tokens.append(WORD_SEP)  # word boundary between successive emitted pieces
            tokens.extend(piece)
        return tokens

    def _acronym_tokens(self, word: str) -> Optional[List[str]]:
        """Expand an ACRONYM_JOIN-marked core into ENGLISH letter names, or None.

        Welsh speech reads acronyms with English letter names (API, TTS, BBC ->
        ay-pee-eye, tee-tee-ess, bee-bee-cee). The marker is put there by
        welsh_normalize._spell_acronym, which is the only place that still knows an
        acronym boundary was crossed; an ISOLATED or punctuation-separated letter --
        keyboard echo, dictated spelling ("c, a, th") -- carries no marker and keeps its
        Welsh name. Each letter is its own spoken word, so they are WORD_SEP-separated,
        which is what the trained model saw for these ids.

        Returns None when the core is NOT an acronym, i.e. when any marker-separated part
        is anything other than a single letter we have a name for. U+00B7 is a character a
        user can type (Catalan punt volat, Greek ano teleia, a stray keystroke), so a core
        can arrive carrying one that _spell_acronym never wrote. This used to skip every
        unrecognised part and return whatever was left, which SILENTLY DELETED the text:
        "mae 5·5 yma" normalized to "mae pump·pump yma" and spoke "mae yma", and
        "pris·da" produced nothing at all -- a 200 response with ~58 ms of silence.
        Every genuine marker _spell_acronym emits separates single a-z letters, so
        requiring that of all parts costs nothing and makes the collision safe."""
        parts = word.split(ACRONYM_JOIN)
        if not all(part in _EN_LETTER_NAMES for part in parts):
            return None
        out: List[str] = []
        for i, part in enumerate(parts):
            if i:
                out.append(WORD_SEP)
            out.extend(_EN_LETTER_NAMES[part])
        return out

    def _typed_marker_tokens(self, word: str, on_oov: str, lang: str) -> List[str]:
        """Speak a core whose U+00B7 is literal text, not our acronym marker.

        The marker is treated as a WORD SEPARATOR and every part goes through the normal
        word path, so nothing is dropped: "pump·pump" reads "pump pump" (five five).
        Deleting the marker instead would join the parts into one invented word
        ("pumppump") and hand that to LTS -- still corruption, just not deletion. Every
        real-world use of U+00B7 (Catalan l·l, Greek ano teleia, the dot operator) is a
        separator, so splitting is also the honest reading of the character."""
        pieces: List[List[str]] = []
        for part in word.split(ACRONYM_JOIN):
            if not part:
                continue
            toks = self._word_tokens(part, on_oov, lang)
            if toks:
                pieces.append(toks)
        out: List[str] = []
        for i, piece in enumerate(pieces):
            if i:
                out.append(WORD_SEP)
            out.extend(piece)
        return out

    def _sentence_lang(self, words: List[str]) -> str:
        """Dominant language of a run of words, so shared words (present in BOTH the
        Welsh and English lexicons, e.g. "Wales"/"the"/"access" vs "a"/"ac"/"aber")
        resolve toward the language actually being spoken.

        Welsh is the DEFAULT (the voice's majority language). We switch to English
        only on confident, sustained evidence: words exclusive to the English lexicon
        must outnumber the Welsh-exclusive ones AND make up a real share of the run
        (at least two, and at least a third). This keeps genuinely-English sentences
        English while stopping a lone English loanword or interjection ("taxi", "no",
        "ok") from flipping a Welsh utterance built from shared words — which would
        corrupt every shared Welsh word (banc -> /bæŋk/). Individual code-switched
        words still resolve per-word inside the chosen context (see _word_tokens)."""
        return "en" if self._lang_score(words) <= -_PRIOR_MIN else "cy"

    def _word_weight(self, w: str) -> int:
        """The prior's weight for one (lowercased) word: the table, or +-1 nat from dictionary
        exclusivity added, or 0."""
        # A letter name ("c", "th", "B.") is not a word: English text is full of letters as list
        # markers and initials, which would route "Z." English. The only letters that ARE words
        # here are Welsh "o" (of) and "y" (the); "a" and "i" are words in both languages and
        # cancel, so they are left neutral too.
        if (len(w) == 1 or w in _WELSH_LETTERS) and w not in _LETTER_WORDS:
            return 0
        # Corpus weight PLUS dictionary exclusivity (2026-09-08; was "table, else exclusivity").
        # A rare word's corpus weight is noise ("unread" +7 from one Welsh tweet made "2 unread
        # messages" Welsh); the lexicon knows it is English. Held-out (scripts/gen_lang_prior.py
        # split): English 98.6% -> 99.2%, Welsh 99.7% unchanged.
        v = self.lang_prior.get(w, 0)
        in_welsh = self.lexicon.lookup_welsh(w) is not None
        in_english = self.english.lookup(w) is not None
        if in_welsh and not in_english:
            return v + _PRIOR_FALLBACK
        if in_english and not in_welsh:
            return v - _PRIOR_FALLBACK
        return v

    def _lang_score(self, words: List[str]) -> int:
        """Sum of the words' weights; positive Welsh, negative English, 0 no evidence. Letter
        names ("c, a, th") weigh nothing (_word_weight)."""
        return sum(self._word_weight(w) for w in words)

    def _routing_words(self, text: str) -> List[str]:
        """The words _sentence_lang scores for `text`: every non-empty core with a letter or
        digit, after the same segmentation and hyphen splitting phonemize applies."""
        return self._routing_words_of(self._split_unknown_hyphen_compounds(list(self._segment(text))))

    @staticmethod
    def _routing_words_of(segments) -> List[str]:
        words = []
        for _lead, core, _trail in segments:
            # an ACRONYM_JOIN-marked core ("ab·cd") is emitted as its parts, so it is scored
            # as its parts too (the C tokeniser splits it before routing)
            for part in core.split(ACRONYM_JOIN) if core else ():
                if part and any(ch.isalnum() for ch in part):
                    words.append(part)
        return words

    def _route_sentences(self, text: str, spans) -> List[str]:
        """Phone routing per SENTENCE (owner, 2026-09-08: "surely it's possible to have an
        English sentence followed by a Welsh sentence and get the correct phonemes").

        Each sentence takes the sign of its own prior score; a sentence with no evidence takes
        the whole utterance's decision, so a short "I agree." inside English text does not flip.
        The same spans as the number language (_split_sentences), so the two decisions never
        disagree on where a sentence ends."""
        whole = self._sentence_lang(self._routing_words(text))
        langs = []
        for start, end, dend, _kind in spans:
            s = self._lang_score(self._routing_words(text[start:dend].rstrip(_NL_WS)))
            langs.append("en" if s <= -_PRIOR_MIN else "cy" if s >= _PRIOR_MIN else whole)
        return langs

    def _word_tokens(self, word: str, on_oov: str, lang: str = "cy",
                     solo_vowel: bool = False,
                     pos: Optional[str] = None) -> Optional[List[str]]:
        # Isolated letters are spelled by name, not looked up: the lexicons resolve a
        # bare "b" to the naked stop /b/ (unpronounceable as an utterance) and have no
        # entry at all for ll/rh/ff/ng/th. A marked acronym gets ENGLISH letter names
        # (how Welsh reads API/TTS/BBC); digraphs are Welsh letters in any context;
        # other single consonants get Welsh names, except that an English-context
        # sentence under native mode keeps CMUdict's.
        if solo_vowel and word in _CY_VOWEL_SOLO:  # single typed vowel key, not a word
            return list(_CY_VOWEL_SOLO[word])
        if ACRONYM_JOIN in word:
            acronym = self._acronym_tokens(word)
            if acronym is not None:
                return acronym
            # a U+00B7 the author typed, not the marker _spell_acronym writes
            return self._typed_marker_tokens(word, on_oov, lang)
        if word in _CY_DIGRAPH_NAMES:
            return list(_CY_DIGRAPH_NAMES[word])
        if word in _CY_LETTER_NAMES and not (self.english_mode == "native" and lang == "en"):
            return list(_CY_LETTER_NAMES[word])
        # Heteronyms, before either lexicon: both routes hold one reading and it is the wrong
        # one for 9 of 15 words. pos is None until the tagger lands, which selects the
        # majority-reading fallback -- see _HETERONYM.
        if word in _HETERONYM:
            branch = _HETERONYM[word]
            return list(branch.get(pos) or branch[None])
        if self.english_mode == "native":
            welsh = self.lexicon.lookup_welsh(word)
            en_available = self.english.lookup(word) is not None
            if lang == "en":
                # English context: the English lexicon wins for any word it knows,
                # so shared words get their English pronunciation (Wales -> weɪlz).
                # A word only the Welsh lexicon knows is a Welsh code-switch -> Welsh.
                if en_available:
                    return self.english.phonemize(word, native=True)
                if welsh is not None:
                    return welsh
            else:
                # Welsh context (default): the Welsh lexicon wins, protecting
                # genuinely-Welsh words that also exist in English (a, ac, aber…).
                # A word only English knows is an English code-switch -> English.
                if welsh is not None:
                    return welsh
                if en_available or classify_word(word) == "en":
                    return self.english.phonemize(word, native=True)
            # OOV: route the letter-to-sound fallback by context.
            if on_oov == "skip":
                return None
            if on_oov == "lts":
                if lang == "en" or classify_word(word) == "en":
                    return self.english.phonemize(word, native=True)
                return lts(word)
            raise OOVError(word)

        # "accented" (default): English via the Bangor Welsh-accented tables.
        hit = self.lexicon.lookup(word)
        if hit is not None:
            return hit
        if on_oov == "skip":
            return None
        if on_oov == "raise":
            raise OOVError(word)
        # on_oov == "lts": prefer the English G2P (folded) for English OOV, else Welsh LTS.
        if self.english.lookup(word) is not None or classify_word(word) == "en":
            return self.english.phonemize(word, native=False)
        return lts(word)

    def phonemes_to_ids(self, tokens: List[str]) -> List[int]:
        pad, bos, eos = self.control["pad"], self.control["bos"], self.control["eos"]
        ids = [bos]
        for t in tokens:
            ids += [pad, self.id_map[t][0]]
        ids += [pad, eos]
        return ids

    def segments(self, text: str, on_oov: str = "lts",
                 lang: Optional[str] = None) -> List[Segment]:
        """The utterance as rendering units (docs/text-structure-programme.md §3.1).

        Each segment is a sentence, a heading or a list line, with the boundary that follows it.
        A line without terminal punctuation takes a full stop, so a heading gets the sentence-final
        fall. Numbers and phones are decided per segment with the previous segment's language as
        the fallback for a segment with no evidence (the first falls back to the whole utterance's
        decision). An explicit `lang` applies to every segment. Consumers synthesise one pass per
        segment and insert BOUNDARY_GAP_MS[boundary] of silence between them; text_to_ids is the
        concatenation, so a whole-text caller and a per-segment caller agree by construction."""
        raw: List[Tuple[str, str]] = []
        for start, end, dend, kind in self._split_sentences(text):
            seg = text[start:dend].strip(_NL_WS)      # with its own terminal punctuation
            if not seg:
                continue
            if kind in ("line", "paragraph") and seg[-1] not in _NO_FULL_STOP_AFTER:
                seg += "."
            raw.append((seg, kind))
        if not raw:
            return []
        norms: List[Tuple[str, str]] = []
        num = "cy"
        for seg, _kind in raw:
            norm, num = self._normalize_carry(seg, lang, default=num)
            norms.append((norm, num))
        words_per: List[List[str]] = [self._routing_words(norm) for norm, _ in norms]
        whole = self._sentence_lang([w for ws in words_per for w in ws])
        prev = whole
        out: List[Segment] = []
        for (seg, kind), (norm, nl), ws in zip(raw, norms, words_per):
            if lang:
                pl = lang
            else:
                s = self._lang_score(ws)
                pl = "en" if s <= -_PRIOR_MIN else "cy" if s >= _PRIOR_MIN else prev
            prev = pl
            toks = self.phonemize(norm, on_oov=on_oov, lang=pl)
            out.append(Segment(norm, toks, self.phonemes_to_ids(toks), kind, nl, pl))
        return out

    def text_to_ids(self, text: str, on_oov: str = "lts",
                    lang: Optional[str] = None) -> List[int]:
        """The whole utterance as one id sequence: the segments' phones joined by WORD_SEP."""
        toks: List[str] = []
        for seg in self.segments(text, on_oov=on_oov, lang=lang):
            if seg.tokens and toks:
                toks.append(WORD_SEP)
            toks.extend(seg.tokens)
        return self.phonemes_to_ids(toks)

    # --- integrity ---
    def _compute_data_version(self, id_map_raw: str) -> str:
        h = hashlib.sha256()
        h.update(_EMISSION_POLICY.encode())
        h.update(id_map_raw.encode())
        for name in _DICT_ORDER:
            h.update(name.encode())
            h.update((self.lexicon.data_dir / name).read_bytes())
        # The native English lexicon, hashed from 2026-09-04. It was OUTSIDE this hash
        # while it determined the accent of every English word the voice speaks, so
        # converting it from General American to Welsh English -- a change that needs a
        # matching model -- moved data_version not at all. That is exactly the pairing
        # failure this hash exists to prevent. Hashed unconditionally, not only under
        # english_mode="native": data_version describes the DATA, and both modes are
        # compared against one generated data_version.txt on the C side.
        h.update(b"cmudict_native.dict")
        h.update(_ENGLISH_LEXICON.read_bytes())
        # The POS models, hashed from 2026-09-04. They decide which reading a heteronym
        # gets, so they are emission-relevant data on exactly the same footing as the
        # dictionaries. Hashed in a fixed order, and a MISSING model is hashed as absent
        # rather than skipped: pos_tagger.load() returns None so the code degrades to the
        # majority reading instead of crashing, but a distro that ships without the models
        # is not running the same G2P and data_version must not claim otherwise.
        for name in ("pos_cy.bin", "pos_en.bin"):
            h.update(name.encode())
            f = _POS_DATA / name
            h.update(f.read_bytes() if f.exists() else b"<absent>")
        # The language prior, hashed from 2026-09-08: it decides which lexicon a shared word
        # reads from ("banc", "more", "un"), so it is emission-relevant data on the same footing
        # as the POS models.
        h.update(b"lang_prior.tsv")
        h.update(_LANG_PRIOR.read_bytes())
        return h.hexdigest()[:16]

    def data_version(self) -> str:
        return self._data_version


if __name__ == "__main__":
    g = BangorG2P()
    print("lexicon:", g.lexicon.stats)
    print("data_version:", g.data_version())
    for w in ["da", "cymraeg", "prifysgol", "bangor"]:
        try:
            print(f"  {w!r} -> {g.phonemize(w)}")
        except OOVError:
            print(f"  {w!r} -> OOV")
