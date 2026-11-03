"""Word highlighting (CHANGELOG Unreleased): where each segment and each spoken word came from in
the source text -- BangorG2P.segment_spans / word_marks / word_starts and their C mirrors
cyp_segment_spans / cyp_word_marks / cyp_word_starts. Python offsets are code points, C's UTF-8
bytes. word_marks_golden.tsv (scripts/emit_c_data.py) pins both to the same answer."""
import sys
from pathlib import Path

import pytest

from techiaith.g2p.bangor_g2p import BangorG2P, Segment, WordMark

REPO = Path(__file__).resolve().parent.parent
C_DIR = REPO / "techiaith" / "g2p" / "c"
GOLDEN = C_DIR / "word_marks_golden.tsv"
N_GOLDEN_ROWS = 245                      # test_word_marks.c N_WORD_MARK_ROWS; update together


@pytest.fixture(scope="module")
def g2p():
    return BangorG2P(english_mode="native")


def _rows():
    rows = []
    for line in GOLDEN.read_text(encoding="utf-8").split("\n"):    # not splitlines(): U+2028 etc.
        if "\t" in line:
            text, lang, spans, marks, starts = line.split("\t")
            rows.append((text.replace("\\n", "\n"), None if lang == "-" else lang, spans, marks, starts))
    assert len(rows) == N_GOLDEN_ROWS, f"expected {N_GOLDEN_ROWS} golden rows, got {len(rows)}"
    return rows


def _render(text, spans, marks, starts):
    """The golden's three columns from code-point spans, as scripts/emit_c_data.py writes them."""
    b = lambda i: len(text[:i].encode("utf-8"))
    return ("|".join(f"{b(a)}:{b(e)}" for a, e in spans),
            "|".join(f"{m[0]}:{m[1]}:{b(m[2])}:{b(m[3])}" for m in marks),
            "|".join(" ".join(map(str, s)) for s in starts))


def test_api_shape():
    assert WordMark._fields == ("seg", "word", "start", "end")
    # Segment is unchanged: the API and the apps unpack it, and the spans are a separate call
    assert Segment._fields == ("text", "tokens", "ids", "boundary", "number_lang", "phone_lang")


def test_segment_spans_are_the_trimmed_source_of_each_segment(g2p):
    text = "  Heading\n\nFirst sentence. Second one.  "
    assert g2p.segment_spans(text) == [(2, 9), (11, 26), (27, 38)]
    assert [text[a:e] for a, e in g2p.segment_spans(text)] == ["Heading", "First sentence.", "Second one."]
    assert [s.text for s in g2p.segments(text)][0] == "heading."     # the "." is not in the source span
    assert g2p.segment_spans("") == [] and g2p.segment_spans(" \n\t ") == []
    for text in ("Settings\nGeneral\nAbout phone", "Dr. Jones. Mae Dr. Jones yma.", "1 o 1. 1 of 1", "...",
                 "Live Recognition\nUsing on-device intelligence, your iPhone can detect people.\n"
                 "Triple-tap with four fingers to start Live Recognition or use the Live\nRecognition Rotor."):
        for lang in (None, "cy", "en"):
            assert len(g2p.segment_spans(text, lang=lang)) == len(g2p.segments(text, lang=lang)), (text, lang)


def test_word_marks_skip_what_makes_no_sound_and_jump_over_expansions(g2p):
    text = "Costiodd y llyfr £9.50 ar 12 Mawrth 2026. Diolch 😀!"
    marks = g2p.word_marks(text)
    assert [(m.seg, m.word, text[m.start:m.end]) for m in marks] == [
        (0, 0, "Costiodd"), (0, 1, "y"), (0, 2, "llyfr"), (0, 3, "£9.50"), (0, 8, "ar"), (0, 9, "12"),
        (0, 12, "Mawrth"), (0, 13, "2026."), (1, 0, "Diolch"), (1, 1, "😀!")]
    # a bullet, a lone dash: no spoken word, no mark
    assert [(text[m.start:m.end]) for text in ["- item"] for m in g2p.word_marks(text)] == ["item"]
    text = "Tudalen 1 o 3 • Page 1 of 3"
    assert "•" not in [text[m.start:m.end] for m in g2p.word_marks(text)]
    # no-break and thin spaces separate source words, as str.split() does
    text = "Bore da a hwyl"
    assert [text[m.start:m.end] for m in g2p.word_marks(text)] == ["Bore", "da", "a", "hwyl"]
    assert g2p.word_marks("") == []


def test_word_marks_invariants(g2p):
    """Over the golden corpus, every lang: marks are strictly increasing in `word` within a
    segment, never reach its phone-word count, sit inside its span on a whitespace-free word, and
    the first mark of a segment with a spoken word is word 0."""
    for text, lang, *_ in _rows():
        segs = g2p.segments(text, lang=lang)
        spans = g2p.segment_spans(text, lang=lang)
        marks = g2p.word_marks(text, lang=lang)
        for si, (seg, (a, e)) in enumerate(zip(segs, spans)):
            mine = [m for m in marks if m.seg == si]
            total = len(g2p.word_starts(seg.ids))
            assert all(x.word < y.word for x, y in zip(mine, mine[1:])), text
            assert all(0 <= m.word < total for m in mine), text
            assert all(a <= m.start < m.end <= e and not any(c.isspace() for c in text[m.start:m.end]) for m in mine), text
            if mine:
                assert mine[0].word == 0, text
        assert sorted(m.seg for m in marks) == [m.seg for m in marks], text


def test_long_segments_count_in_a_window(g2p, monkeypatch):
    """A segment's count runs in a window from its 32nd word on (bangor_g2p._WM_WINDOW, C
    WM_WINDOW), so word_marks is linear in the text: the whole prefix made one 4 KB segment of
    lowercase-start prose cost 465 ms in C. The window gives the whole-prefix marks on every long
    golden row (and on every long text measured), and never phonemises more than 2H words."""
    from techiaith.g2p import bangor_g2p
    H = bangor_g2p._WM_WINDOW
    long_rows = [(t, lang) for t, lang, *_ in _rows()
                 if any(len(t[a:e].split()) >= 3 * H for a, e in g2p.segment_spans(t, lang=lang))]
    assert len(long_rows) >= 4
    for text, lang in long_rows:
        windowed = g2p.word_marks(text, lang=lang)
        monkeypatch.setattr(bangor_g2p, "_WM_WINDOW", 10 ** 9)        # the whole prefix
        assert g2p.word_marks(text, lang=lang) == windowed, (text, lang)
        monkeypatch.setattr(bangor_g2p, "_WM_WINDOW", H)
    seen = []
    real = g2p.text_to_ids
    monkeypatch.setattr(g2p, "text_to_ids", lambda t, **kw: seen.append(len(t.split())) or real(t, **kw))
    text = " ".join(["mae'r llais yn darllen y testun yn uchel i chi."] * 25)   # one segment, 250 words
    assert len(g2p.segment_spans(text)) == 1
    assert len(g2p.word_marks(text)) == 250
    assert max(seen) <= 2 * H and len(seen) <= 250 + 250 // H


def test_word_starts_layout(g2p):
    assert g2p.word_starts([1, 0, 2]) == []                          # empty segment
    assert g2p.word_starts([1, 0, 20, 0, 3, 0, 21, 0, 2]) == [1, 5]   # PAD after BOS, PAD after WORD_SEP
    assert g2p.word_starts([1, 0, 20, 0, 3, 2]) == [1]                # a piece cut just after a WORD_SEP
    for seg in g2p.segments("Mae 3 o'r plant.\n\nShow 3 of 4."):
        starts = g2p.word_starts(seg.ids)
        assert len(starts) == 1 + seg.tokens.count(" ")
        assert all(seg.ids[i - 1] == 3 for i in starts[1:])


def test_invalid_lang_rejected(g2p):
    for call in (g2p.segment_spans, g2p.word_marks):
        with pytest.raises(ValueError):
            call("Bore da", lang="fr")


def test_golden_is_current(g2p):
    """The committed word_marks_golden.tsv is what this Python produces: a Python-side change
    that moves a mark must regenerate the golden (and so be seen by the C suite)."""
    for text, lang, spans, marks, starts in _rows():
        got = _render(text, g2p.segment_spans(text, lang=lang), g2p.word_marks(text, lang=lang),
                      [g2p.word_starts(s.ids) for s in g2p.segments(text, lang=lang)])
        assert got == (spans, marks, starts), (text, lang)


def _corpora():
    """The committed C corpora's inputs: segments, word marks, bilingual, golden, lang."""
    texts = [r[0] for r in _rows()]
    for name in ("segments_golden.tsv", "bilingual_golden_native.tsv", "golden.tsv", "lang_golden.tsv"):
        for line in (C_DIR / name).read_text(encoding="utf-8").split("\n"):
            if "\t" in line:
                texts.append(line.split("\t")[0].replace("\\n", "\n"))
    return list(dict.fromkeys(texts))


def test_c_matches_python_on_the_corpora(g2p):
    """C-vs-Python cross-check over every committed corpus input, AUTO and both forced languages."""
    so = C_DIR / "libcy_phonemize.so"
    if not so.exists():
        pytest.skip("libcy_phonemize.so not built (make -C techiaith/g2p/c libcy_phonemize.so)")
    sys.path.insert(0, str(REPO / "bindings" / "python"))
    try:
        from cy_phonemize import CyPhonemizer
    finally:
        sys.path.pop(0)
    c = CyPhonemizer(english_mode="native", lib_path=so)
    texts = _corpora()
    assert len(texts) > 200                  # 260 distinct inputs today; an emptied corpus fails here
    checked = 0
    for text in texts:
        for lang in (None, "cy", "en"):
            b = lambda i: len(text[:i].encode("utf-8"))
            assert c.segment_spans(text, lang=lang) == [(b(a), b(e)) for a, e in g2p.segment_spans(text, lang=lang)], (text, lang)
            assert c.word_marks(text, lang=lang) == [(m.seg, m.word, b(m.start), b(m.end))
                                                     for m in g2p.word_marks(text, lang=lang)], (text, lang)
            for seg in g2p.segments(text, lang=lang):
                assert c.word_starts(seg.ids) == g2p.word_starts(seg.ids), (text, lang)
            checked += 1
    assert checked == 3 * len(texts)


def test_binding_spans_at_the_segment_cap(g2p):
    """A text has at most 2,049 segments (2,048 boundaries plus the tail). The binding sized its
    span arrays at 2,048, so it raised where Python returns 2,049 spans; consumers must size
    max_segs at 2,049 for cyp_segments and cyp_segment_spans alike (cy_phonemize.h)."""
    so = C_DIR / "libcy_phonemize.so"
    if not so.exists():
        pytest.skip("libcy_phonemize.so not built (make -C techiaith/g2p/c libcy_phonemize.so)")
    sys.path.insert(0, str(REPO / "bindings" / "python"))
    try:
        from cy_phonemize import CyPhonemizer
    finally:
        sys.path.pop(0)
    c = CyPhonemizer(english_mode="native", lib_path=so)
    for n in (2048, 2049, 2100):
        text = "a\n" * n
        b = lambda i: len(text[:i].encode("utf-8"))
        assert c.segment_spans(text) == [(b(x), b(y)) for x, y in g2p.segment_spans(text)], n
