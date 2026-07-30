import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

IPA_MAP = REPO / "techiaith" / "g2p" / "ipa_map.json"


def test_ipa_map_covers_every_phone_token():
    """Every phone token must be reachable from some IPA spelling, and nothing else."""
    spec = json.loads((REPO / "techiaith" / "g2p" / "bangor_phoneme_id_map.json").read_text(encoding="utf-8"))
    ipa = json.loads(IPA_MAP.read_text(encoding="utf-8"))["ipa_to_token"]

    # 85 tokens = 4 control + 3 stress/syllable + 13 punctuation + 65 phones
    non_phones = set("_^$ ") | {"ˈ", "ˌ", "|"} | set(".,?!;:-()\"'…—")
    phones = {t for t in spec["phoneme_id_map"] if t not in non_phones}
    assert len(phones) == 65, f"expected 65 phone tokens, got {len(phones)}"

    assert set(ipa.values()) == phones, (
        f"unreachable phones: {sorted(phones - set(ipa.values()))}; "
        f"bogus targets: {sorted(set(ipa.values()) - phones)}"
    )
    # the 7 reserved English phones are already IPA and map to themselves
    for t in ("æ", "ʌ", "ɒ", "ɪə", "eə", "ʊə", "ɹ"):
        assert ipa[t] == t
    # longest-match tokenizers rely on this bound
    assert max(len(k) for k in ipa) == 2


def test_ipa_map_pinned_pairs():
    """Spot-check individual IPA->token pairings against phoneset.md.

    The coverage test above only checks the aggregate value SET, so a generator
    bug that permutes assignments while preserving that set (e.g. an off-by-one
    row walk pairing each IPA cell with the next row's ASCII token) would slip
    through undetected. Pin specific pairs, verified directly against the
    `| ASCII | IPA |` tables in phoneset.md, to catch that class of bug.
    """
    ipa = json.loads(IPA_MAP.read_text(encoding="utf-8"))["ipa_to_token"]
    expected = {
        # short vowel: "| e   | ɛ   | ... Llafariad canolog blaen ..." (not "hir"/long)
        "ɛ": "e",
        # long vowel: "| aa  | aː  | ... blaen hir ..." (sâl, tad)
        "aː": "aa",
        # digraph-derived consonant: "| ch  | tʃ  | ... cwtsh"
        "tʃ": "ch",
        # self-mapped reserved English phone (not from phoneset.md; from the
        # id map's "english" category / the generator's SELF_MAPPED list)
        "ɹ": "ɹ",
        # central closing diphthong: "| aay | ɑɨ  | ... cae"
        "ɑɨ": "aay",
        # voiceless uvular fricative: "| x   | χ   | Ffrithiolyn wfwlar di-lais"
        "χ": "x",
    }
    for ipa_key, token in expected.items():
        assert ipa.get(ipa_key) == token, f"{ipa_key!r} -> {ipa.get(ipa_key)!r}, expected {token!r}"


def test_ipa_map_is_injective():
    """No two IPA spellings may collapse to the same token.

    This does NOT catch a row-shifted generator, and the earlier claim that it
    did was wrong: the map is 65 keys onto 65 distinct values, so any
    permutation of the assignment -- an off-by-one row walk included -- is
    still a bijection. It passes this test and the value-set assertion in
    test_ipa_map_covers_every_phone_token alike (verified by walking one). Only
    the pinned pairs above catch that class.

    What this test does catch is a map that stops being a bijection: an added
    or edited key that aliases an existing token (two IPA spellings both
    reaching "aa"), which necessarily leaves some other phone unreachable or
    silently merges two contrasts. Cheap, and orthogonal to the pinned pairs.
    """
    ipa = json.loads(IPA_MAP.read_text(encoding="utf-8"))["ipa_to_token"]
    tokens = list(ipa.values())
    dupes = {t for t in tokens if tokens.count(t) > 1}
    assert not dupes, f"tokens claimed by more than one IPA spelling: {sorted(dupes)}"


def test_tokens_from_phones_bangor_roundtrip():
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    assert g.tokens_from_phones("ˈ b a n g o r") == ["ˈ", "b", "a", "n", "g", "o", "r"]
    # a word's own lexicon tokens must survive a round trip
    toks = g.phonemize("bangor")
    assert g.tokens_from_phones(" ".join(toks)) == toks


def test_tokens_from_phones_ipa_longest_match():
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    # unspaced IPA, longest-match: "aː" is one token, not "a" + "ː"
    assert g.tokens_from_phones("baːn", alphabet="ipa") == ["b", "aa", "n"]
    # stress and syllable marks pass through in either alphabet
    assert g.tokens_from_phones("ˈbaːn", alphabet="ipa") == ["ˈ", "b", "aa", "n"]


def test_tokens_from_phones_rejects_unknown():
    import pytest
    from techiaith.g2p.bangor_g2p import BangorG2P, PhoneError
    g = BangorG2P(english_mode="native")
    with pytest.raises(PhoneError, match="zzz"):
        g.tokens_from_phones("b zzz n")
    with pytest.raises(PhoneError, match="ǃ"):
        g.tokens_from_phones("bǃn", alphabet="ipa")
    with pytest.raises(PhoneError, match="alphabet"):
        g.tokens_from_phones("ban", alphabet="x-sampa")


def test_tokens_from_phones_rejects_structural_tokens():
    """Authors supply phones, not control tokens: pad/bos/eos and word separators are ours."""
    import pytest
    from techiaith.g2p.bangor_g2p import BangorG2P, PhoneError
    g = BangorG2P(english_mode="native")
    for bad in ("_", "^", "$"):
        with pytest.raises(PhoneError):
            g.tokens_from_phones(bad)


def test_forced_lang_overrides_sentence_detection():
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    # "Wales" exists in both lexicons; automatic routing calls this sentence Welsh
    auto = g.phonemize(g.normalize("Wales"), on_oov="lts")
    forced_en = g.phonemize(g.normalize("Wales"), on_oov="lts", lang="en")
    assert forced_en != auto, "forcing English must change a shared word's realisation"
    assert forced_en == g.english.phonemize("wales", native=True)


def test_forced_lang_cy_protects_welsh_words():
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    # an English-dominant sentence would route "banc" to English; cy must prevent that
    text = g.normalize("the modern banc access")
    assert g.phonemize(text, on_oov="lts", lang="cy") != g.phonemize(text, on_oov="lts", lang="en")
    assert g.phonemize("banc", on_oov="lts", lang="cy") == g.lexicon.lookup_welsh("banc")


def test_lang_none_reproduces_golden_and_consults_sentence_lang():
    """lang omitted must be byte-for-byte identical to the pre-`lang` behaviour, checked
    against an independent oracle rather than against another call with the same
    (indistinguishable) default -- and the fallback must genuinely call _sentence_lang
    rather than a hardcoded constant.

    `phonemize(n, on_oov="lts") == phonemize(n, on_oov="lts", lang=None)` is tautological:
    Python cannot tell an omitted keyword from one explicitly passed its own default, so
    that assertion holds for any implementation whatsoever, including a broken one that
    ignores the `lang` override entirely. The oracle here is a FROZEN file,
    tests/golden/bilingual_prelang_native.tsv, whose whole value is that it predates the
    code it checks:

      * rows 1..69 are byte-for-byte the bilingual_golden_native.tsv committed at 05d9436,
        generated by the then-current text_to_ids(text) with no lang argument in existence;
      * rows 70..82 were appended at d0e019b (the literal-U+00B7 fix), so they predate the
        2026-07-27 language decisions but not `lang` itself.

    It lives under tests/golden/ and is NOT written by scripts/emit_c_data.py, unlike
    techiaith/g2p/c/bilingual_golden_native.tsv, which this test used to read. That file
    is now regenerated whenever Python changes, so reading it would make this test compare
    current Python against itself -- tautological again, which is the exact failure mode
    this docstring exists to prevent. NEVER point this test back at a generated corpus,
    and never refresh the frozen file to make a failure go away: a diff here means either
    a regression (fix the code) or a deliberate decision (add it to CHANGED below, with
    its own independent oracle).

    CHANGED records the intentional behaviour changes since the freeze. Each expectation
    is rebuilt from the TABLE THAT IS THE DECISION (_CY_VOWEL_SOLO, _CY_LETTER_NAMES)
    through phonemes_to_ids, so it stays independent of phonemize/_segment/_word_tokens,
    the machinery under test. Every other row must still match the frozen bytes exactly.

      * 2026-07-27 isolated-vowel letter names for a/e/u/y (owner, by ear).
      * 2026-07-27 isolated K -> "cê" (piper-lleol issue #5). K is absent from Tabl 1 of
        the verbatim transcription guidelines, so it falls back to Tabl 2's "ke", the
        same route that already gives q -> ciw and x -> ecs.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P, _CY_VOWEL_SOLO, _CY_LETTER_NAMES
    g = BangorG2P(english_mode="native")

    # text -> the phone tokens the decision mandates. i/o/w already had solo vowel names
    # before the freeze and must NOT appear here.
    CHANGED = {v: list(_CY_VOWEL_SOLO[v]) for v in ("a", "e", "u", "y")}
    # Isolated K, in the three casings/punctuations the corpus carries. "." is appended
    # for "K." because the frozen rows show sentence punctuation as its own trailing token.
    CHANGED["k"] = list(_CY_LETTER_NAMES["k"])
    CHANGED["K"] = list(_CY_LETTER_NAMES["k"])
    CHANGED["K."] = list(_CY_LETTER_NAMES["k"]) + ["."]

    # NOTE, and the frozen oracle earned its keep here: the number register was moved to
    # vigesimal and back on 2026-07-27, so "Mae 25 o gathod", "yn 2026" and "A55." briefly
    # needed CHANGED entries and now do NOT. They read exactly as the frozen bytes again.
    # Leaving those entries in place would have asserted `expected_ids != frozen_ids` and
    # failed -- which is precisely how an exception list is supposed to behave when the
    # behaviour it excuses goes away.
    #
    # 2026-07-28: "mil"/"fil" take the LONG vowel (bangor_g2p._CY_PRON_OVERRIDE -- the
    # Bangor dictionary has them short, which made every thousand and every year 1000-2099
    # unintelligible; the owner isolated it by ear on the live service). "yn 2026" reads
    # "yn dwy fil a dau ddeg chwech", so its frozen row carries the short-i "fil".
    #
    # This one cannot use CHANGED, because CHANGED rebuilds a whole row's phones from a
    # table and this row is a six-word sentence, not a single letter. Rebuilding it through
    # phonemize would be the tautology the docstring forbids. So the oracle is the FROZEN
    # BYTES with the single id substitution the decision mandates, i -> ii, which touches
    # no machinery under test. The count assertion is what keeps it honest: if the row ever
    # contains more than one short "i", this substitution is ambiguous and must be revisited
    # rather than silently applied to the wrong phone.
    SUBST_I_TO_II = {"yn 2026"}
    _I, _II = g.id_map["i"][0], g.id_map["ii"][0]

    PRE_LANG_ROWS = 69      # rows 1..69 are the 05d9436 file, the independent oracle
    frozen_path = REPO / "tests" / "golden" / "bilingual_prelang_native.tsv"
    rows = [line.split("\t") for line in frozen_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) >= PRE_LANG_ROWS, (
        f"expected at least the {PRE_LANG_ROWS} pre-lang golden rows, got {len(rows)} "
        f"(file truncated?)")
    assert set(CHANGED) | SUBST_I_TO_II <= {text for text, _ in rows}, (
        "the frozen oracle no longer contains the rows the exception list is about; "
        "it has been replaced rather than frozen")
    for text, ids_str in rows:
        frozen_ids = [int(x) for x in ids_str.split()]
        if text in SUBST_I_TO_II:
            assert frozen_ids.count(_I) == 1, (
                f"{text!r} has {frozen_ids.count(_I)} short-i phones in the frozen row, so "
                f"substituting i -> ii is ambiguous; identify the mil/fil position instead")
            expected_ids = [_II if x == _I else x for x in frozen_ids]
            assert expected_ids != frozen_ids, (
                f"the frozen oracle already carries the long vowel for {text!r}: it has been "
                f"regenerated. Restore it from git, do not refresh it.")
        elif text in CHANGED:
            expected_ids = g.phonemes_to_ids(CHANGED[text])
            assert expected_ids != frozen_ids, (
                f"the frozen oracle already carries the NEW rendering for {text!r}: it has "
                f"been regenerated, so it no longer predates the change it is meant to "
                f"pin. Restore it from git (05d9436 / d0e019b), do not refresh it.")
        else:
            expected_ids = frozen_ids
        got_ids = g.text_to_ids(text)  # lang omitted entirely
        assert got_ids == expected_ids, (
            f"lang-omitted text_to_ids diverged from the pre-lang golden for {text!r}: "
            f"expected {expected_ids}, got {got_ids}"
        )

    # The fallback must genuinely consult _sentence_lang, not a hardcoded constant: pick
    # a text whose inferred language is "en" (the non-default) using the same word
    # extraction phonemize itself uses, then check that omitting lang matches explicitly
    # passing that inferred value. A hardcoded fallback (e.g. always "cy") would make
    # these two calls diverge.
    text = g.normalize("computer windows")
    words = [core for _lead, core, _trail in g._segment(text) if core]
    inferred = g._sentence_lang(words)
    assert inferred == "en", f"test setup assumes an English-inferred sentence, got {inferred!r}"
    assert g.phonemize(text, on_oov="lts", lang=inferred) == g.phonemize(text, on_oov="lts")


def test_text_to_ids_forwards_lang():
    """text_to_ids must pass `lang` on to phonemize.

    Nothing on the Python side pinned this: deleting `lang=lang` from text_to_ids left
    all 40 tests green, because every other lang test calls phonemize directly. It is
    the exact entry point the HTTP API calls for SSML <lang xml:lang="...">, so a
    silently dropped override there means the whole feature does nothing in production
    while the unit tests stay green. (The C mirror is covered, by lang_golden.tsv.)

    lang_golden.tsv is the oracle: it was generated through text_to_ids itself, so it
    is checked here against the assertion that the three variants are not all equal --
    without that guard a dropped pass-through would just make the rows agree with each
    other and the comparison would prove nothing.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")

    rows = [line.split("\t") for line in
            (REPO / "techiaith" / "g2p" / "c" / "lang_golden.tsv")
            .read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(rows) == 21, f"expected 21 golden rows, got {len(rows)} (file truncated?)"
    seen_difference = False
    by_text: dict = {}
    for text, lang, ids_str in rows:
        expected = [int(x) for x in ids_str.split()]
        got = g.text_to_ids(text, lang=None if lang == "-" else lang)
        assert got == expected, (
            f"text_to_ids({text!r}, lang={lang!r}) diverged from lang_golden.tsv: "
            f"expected {expected}, got {got}")
        by_text.setdefault(text, {})[lang] = expected
    for text, variants in by_text.items():
        if variants.get("cy") != variants.get("en"):
            seen_difference = True
    assert seen_difference, (
        "no golden row distinguishes lang='cy' from lang='en', so these rows cannot "
        "prove the override is forwarded at all")

    # ...and the same thing said directly, so the failure message names the cause.
    assert g.text_to_ids("Wales", lang="en") != g.text_to_ids("Wales", lang="cy"), (
        "text_to_ids is not forwarding lang to phonemize")


def test_invalid_lang_rejected():
    import pytest
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    with pytest.raises(ValueError, match="fr"):
        g.phonemize("bore da", on_oov="lts", lang="fr")


def test_letter_tokens_is_digraph_aware():
    """The vowel piece's oracle is _CY_VOWEL_SPELLED -- the table that IS the decision --
    not g.phonemize("a"), which as a whole one-character utterance would re-derive the
    isolated-keystroke branch and return the _CY_VOWEL_SOLO name instead. Asserting the
    full sequence also pins the semicolon separator and the digraph split in one place.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P, _CY_DIGRAPH_NAMES, _CY_LETTER_NAMES, _CY_VOWEL_SPELLED
    g = BangorG2P(english_mode="native")
    assert g.letter_tokens("llan") == (
        list(_CY_DIGRAPH_NAMES["ll"]) + [";"]
        + list(_CY_VOWEL_SPELLED["a"]) + [";"]
        + list(_CY_LETTER_NAMES["n"]))


def test_letter_tokens_consonants_use_welsh_names():
    from techiaith.g2p.bangor_g2p import BangorG2P, _CY_LETTER_NAMES, WORD_SEP
    g = BangorG2P(english_mode="native")
    got = g.letter_tokens("bt")
    assert got == list(_CY_LETTER_NAMES["b"]) + [";"] + list(_CY_LETTER_NAMES["t"])
    assert WORD_SEP not in got, "spell-out must use the semicolon pause, not WORD_SEP"
    assert "," not in got, "spell-out still uses the old comma pause"


def test_letter_tokens_reads_digits_as_numbers():
    from techiaith.g2p.bangor_g2p import BangorG2P, _CY_LETTER_NAMES, WORD_SEP
    g = BangorG2P(english_mode="native")
    got = g.letter_tokens("s4c")
    assert got[:len(_CY_LETTER_NAMES["s"])] == list(_CY_LETTER_NAMES["s"])
    assert got[-len(_CY_LETTER_NAMES["c"]):] == list(_CY_LETTER_NAMES["c"])
    assert ";" in got
    assert WORD_SEP not in got, "spell-out must use the semicolon pause, not WORD_SEP"

    # A single-digit run ("s4c" above) cannot distinguish "read the run as one number"
    # from "read each digit individually" -- for a run of length 1 those are
    # byte-identical. Pin a multi-digit run instead: "s42c" must read 42 as the single
    # cardinal "pedwar deg dau" (forty-two), not digit-by-digit as "pedwar dau" (four,
    # two). Derive the expected phones from num_to_welsh_public(42) phonemized -- not a
    # hand-written phone list -- so this stays correct if the cardinal verbaliser's
    # wording changes, and assert the full structural sequence: s, comma, the
    # forty-two tokens, comma, c.
    forty_two = g.phonemize(g.normalizer.num_to_welsh_public(42), on_oov="lts")
    assert g.letter_tokens("s42c") == (
        list(_CY_LETTER_NAMES["s"]) + [";"] + forty_two
        + [";"] + list(_CY_LETTER_NAMES["c"]))


def test_letter_tokens_spells_vowels_by_name_not_as_words():
    """Supersedes an earlier "plain vowels in spell-out" rule, which was reversed by ear
    on 2026-07-27 after listening to 31 words.

    That rule sent a spelled vowel to the lexicon, and because a/e/i/o/y are real Welsh
    function words the lexicon returned the short unstressed WORD. It had only ever been
    auditioned on 'bach', whose single vowel is the one where the word and the letter name
    are near-indistinguishable -- so nothing caught that 'w', not being a function word,
    fell through to English and came back as a three-syllable "double-you".

    The direction of the old assertion is kept as the guard: the spelled vowel must now
    differ from the plain lexicon form, so a silent revert fails here.
    """
    from techiaith.g2p.bangor_g2p import (BangorG2P, _CY_LETTER_NAMES, _CY_DIGRAPH_NAMES,
                            _CY_VOWEL_SPELLED)
    g = BangorG2P(english_mode="native")
    plain_a = g.lexicon.lookup_welsh("a")
    assert plain_a != list(_CY_VOWEL_SPELLED["a"]), (
        "the letter name and the function word have collapsed; this test can no longer "
        "tell the two renderings apart")
    assert g.letter_tokens("bach") == (
        list(_CY_LETTER_NAMES["b"]) + [";"] + list(_CY_VOWEL_SPELLED["a"]) + [";"]
        + list(_CY_DIGRAPH_NAMES["ch"]))


# --- isolated-vowel keystrokes (Decision 1, 2026-07-27) -----------------------------

# The two vowel tables, written out as LITERALS. These are the ear decisions themselves,
# so they are the only real oracle for them: a test that reads the expectation out of the
# table it is checking cannot see a wrong VALUE in that table, only a wrong key. The
# previous version did exactly that while its docstring claimed the opposite -- setting
# _CY_VOWEL_SOLO["u"] to a triple passed every decision test on this branch.
#
# SOLO = one vowel alone as the whole utterance. SPELLED = a vowel inside a spell-out run.
# They differ on i/o/y on purpose; see their definitions in bangor_g2p.py.
_EXPECTED_SOLO = {
    "a": ["ˈ", "aa", "aa"], "e": ["ˈ", "ee", "ee"], "i": ["ˈ", "i", "ii"],
    "o": ["ˈ", "oo", "oo", "oo"], "u": ["ˈ", "iu", "iu"], "w": ["ˈ", "uu"],
    "y": ["ˈ", "@", "@"],
}
_EXPECTED_SPELLED = {
    "a": ["ˈ", "aa", "aa"], "e": ["ˈ", "ee", "ee"], "i": ["ˈ", "ii"],
    "o": ["ˈ", "oo"], "u": ["ˈ", "iu", "iu"], "w": ["ˈ", "uu"],
    "y": ["ˈ", "yy"],
}


def test_isolated_vowel_keystrokes_use_the_new_solo_names():
    """Both vowel tables, pinned against literals, and the pipeline against the tables.

    Two separate things are asserted, and both are needed: the LITERAL check catches a
    changed table value (an ear decision being edited), and the table-vs-pipeline check
    catches phonemize/letter_tokens ceasing to use the table it is supposed to.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P, _CY_VOWEL_SOLO, _CY_VOWEL_SPELLED
    g = BangorG2P(english_mode="native")

    assert set(_CY_VOWEL_SOLO) == set("aeiouwy"), (
        f"_CY_VOWEL_SOLO must be exactly a/e/i/o/u/w/y, got {sorted(_CY_VOWEL_SOLO)}")
    assert set(_CY_VOWEL_SPELLED) == set("aeiouwy"), (
        f"_CY_VOWEL_SPELLED must be exactly a/e/i/o/u/w/y, got {sorted(_CY_VOWEL_SPELLED)}")

    # The decisions themselves.
    assert {k: list(v) for k, v in _CY_VOWEL_SOLO.items()} == _EXPECTED_SOLO
    assert {k: list(v) for k, v in _CY_VOWEL_SPELLED.items()} == _EXPECTED_SPELLED
    # ...and they must stay distinct, or one of the two decisions has been lost.
    assert _EXPECTED_SOLO != _EXPECTED_SPELLED
    for letter in "ioy":
        assert _EXPECTED_SOLO[letter] != _EXPECTED_SPELLED[letter], letter

    # The pipeline really reads them: a solo keystroke takes SOLO...
    for letter in "aeiouwy":
        got = g.phonemize(letter, on_oov="lts")
        assert got == _EXPECTED_SOLO[letter], (
            f"solo keystroke {letter!r} -> {got}, expected {_EXPECTED_SOLO[letter]}")
    # ...and the same letter inside a spelled word takes SPELLED.
    for letter in "aeiouwy":
        got = g.letter_tokens("b" + letter + "b")[4:-4]
        assert list(got) == _EXPECTED_SPELLED[letter], (
            f"spelled {letter!r} -> {list(got)}, expected {_EXPECTED_SPELLED[letter]}")


def test_a_circumflex_is_not_in_solo_vowel_table():
    """â was compared by the owner and REJECTED in favour of the existing plain 'aa'
    rendering, so it must never be added to _CY_VOWEL_SOLO -- catches the mistake of
    copying the a/e/u/y pattern onto â too."""
    from techiaith.g2p.bangor_g2p import BangorG2P, _CY_VOWEL_SOLO, _CY_VOWEL_SPELLED
    assert "â" not in _CY_VOWEL_SOLO
    assert "â" not in _CY_VOWEL_SPELLED
    g = BangorG2P(english_mode="native")
    # A LITERAL, not `g._word_tokens(...)`: comparing phonemize against _word_tokens
    # compared the code path against itself, since phonemize reaches â THROUGH
    # _word_tokens. The bare "aa" here is the rendering the owner preferred over a
    # stressed/held one.
    assert g.phonemize("â", on_oov="lts") == ["aa"]
    # ŷ is the contrast case: it has no table entry either, but its lexicon form is
    # already the long "yy" that plain y now uses, which is part of why y -> yy was
    # chosen. If this ever stops being true the y decision's rationale is stale.
    assert g.phonemize("ŷ", on_oov="lts") == ["ˈ", "yy"]


def test_one_letter_word_in_a_sentence_never_uses_the_solo_vowel_name():
    """The whole point of solo_vowel requiring len(words) == 1: a one-letter WORD inside
    a real sentence must render as its plain lexicon form, never the isolated-keystroke
    name -- "Mae hi'n mynd" must not change just because "i" is a solo vowel elsewhere.
    Checks all seven letters (the existing acronym-boundary test only covers a/o/i/y)
    and asserts the FULL token sequence against an independent oracle
    (lexicon.lookup_welsh), not membership, so a leak of the solo name into a sentence
    is caught rather than merely "some output was produced".
    """
    from techiaith.g2p.bangor_g2p import BangorG2P, _CY_VOWEL_SOLO
    g = BangorG2P(english_mode="native")
    for letter in "aeiouwy":
        plain = g.lexicon.lookup_welsh(letter)
        assert plain != list(_CY_VOWEL_SOLO[letter]), (
            f"oracle for {letter!r} collapsed with its solo name; strengthen the test")
        sentence = g.normalize(f"{letter} ci")
        got = g.phonemize(sentence, on_oov="lts")
        expected = plain + [" "] + g.phonemize("ci", on_oov="lts")
        assert got == expected, (
            f"{letter!r} used its solo-keystroke name inside a sentence: {got}")


# --- hyphenated single-letter runs (Decision 3, 2026-07-27) -------------------------

def test_hyphenated_single_letters_act_as_separators():
    """'d-d-d' and 'b-a-ch' are keyboard echo: hyphens between single letters/digraphs
    must behave exactly like the commas in 'c, a, th', each letter its own token run
    separated by a comma pause. First prove equivalence with the comma-and-space
    spelling that already worked before this task (an independent, pre-existing code
    path); then pin the literal shape so a change to the separator convention itself
    is also caught, not just agreement between the two spellings.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P, _CY_LETTER_NAMES, _CY_DIGRAPH_NAMES
    g = BangorG2P(english_mode="native")
    assert g.phonemize("d-d-d", on_oov="lts") == g.phonemize("d, d, d", on_oov="lts")
    assert g.phonemize("b-a-ch", on_oov="lts") == g.phonemize("b, a, ch", on_oov="lts")

    d = list(_CY_LETTER_NAMES["d"])
    assert g.phonemize("d-d-d", on_oov="lts") == d + [",", " "] + d + [",", " "] + d

    b, a, ch = list(_CY_LETTER_NAMES["b"]), g.lexicon.lookup_welsh("a"), list(_CY_DIGRAPH_NAMES["ch"])
    assert g.phonemize("b-a-ch", on_oov="lts") == b + [",", " "] + a + [",", " "] + ch


def test_hyphen_rule_does_not_fire_on_real_compounds():
    """The critical constraint: word-internal hyphens must stay intact for real
    compounds. 'gogledd-ddwyrain' must still resolve as ONE lexicon key -- proved by
    checking it matches the lexicon's own multi-token pronunciation directly (not a
    hand-written phone list) and that no comma pause was inserted."""
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    expected = g.lexicon.lookup_welsh("gogledd-ddwyrain")
    assert expected is not None, "test assumes gogledd-ddwyrain is a lexicon key"
    assert len(expected) > 10, "expected a real multi-syllable pronunciation, not letters"
    got = g.phonemize("gogledd-ddwyrain", on_oov="lts")
    assert got == expected
    assert "," not in got, "the hyphen rule must not have fired on a real compound"


def test_hyphen_rule_requires_every_part_be_a_single_letter_unit():
    """Direct unit test of the classifier _segment relies on: EVERY hyphen-separated
    part must be exactly one letter or one of the eight digraphs, or the run is left
    alone. A 2-letter, non-digraph part ("xy") must block the split even though it is
    short -- this is the exact discriminator that keeps real compounds like
    'gogledd-ddwyrain' intact, so pin it directly rather than only through real words.
    """
    from techiaith.g2p.bangor_g2p import _hyphen_letter_run
    # A TWO-part run, first: every positive case here had three or more parts, so the
    # arity guard `len(parts) < 2` could be loosened to `< 3` and still pass -- silently
    # dropping the shortest real keyboard echo ("a-b") back into the lexicon.
    assert _hyphen_letter_run("a-b") == ["a", "b"]
    assert _hyphen_letter_run("ll-dd") == ["ll", "dd"]
    assert _hyphen_letter_run("d-d-d") == ["d", "d", "d"]
    assert _hyphen_letter_run("b-a-ch") == ["b", "a", "ch"]
    assert _hyphen_letter_run("xy-a") is None
    assert _hyphen_letter_run("a-xy") is None
    assert _hyphen_letter_run("gogledd-ddwyrain") is None
    assert _hyphen_letter_run("solo") is None  # no hyphen at all


def test_letter_tokens_ignores_whitespace_and_punctuation():
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    assert g.letter_tokens("b t") == g.letter_tokens("bt")
    assert g.letter_tokens("b-t") == g.letter_tokens("bt")


def test_letter_tokens_does_not_crash_on_non_decimal_numerics():
    """isalnum()/isdigit() are true for characters int() then rejects.

    '²' (U+00B2 superscript two) and '①' (U+2460 circled one) are both isdigit(), but
    int() raises ValueError on them. letter_tokens used to test isdigit() and hand the
    run straight to int(), so a <say-as interpret-as="characters"> payload containing
    either raised ValueError out of the G2P -- an unhandled 500 from the API, on input
    an author can type. The test is the pin: these characters must be skipped, exactly
    as the C port skips them, never raise.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    for ch in ("²", "①", "½", "Ⅷ", "₁", "〇"):
        assert g.letter_tokens(ch) == [], f"{ch!r} should spell as nothing"
        # and it must not disturb the letters around it
        assert g.letter_tokens(f"b{ch}c") == g.letter_tokens("bc"), f"{ch!r} not skipped"


def test_letter_tokens_still_reads_non_ascii_decimals():
    """Skipping non-decimal numerics must not regress genuine non-ASCII DECIMALS.

    '٣' is Arabic-Indic three: isdecimal() is true, int('٣') == 3, and it has always
    spelled out as the Welsh cardinal. int() also accepts a mixed-script run
    (int('٣4') == 34), which is why the run scan tests isdecimal() rather than
    restricting itself to ASCII.
    """
    from techiaith.g2p.bangor_g2p import BangorG2P
    g = BangorG2P(english_mode="native")
    assert g.letter_tokens("٣") == g.phonemize("tri", on_oov="lts")
    assert g.letter_tokens("٣٤") == g.phonemize(
        g.normalizer.num_to_welsh_public(34), on_oov="lts")
    assert g.letter_tokens("٣4") == g.letter_tokens("٣٤")


def test_python_digit_predicate_is_interpreter_independent():
    """The reference must classify digits from the vendored table, not the host interpreter.

    letter_tokens used ch.isdecimal(), which follows whatever Unicode version the user's
    Python carries -- 13 on the API container, 16 on a current system python. The C port
    carries a fixed table, so the two silently disagreed on every Nd block added after the
    canonical version. Vendoring the same table into Python removes the class of bug rather
    than documenting it.
    """
    from techiaith.g2p.canonical import ND_BLOCK, decimal_value, CANONICAL_UNICODE
    assert len(ND_BLOCK) == 65, f"expected the Unicode 13 table, got {len(ND_BLOCK)} blocks"
    assert CANONICAL_UNICODE == "13.0.0"
    # ASCII, and one non-ASCII block that exists in every Unicode version we care about
    assert [decimal_value(c) for c in "0123456789"] == list(range(10))
    assert decimal_value("٣") == 3      # Arabic-Indic three, in Unicode 13
    assert decimal_value("a") == -1
    assert decimal_value("²") == -1     # superscript two: isdigit, NOT isdecimal
    # Added after Unicode 13, so the canonical table must NOT claim them
    for cp in (0x11F50, 0x16AC0, 0x1E4F0):
        assert decimal_value(chr(cp)) == -1, f"{hex(cp)} postdates Unicode 13"


def test_c_decimal_table_matches_the_vendored_table():
    """The C port's Nd table and Python's vendored one must be the same table.

    This assertion used to compare C against the RUNNING interpreter's str.isdecimal(), which
    made it a test of the host's Unicode version rather than of the code: a Unicode 13 table
    genuinely disagrees with a Unicode 16 interpreter on 110 codepoints, so the suite could
    only be green on whichever machine generated the table. Both sides now read one vendored
    table, so this walks the whole codepoint space and asserts they are identical -- on every
    interpreter.
    """
    import ctypes
    from techiaith.g2p.canonical import decimal_value
    so = REPO / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
    if not so.exists():
        import pytest
        pytest.skip("libcy_phonemize.so not built (make -C techiaith/g2p/c libcy_phonemize.so)")
    lib = ctypes.CDLL(str(so))
    lib.cyp__cp_decimal_value.argtypes = [ctypes.c_long]
    lib.cyp__cp_decimal_value.restype = ctypes.c_int

    bad = []
    for cp in range(0x110000):
        want = decimal_value(chr(cp))
        got = lib.cyp__cp_decimal_value(cp)
        if got != want:
            bad.append((hex(cp), want, got))
            if len(bad) > 10:
                break
    assert not bad, f"C Nd table disagrees with the vendored table: {bad}"


def test_c_spells_every_nd_block_the_same_as_python():
    """Drive the digits through cyp_letter_tokens, not just the predicate underneath it.

    test_c_decimal_table_matches_unicodedata calls cyp__cp_decimal_value directly, so it
    passed green while the only caller of that predicate could not reach half the table:
    utf8_next had no 4-byte branch, so every SUPPLEMENTARY-plane digit decoded as U+FFFD
    one byte at a time and was silently dropped, where Python spells it out. 310 of 310
    astral Nd codepoints diverged and no test noticed, because none of them went through
    the real entry point. Walk one digit from every Nd block -- BMP and astral -- end to
    end instead.
    """
    import ctypes
    import unicodedata
    from techiaith.g2p.bangor_g2p import BangorG2P

    so = REPO / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
    if not so.exists():
        import pytest
        pytest.skip("libcy_phonemize.so not built (make -C techiaith/g2p/c libcy_phonemize.so)")
    lib = ctypes.CDLL(str(so))
    lib.cyp_create.restype = ctypes.c_void_p
    lib.cyp_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    i32 = ctypes.POINTER(ctypes.c_int32)
    lib.cyp_letter_tokens.argtypes = [ctypes.c_void_p, ctypes.c_char_p, i32, ctypes.c_int]
    lib.cyp_letter_tokens.restype = ctypes.c_int

    g = BangorG2P(english_mode="native")
    idm = g.id_map
    p = lib.cyp_create(str(REPO / "techiaith" / "g2p").encode(), b"native")
    assert p, "cyp_create failed"
    buf = (ctypes.c_int32 * 4096)()

    nd = [cp for cp in range(0x110000) if unicodedata.category(chr(cp)) == "Nd"]
    blocks = nd[::10]                      # one block start per Nd block
    assert any(cp >= 0x10000 for cp in blocks), "no supplementary blocks — table looks wrong"

    bad = []
    for start in blocks:
        for value in (0, 7):               # first and a middle digit of each block
            word = f"b{chr(start + value)}c"
            n = lib.cyp_letter_tokens(p, word.encode(), buf, 4096)
            got = None if n < 0 else list(buf[:n])
            want = [idm[t][0] for t in g.letter_tokens(word)]
            if got != want:
                bad.append((hex(start + value), want, got))
                if len(bad) > 8:
                    break
    assert not bad, (
        f"cyp_letter_tokens disagrees with the Python reference on "
        f"{len(bad)}+ Nd digits (Unicode {unicodedata.unidata_version}): {bad}"
    )


# --- C parity for the 2026-07-27 language decisions -------------------------------
# The C port ships on-device and must reproduce these byte for byte, but the generated
# corpora under techiaith/g2p/c/ cannot reach them: not one row of golden.tsv,
# bilingual_golden_*.tsv or spell_golden.tsv contains a hyphen inside a word, and
# spell_golden.tsv has no vowel-only input. Without the two tests below, the hyphen rule
# and the plain-vowel spell-out fallback would have ZERO C coverage -- a C port that
# reimplemented either one wrongly would ship silently. Drive the library directly
# against live Python instead, in both english modes.


def _c_lib():
    """The built shared library with the entry points these tests call, or skip."""
    import ctypes
    so = REPO / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
    if not so.exists():
        import pytest
        pytest.skip("libcy_phonemize.so not built (make -C techiaith/g2p/c libcy_phonemize.so)")
    lib = ctypes.CDLL(str(so))
    lib.cyp_create.restype = ctypes.c_void_p
    lib.cyp_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    i32 = ctypes.POINTER(ctypes.c_int32)
    lib.cyp_text_to_ids.argtypes = [ctypes.c_void_p, ctypes.c_char_p, i32, ctypes.c_int]
    lib.cyp_text_to_ids.restype = ctypes.c_int
    lib.cyp_letter_tokens.argtypes = [ctypes.c_void_p, ctypes.c_char_p, i32, ctypes.c_int]
    lib.cyp_letter_tokens.restype = ctypes.c_int
    return lib


# Hyphen runs (keyboard echo), real compounds that must survive intact, every isolated
# vowel keystroke, and the same vowels as one-letter WORDS -- including next to a
# letterless core ("a $"), which is two words to Python's `words` list and must therefore
# NOT be read as a lone keystroke.
_C_DECISION_INPUTS = [
    "d-d-d", "b-a-ch", "a-b", "ll-dd-ch", "y-y", "â-e", "A-B-C", "d-d-d.", "(d-d-d)",
    "c-a-th!", "mae d-d-d yma", "a-b c-d",
    "gogledd-ddwyrain", "de-ddwyrain", "e-bost", "xy-a", "a-xy", "-a", "a-", "a--b",
    "co-op", "a-1", "1-a", "5-5", "-", "--",
    "a", "e", "i", "o", "u", "w", "y", "â", "k",
    "a ci", "ci a", "a $", "$ a", "a %", "a +", "a 5", "a a", "a.", "(a)", "a?", "a - b",
    "c, a, th", "a i o y", "mae hi'n mynd",
]


def test_c_agrees_with_python_on_hyphen_runs_and_solo_vowels():
    """cyp_text_to_ids must match the reference on Decision 1 and Decision 3 surfaces.

    Also asserts the two structural facts the decisions are ABOUT, so a C port (or a
    Python change) that agreed with itself while getting the rule wrong still fails: a
    hyphenated letter run must contain the comma pause token, and a real compound must
    contain none.
    """
    import ctypes
    from techiaith.g2p.bangor_g2p import BangorG2P

    lib = _c_lib()
    comma = None
    for mode in ("native", "accented"):
        g = BangorG2P(english_mode=mode)
        comma = g.id_map[","][0]
        p = lib.cyp_create(str(REPO / "techiaith" / "g2p").encode(), mode.encode())
        assert p, f"cyp_create failed for {mode}"
        buf = (ctypes.c_int32 * 8192)()
        bad = []
        for text in _C_DECISION_INPUTS:
            n = lib.cyp_text_to_ids(p, text.encode(), buf, 8192)
            got = None if n < 0 else list(buf[:n])
            want = g.text_to_ids(text)
            if got != want:
                bad.append((text, want, got))
        assert not bad, f"C/Python divergence in {mode} mode: {bad[:6]}"

    # ...and the rule itself, not merely agreement about it.
    g = BangorG2P(english_mode="native")
    assert comma in g.text_to_ids("d-d-d"), (
        "a hyphenated single-letter run must be comma-paced; the hyphen rule did not fire")
    assert comma not in g.text_to_ids("gogledd-ddwyrain"), (
        "the hyphen rule fired on a real compound; the lexicon key has been split")


def test_c_spell_out_uses_the_semicolon_pause_and_letter_names():
    """cyp_letter_tokens must match the reference, including on vowel-only inputs.

    spell_golden.tsv has no vowel-only row -- and no row containing i, o or w at all -- so
    the inputs here are the only cover for VSPELLED. They also pin that the spell-out path
    does NOT reach the isolated-keystroke table: the two encode separate ear decisions and
    a change that collapsed them would still look like "vowel names" from the outside.
    """
    import ctypes
    from techiaith.g2p.bangor_g2p import BangorG2P, WORD_SEP, _CY_VOWEL_SOLO, _CY_VOWEL_SPELLED

    words = ["bach", "llan", "bt", "abc", "cymru", "aeiouwy", "a", "e", "i", "o", "u",
             "w", "y", "â", "d-d-d", "b-a-ch", "ll", "s42c", "", "  a  ", "A-B"]
    lib = _c_lib()
    for mode in ("native", "accented"):
        g = BangorG2P(english_mode=mode)
        idm = g.id_map
        p = lib.cyp_create(str(REPO / "techiaith" / "g2p").encode(), mode.encode())
        assert p, f"cyp_create failed for {mode}"
        buf = (ctypes.c_int32 * 8192)()
        bad = []
        for w in words:
            n = lib.cyp_letter_tokens(p, w.encode(), buf, 8192)
            got = None if n < 0 else list(buf[:n])
            want = [idm[t][0] for t in g.letter_tokens(w)]
            if got != want:
                bad.append((w, want, got))
        assert not bad, f"cyp_letter_tokens diverged in {mode} mode: {bad[:6]}"

    # ...and the two properties themselves, so agreement alone cannot carry the test.
    g = BangorG2P(english_mode="native")
    assert g.letter_tokens("bt").count(";") == 1
    assert "," not in g.letter_tokens("bt"), "spell-out still uses the old comma pause"
    assert WORD_SEP not in g.letter_tokens("bt")
    # "o" is where the two tables differ most: a triple hold alone, single-long in a run.
    # Spelling a word with an o must use the run form, never the keystroke form.
    solo_o, spelled = list(_CY_VOWEL_SOLO["o"]), g.letter_tokens("bore")
    assert solo_o != list(_CY_VOWEL_SPELLED["o"]), "the two vowel tables have collapsed"
    assert not any(spelled[i:i + len(solo_o)] == solo_o for i in range(len(spelled))), (
        "spell-out leaked the isolated-keystroke vowel name into 'bore'")
    from techiaith.g2p.bangor_g2p import _CY_LETTER_NAMES
    assert spelled == (
        list(_CY_LETTER_NAMES["b"]) + [";"] + list(_CY_VOWEL_SPELLED["o"]) + [";"]
        + list(_CY_LETTER_NAMES["r"]) + [";"] + list(_CY_VOWEL_SPELLED["e"])), (
        f"'bore' spelled out is not b;o;r;e by name: {spelled}")


# --- interpreter provenance -------------------------------------------------------
# letter_tokens' character tests (str.isdecimal / str.isalpha) and the C port's matching
# Nd table are Unicode-VERSION-dependent, so "the C port reproduces the Python reference
# byte for byte" says nothing useful unless the corpora, the table and the test all come
# from one interpreter. Three are in play here (techiaith/g2p/c/README.md lists them,
# including the 3.10 / Unicode 13.0.0 container that actually serves users). They agree
# today, which is exactly why this is worth pinning now rather than after it bites.

GENERATOR_ENV = REPO / "techiaith" / "g2p" / "c" / "generator_env.txt"


def _generator_env():
    env = {}
    for line in GENERATOR_ENV.read_text(encoding="utf-8").splitlines():
        if line.startswith("#") or "\t" not in line:
            continue
        k, v = line.split("\t", 1)
        env[k] = v
    return env


def test_generated_data_matches_the_declared_canonical_interpreter():
    """The corpora must match the interpreter the REPO declares, not the one running pytest.

    The previous form of this assertion compared generator_env.txt against
    unicodedata.unidata_version of the running interpreter, which made it impossible to run the
    suite on any interpreter but the generator -- so a CI matrix across the supported range
    could never be green. What actually matters is that the committed artifacts were produced
    under the one interpreter the repo names as canonical.
    """
    from techiaith.g2p.canonical import CANONICAL_PYTHON, CANONICAL_UNICODE
    env = _generator_env()
    assert env.get("unicodedata_version") == CANONICAL_UNICODE, (
        f"corpora were generated under Unicode {env.get('unicodedata_version')} but "
        f"canonical.py declares {CANONICAL_UNICODE}. Regenerate with "
        f"scripts/emit_c_data.py under Python {CANONICAL_PYTHON}."
    )
    assert env.get("python_version", "").startswith(CANONICAL_PYTHON + "."), (
        f"corpora were generated under Python {env.get('python_version')} but canonical.py "
        f"declares {CANONICAL_PYTHON}.x"
    )


def test_nd_table_declares_the_same_unicode_version_as_the_corpora():
    """The C Nd table records its own Unicode version; it must match the corpora's.

    The table is compiled into cy_normalize.c rather than loaded, so it is the one
    generated artifact that cannot be regenerated by running emit_c_data.py -- which is
    precisely how it could be left behind at an older Unicode version while the corpora
    moved on.
    """
    import re
    src = (REPO / "techiaith" / "g2p" / "c" / "cy_normalize.c").read_text(encoding="utf-8")
    m = re.search(r"ND_TABLE_UNICODE_VERSION\s*=\s*([0-9]+\.[0-9]+\.[0-9]+)", src)
    assert m, "cy_normalize.c no longer declares ND_TABLE_UNICODE_VERSION next to ND_BLOCK"
    declared = m.group(1)
    recorded = _generator_env().get("unicodedata_version")
    assert declared == recorded, (
        f"the C Nd table declares Unicode {declared} but the corpora were generated under "
        f"Unicode {recorded}; regenerate both under one interpreter "
        f"(see techiaith/g2p/c/README.md)"
    )


# Nasal mutation before blynedd/blwydd (piper-lleol issue #1). Invisible to `make check`:
# no row of any parity corpus contains "<digits> blynedd", so all 1890 normalize rows stay
# green whether or not the C port implements the rule at all -- which is exactly the state
# this test was written to catch. Mutating away pass_blynedd's registration in
# cyp_normalize leaves make check at 1890/1890 and fails only here.
_C_BLYNEDD_INPUTS = [
    # Confirmed row, both nouns.
    "10 blynedd", "10 blwydd oed",
    # The rest of the table: nasal, soft, and unmutated numerals.
    "1 blynedd", "1 blwydd oed", "2 blynedd", "3 blynedd", "4 blynedd", "5 blynedd",
    "6 blynedd", "7 blynedd", "8 blynedd", "9 blynedd", "15 blynedd", "20 blynedd",
    "50 blynedd", "100 blynedd",
    # Off-table values take the nasal with a decimal numeral; 2/3/4/6 stay unmutated.
    "37 blynedd", "1000 blynedd", "2 blynedd", "3 blynedd", "4 blynedd", "6 blynedd",
    # Already-mutated input still gets its digits expanded correctly.
    "10 mlynedd", "10 flynedd",
    # the non-compound 11+ band, which no corpus row reaches
    "12 blynedd", "18 blynedd", "40 blynedd", "60 blynedd", "80 blynedd",
    "18 blwydd oed", "11 blynedd", "25 blynedd",
    # Boundary cases: "blwyddyn" is a longer word (trailing \b must reject the match),
    # the space is required, and a trailing comma inside the digit run is still a match.
    "10 blwyddyn", "10blynedd", "10, blynedd", "0010 blynedd",
    # In a sentence, and alongside the passes that share the digit surface.
    "mae 10 blynedd o brofiad ganddi", "yn 10 blwydd oed",
    "10 km", "25", "10:30", "£10m", "10%", "1/2",
]


def test_c_agrees_with_python_on_blynedd_mutation():
    """cyp_text_to_ids must match the reference, AND produce the mutation it is about.

    The equality half alone would pass if both implementations were wrong in the same
    way, so the structural half pins the three behaviours the rule actually claims:
    nasal mutation with the "deng" form on the confirmed row, an unmutated fallback for
    values off the table, and no match at all across a word boundary.
    """
    import ctypes
    from techiaith.g2p.welsh_normalize import WelshNormalizer
    from techiaith.g2p.bangor_g2p import BangorG2P

    g = BangorG2P(english_mode="native")
    lib = _c_lib()
    p = lib.cyp_create(str(REPO / "techiaith" / "g2p").encode(), b"native")
    assert p, "cyp_create failed"
    buf = (ctypes.c_int32 * 4096)()

    bad = []
    for text in _C_BLYNEDD_INPUTS:
        n = lib.cyp_text_to_ids(ctypes.c_void_p(p), text.encode(), buf, 4096)
        if list(buf[:n]) != g.text_to_ids(text):
            bad.append(text)
    assert not bad, f"C/Python divergence on blynedd mutation: {bad}"

    norm = WelshNormalizer().normalize
    # The NON-COMPOUND 11+ values fell between BTC's two rules and got neither: the
    # counted-noun rule sends only COMPOUND numerals to "o flynyddoedd", and the nasal rule
    # was applied only to the values _BLYNEDD_NUM lists. So 12/18/40/60/80 read "deuddeg
    # blynedd", "deugain blynedd" and so on -- no plural and no mutation. No corpus row
    # contains any of them, so make check was 8/8 throughout.
    # Under the DECIMAL register the numerals are decimal, but the nasal rule still
    # applies -- BTC states it over the numeral's VALUE, and none of these is 2/3/4/6.
    assert norm("12 blynedd") == "un deg dau mlynedd"
    assert norm("18 blynedd") == "un deg wyth mlynedd"
    assert norm("40 blynedd") == "pedwar deg mlynedd"
    assert norm("11 blynedd") == "un deg un mlynedd"
    assert norm("25 blynedd") == "dau ddeg pump mlynedd"
    assert norm("18 blwydd oed") == "un deg wyth mlwydd oed"
    # The 2/3/4/6 exceptions, unchanged.
    assert norm("3 blynedd") == "tair blynedd"
    assert norm("6 blynedd") == "chwe blynedd"
    # FLAGGED for native-speaker review in §6: BTC frames the exception over the numeral, so 12 mutates
    # -- but under decimal the word touching "mlynedd" is "dau", which IS one of the four.
    # BTC never had to answer this because it reads figures vigesimally, where 12 is the
    # single word "deuddeg". Current behaviour follows the value, not the adjacent word.

    # Nasal, with deg -> deng. This is the row confirmed verbatim.
    assert norm("10 blynedd") == "deng mlynedd"
    assert norm("10 blwydd oed") == "deng mlwydd oed"
    # Soft after the feminine "dwy", and the singular noun after "un".
    assert norm("2 blynedd") == "dwy flynedd"
    assert norm("1 blynedd") == "un flwyddyn"
    # Unmutated after numerals that do not trigger it.
    assert norm("3 blynedd") == "tair blynedd"
    # Off the table: plain cardinal, noun left alone -- never confidently wrong. The
    # cardinal itself is now vigesimal (BTC), which is why 37 reads this way; the point
    # of the assertion is the UNMUTATED "blynedd", not the numeral's register.
    # 37 >= 11 with a compound numeral, so BTC's counted-noun branch sends the noun to
    # the nasal, with the decimal numeral. The original point of this assertion -- that
    # the fallback never invents a form for a value the table does not cover -- is now
    # carried by the 2/3/4/6 cases above, which are the only values it leaves unmutated.
    assert norm("37 blynedd") == "tri deg saith mlynedd"
    # "blwyddyn" is a different, longer word: the trailing \b must refuse the match, so
    # the numeral stays "deg" and the noun is untouched.
    assert norm("10 blwyddyn") == "deg blwyddyn"
    # The idiom must not leak into the neighbouring numeric passes.
    assert norm("10 km") == "deg cilomedr"
    assert norm("25") == "dau ddeg pump"        # decimal cardinal register


# Spelled-vowel letter names (2026-07-27). spell_golden.tsv cannot see most of this: its
# 15 words contain no 'i', no 'o' and no 'w' at all, so the single-long i/o change and the
# "double-you" fix -- the actual defect -- are invisible to `make check`. Its row count is
# pinned by N_SPELL_ROWS in test_ssml.c, so the coverage lives here instead.
_C_SPELL_INPUTS = [
    "kilo", "llaw", "cwm", "dyn", "bach", "wedi", "blwyddyn", "Cymraeg", "ysgol",
    "bore", "iawn", "gwaith", "tŷ", "dŵr", "diolch", "ffordd", "rhad", "angen",
    "a", "e", "i", "o", "u", "w", "y", "â", "ŷ",
]
# The English letter name for w, which a spelled Welsh word must never contain.
_DOUBLE_YOU = ["d", "@", "|", "b", "@", "l", "|", "j", "uu"]


def test_c_agrees_with_python_on_spelled_vowel_names():
    """Spelled vowels take their letter names, and the isolated keystroke does not change.

    Two tables are in play on purpose: _CY_VOWEL_SPELLED for a letter inside a run,
    _CY_VOWEL_SOLO for a letter alone. The owner auditioned those contexts separately and
    preferred different lengths, so a change that collapsed them into one would be a
    regression even though both tables are "vowel names" -- hence the explicit assertions
    on both paths below.
    """
    import ctypes
    from techiaith.g2p.bangor_g2p import BangorG2P, _CY_VOWEL_SOLO, _CY_VOWEL_SPELLED

    g = BangorG2P(english_mode="native")
    lib = _c_lib()
    p = lib.cyp_create(str(REPO / "techiaith" / "g2p").encode(), b"native")
    assert p, "cyp_create failed"
    buf = (ctypes.c_int32 * 4096)()

    # cyp_letter_tokens returns RAW ids -- no bos/pad/eos interleave -- so compare against
    # the id_map directly, not phonemes_to_ids (which does interleave).
    idm = g.id_map
    bad = []
    for w in _C_SPELL_INPUTS:
        n = lib.cyp_letter_tokens(ctypes.c_void_p(p), w.encode(), buf, 4096)
        got = None if n < 0 else list(buf[:n])
        want = [idm[t][0] for t in g.letter_tokens(w)]
        if got != want:
            bad.append((w, want, got))
    assert not bad, f"C/Python divergence on spelled vowels: {bad[:4]}"

    # --- the w defect: an English three-syllable letter name inside a Welsh spelling ---
    for w in ("llaw", "cwm", "wedi", "gwaith", "blwyddyn", "iawn"):
        toks = g.letter_tokens(w)
        assert _DOUBLE_YOU != toks[:len(_DOUBLE_YOU)], w
        joined = " ".join(toks)
        assert " ".join(_DOUBLE_YOU) not in joined, (
            f"{w!r} still spells w with the English \"double-you\": {joined}")
        assert "uu" in toks, f"{w!r} lost the Welsh w"

    # --- literal expectations, so a coordinated C+Python change cannot slip through ---
    assert g.letter_tokens("llaw") == ["ˈ", "e", "lh", ";", "ˈ", "aa", "aa", ";", "ˈ", "uu"]
    assert g.letter_tokens("kilo") == ["ˈ", "k", "ee", ";", "ˈ", "ii", ";",
                                       "ˈ", "e", "l", ";", "ˈ", "oo"]
    assert g.letter_tokens("dyn") == ["ˈ", "d", "ii", ";", "ˈ", "yy", ";", "ˈ", "e", "n"]

    # Separator is the semicolon, and no spelled word carries the old comma.
    for w in ("bach", "kilo", "Cymraeg"):
        toks = g.letter_tokens(w)
        assert ";" in toks and "," not in toks, f"{w!r}: {toks}"

    # y is off the schwa entirely -- that phone is what picked up the r.
    assert "@" not in g.letter_tokens("dyn")
    assert _CY_VOWEL_SPELLED["y"] == ["ˈ", "yy"]

    # --- the isolated keystroke keeps _CY_VOWEL_SOLO, including o's triple hold ---
    for v in "aeiouwy":
        assert g.text_to_ids(v) == g.phonemes_to_ids(list(_CY_VOWEL_SOLO[v])), (
            f"isolated {v!r} no longer uses _CY_VOWEL_SOLO")
    assert _CY_VOWEL_SOLO["o"] == ["ˈ", "oo", "oo", "oo"], "isolated o lost its triple"
    assert _CY_VOWEL_SPELLED["o"] == ["ˈ", "oo"], "spelled o lost the single-long form"
    assert _CY_VOWEL_SOLO["o"] != _CY_VOWEL_SPELLED["o"], (
        "the two vowel tables have been collapsed; they encode two separate ear decisions")
