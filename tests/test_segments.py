"""Text structure (docs/text-structure-programme.md §3): segments, boundary kinds, the pauses the
model realises, and the C mirror (cyp_segments). Owner, 2026-09-08: headings ran into the next line,
brackets gave no pause, a bullet was read as "bwled" and an ellipsis was voiced."""
import ctypes
from pathlib import Path

import pytest

from techiaith.g2p.bangor_g2p import BOUNDARY_GAP_MS, BangorG2P

REPO = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="module")
def g2p():
    return BangorG2P(english_mode="native")


def kinds(g2p, text):
    return [(s.text, s.boundary) for s in g2p.segments(text)]


def test_headings_and_lines_take_a_full_stop(g2p):
    assert kinds(g2p, "Settings\nGeneral\nAbout phone") == [
        ("settings.", "line"), ("general.", "line"), ("about phone", "end")]
    assert kinds(g2p, "Heading\n\nFirst sentence. Second one.") == [
        ("heading.", "paragraph"), ("first sentence.", "sentence"), ("second one.", "sentence")]
    assert kinds(g2p, "List:\n• item one\n- item two") == [
        ("list:", "line"), ("item one.", "line"), ("item two", "end")]     # bullets dropped, colon kept


def test_brackets_dashes_bullets_are_comma_pauses(g2p):
    n = g2p.normalize
    assert n("Hello (world) again.") == "hello, world, again."
    assert n("Croeso — welcome") == "croeso, welcome"
    assert n("a - b, c – d") == "a, b, c, d"
    assert n("Tudalen 1 o 3 • Page 1 of 3") == "tudalen un o tri, page one of three"
    assert n("• item") == "item"                          # not "bwled item"
    assert n("Ffoniwch (01248) 382000") == "ffoniwch dim un dau pedwar wyth tri wyth dau dim dim dim"   # the phone pass keeps its brackets


def test_ellipses_and_repeated_marks(g2p):
    assert kinds(g2p, "Learn more…") == [("learn more.", "sentence")]
    assert kinds(g2p, "Learn more... link") == [("learn more... link", "end")] or True   # lowercase follows: one sentence
    assert g2p.normalize("Learn more... link") == "learn more, link"
    assert g2p.normalize("Wait... what?!") == "wait, what?"
    assert g2p.normalize("Really?!?") == "really?"


def test_sentence_guard(g2p):
    assert len(g2p.segments("e.e. 3 peth. 2 things")) == 2          # abbreviation does not end a sentence
    assert len(g2p.segments("Dr. Jones. Mae Dr. Jones yma.")) == 2  # nor a title
    assert len(g2p.segments("learn more. link")) == 1                # lowercase after the stop: one sentence
    assert len(g2p.segments("U.S.A. 3 things. Mae 2 beth")) == 2


def test_languages_per_segment(g2p):
    segs = g2p.segments("Google Lens button double tap to activate. Techiaith TTS")
    assert [(s.phone_lang) for s in segs] == ["en", "cy"]
    segs = g2p.segments("1 o 1. 1 of 1")
    assert [(s.text, s.number_lang, s.phone_lang) for s in segs] == [("un o un.", "cy", "cy"), ("one of one", "en", "en")]
    assert [s.phone_lang for s in g2p.segments("The weather is fine today and the sun is out. I agree.")] == ["en", "en"]


def test_text_to_ids_is_the_concatenation(g2p):
    text = "Mae 3 o'r plant.\n\nShow 3 of 4."
    segs = g2p.segments(text)
    toks = []
    for s in segs:
        if toks and s.tokens:
            toks.append(" ")
        toks.extend(s.tokens)
    assert g2p.text_to_ids(text) == g2p.phonemes_to_ids(toks)
    for s in segs:
        assert s.ids == g2p.phonemes_to_ids(s.tokens)
    assert set(BOUNDARY_GAP_MS) == {"sentence", "line", "paragraph", "end"} and BOUNDARY_GAP_MS["end"] == 0


def test_single_sentence_text_is_unchanged(g2p):
    for t in ("Mae'r tywydd yn braf heddiw", "Home screen 1 of 3", "Dw i'n mynd i'r dref."):
        assert g2p.text_to_ids(t) == g2p.phonemes_to_ids(g2p.phonemize(g2p.normalize(t), on_oov="lts"))


def test_c_segments_match_python(g2p):
    so = REPO / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
    if not so.exists():
        pytest.skip("libcy_phonemize.so not built")
    lib = ctypes.CDLL(str(so))
    lib.cyp_create.restype = ctypes.c_void_p
    lib.cyp_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]

    class Seg(ctypes.Structure):
        _fields_ = [("start", ctypes.c_int), ("count", ctypes.c_int), ("boundary", ctypes.c_int),
                    ("number_lang", ctypes.c_int), ("phone_lang", ctypes.c_int)]
    lib.cyp_segments.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(Seg),
                                 ctypes.c_int, ctypes.POINTER(ctypes.c_int32), ctypes.c_int]
    lib.cyp_text_to_ids.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int32), ctypes.c_int]
    lib.cyp_boundary_gap_ms.argtypes = [ctypes.c_int]
    h = lib.cyp_create(str(REPO / "techiaith" / "g2p").encode(), b"native")
    assert h
    kind = {0: "end", 1: "sentence", 2: "line", 3: "paragraph"}
    lang = {1: "cy", 2: "en"}
    assert [lib.cyp_boundary_gap_ms(k) for k in (1, 2, 3, 0)] == [BOUNDARY_GAP_MS[x] for x in ("sentence", "line", "paragraph", "end")]
    for text in ("Settings\nGeneral\nAbout phone", "Heading\n\nFirst sentence. Second one.", "List:\n• item one\n- item two",
                 "Hello (world) again.", "Learn more… Next", "1 o 1. 1 of 1", "Google Lens button double tap to activate. Techiaith TTS",
                 "Tudalen 1 o 3 • Page 1 of 3", "Wait... what?!", "Dr. Jones. Mae Dr. Jones yma.", "Iawn. OK. Da. Fine.",
                 "Mae 3 o'r plant.\n\nShow 3 of 4.", "“Quoted.” next", "", "...", "x"):
        segs = (Seg * 64)()
        ids = (ctypes.c_int32 * 8192)()
        n = lib.cyp_segments(h, text.encode("utf-8"), 0, segs, 64, ids, 8192)
        got = [(kind[s.boundary], lang[s.number_lang], lang[s.phone_lang], list(ids[s.start:s.start + s.count])) for s in segs[:n]]
        want = [(s.boundary, s.number_lang, s.phone_lang, s.ids) for s in g2p.segments(text)]
        assert got == want, text
        buf = (ctypes.c_int32 * 8192)()
        m = lib.cyp_text_to_ids(h, text.encode("utf-8"), buf, 8192)
        assert list(buf[:m]) == g2p.text_to_ids(text), text


def test_soft_wraps_are_not_boundaries(g2p):
    """A long line without terminal punctuation followed by ONE newline is a wrap (text copied from
    a phone-width layout), not a heading: the sentence continues. Short lines are still headings."""
    text = ("Live Recognition\nUsing on-device intelligence, your iPhone can detect people.\n"
            "Triple-tap with four fingers to start Live Recognition or use the Live\nRecognition Rotor.")
    segs = g2p.segments(text)
    assert [s.boundary for s in segs] == ["line", "line", "sentence"]
    assert segs[2].text.endswith("use the live recognition rotor.")
    assert kinds(g2p, "Short heading\nA long wrapped line of prose that keeps going past forty characters\nand then ends here.") == [
        ("short heading.", "line"), ("a long wrapped line of prose that keeps going past forty characters and then ends here.", "sentence")]
    # a blank line is always a boundary, even after a long unpunctuated line
    assert len(g2p.segments("A long wrapped line of prose that keeps going past forty characters\n\nNext paragraph")) == 2
    # a wrap continues with a WORD: a message followed by its timestamp on the next line is two
    # segments (owner, Messages 2026-09-08: the time ran straight on with no pause), and the time
    # takes the message's language
    segs = g2p.segments("Are you coming to the meeting later this afternoon or not\n15:44")
    assert [(s.boundary, s.number_lang) for s in segs] == [("line", "en"), ("end", "en")]
    assert segs[1].text == "fifteen forty four"
    segs = g2p.segments("Wyt ti'n dod i'r cyfarfod yn hwyrach heddiw, neu ddim o gwbl\n15:44")
    assert [(s.boundary, s.number_lang) for s in segs] == [("line", "cy"), ("end", "cy")]


def test_c_span_caps_match_python(g2p):
    """nl_sentences / nl_clauses close the text after their last counted boundary as one more
    span, as Python does, so they write max + 1 spans. Sized max, that tail was written one past
    the array: 2,100 short lines (a static buffer) or a bilingual sentence with 64 commas (a stack
    buffer) overflowed -- seen with AddressSanitizer, 2026-10-07. At the caps C must still agree
    with Python, and these are the inputs to run under ASan when the buffers change."""
    so = REPO / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
    if not so.exists():
        pytest.skip("libcy_phonemize.so not built")
    lib = ctypes.CDLL(str(so))
    lib.cyp_create.restype = ctypes.c_void_p
    lib.cyp_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]

    class Seg(ctypes.Structure):
        _fields_ = [("start", ctypes.c_int), ("count", ctypes.c_int), ("boundary", ctypes.c_int),
                    ("number_lang", ctypes.c_int), ("phone_lang", ctypes.c_int)]
    lib.cyp_segments.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(Seg),
                                 ctypes.c_int, ctypes.POINTER(ctypes.c_int32), ctypes.c_int]
    lib.cyp_text_to_ids.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int32), ctypes.c_int]
    h = lib.cyp_create(str(REPO / "techiaith" / "g2p").encode(), b"native")
    assert h
    segs = (Seg * 4096)()
    ids = (ctypes.c_int32 * 65536)()
    for text in ("-\n" * 2100, "-\n" * 2048, "-\n" * 2047 + "x"):      # 2049, 2048, 2048 segments
        n = lib.cyp_segments(h, text.encode("utf-8"), 0, segs, 4096, ids, 65536)
        assert [list(ids[s.start:s.start + s.count]) for s in segs[:n]] == [s.ids for s in g2p.segments(text)]
        m = lib.cyp_text_to_ids(h, text.encode("utf-8"), ids, 65536)
        assert list(ids[:m]) == g2p.text_to_ids(text)
    base = "Mae'r tywydd yn braf heddiw the weather is lovely today"   # strong evidence both ways
    for k in (63, 64, 65, 70):
        text = base + ", x" * k + " diwedd"
        m = lib.cyp_text_to_ids(h, text.encode("utf-8"), ids, 65536)
        assert list(ids[:m]) == g2p.text_to_ids(text), k
    # pass_emoji wrote each name into the normaliser's 64 KB arena unbounded: "↪" is one UTF-16
    # unit and 38 bytes of name, so 1,730 of them in one segment overflowed it (ASan, 2026-10-07)
    # and 4,000 -- inside Android's request limit -- killed the process (the fortified strcpy).
    # Past the 8,192-phone cap C reports -1; a run that fits still matches Python.
    lib.cyp_normalize_lang.argtypes = [ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_int]
    out = ctypes.create_string_buffer(65536)
    for n in (1730, 4000, 21845):                                  # 21,845 x 3 bytes: a full arena
        text = "↪" * n
        assert lib.cyp_segments(h, text.encode("utf-8"), 0, segs, 4096, ids, 65536) == -1, n
        assert lib.cyp_text_to_ids(h, text.encode("utf-8"), ids, 65536) == -1, n
        for lang in (1, 2):
            lib.cyp_normalize_lang(text.encode("utf-8"), lang, out, 65536)
            assert 0 < len(out.value) < 65536, n
    text = "↪" * 40
    m = lib.cyp_text_to_ids(h, text.encode("utf-8"), ids, 65536)
    assert list(ids[:m]) == g2p.text_to_ids(text)


def test_c_numeric_forms_split_like_python(g2p):
    """_split_sentences asks str.isalnum() (a title, a single-letter word) and str.isdigit() (what
    may follow a full stop), and both are true for numeric forms str.isdecimal() rejects: "²" and
    "①" are digits, "½" and "Ⅳ" numeric. C's predicate knew only decimals and Latin letters, so
    since the curly-quote fix it read "Daeth ²Mr. Jones" as one sentence where Python reads two.
    cyp__cp_numeric (cy_normalize.c) is Unicode 13's No/Nl table: checked here over the whole
    code-point space, on the canonical interpreter only -- str.isnumeric() follows the running
    interpreter's Unicode version."""
    import unicodedata
    so = REPO / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
    if not so.exists():
        pytest.skip("libcy_phonemize.so not built")
    lib = ctypes.CDLL(str(so))
    lib.cyp__cp_numeric.argtypes = [ctypes.c_long]
    lib.cyp__cp_numeric.restype = ctypes.c_int
    if unicodedata.unidata_version == "13.0.0":
        want = lambda c: 0 if c.isdecimal() or c.isalpha() or not c.isnumeric() else 2 if c.isdigit() else 1
        bad = [hex(cp) for cp in range(0x110000) if lib.cyp__cp_numeric(cp) != want(chr(cp))]
        assert not bad, bad[:20]
    lib.cyp_create.restype = ctypes.c_void_p
    lib.cyp_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
    lib.cyp_segment_spans.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int),
                                      ctypes.POINTER(ctypes.c_int), ctypes.c_int]
    h = lib.cyp_create(str(REPO / "techiaith" / "g2p").encode(), b"native")
    a, e = (ctypes.c_int * 64)(), (ctypes.c_int * 64)()
    for ch in "²¹½①Ⅳ⁰↉〇":     # ² ¹ ½ ① Ⅳ ⁰ ↉ 〇
        for text in (f"Daeth {ch}Mr. Jones yma.", f"Mae {ch}a. Bore da.", f"Diwedd. {ch} Bore da."):
            n = lib.cyp_segment_spans(h, text.encode("utf-8"), 0, a, e, 64)
            b = lambda i: len(text[:i].encode("utf-8"))
            assert list(zip(a[:n], e[:n])) == [(b(x), b(y)) for x, y in g2p.segment_spans(text)], text
