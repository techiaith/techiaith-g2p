/* libcy_phonemize — C ABI for the permissive Welsh (Bangor) phonemizer.
 *
 * Workstream P / P7, increment 1: dictionary lookup + interleaving. Reproduces the
 * Python reference (accented mode, dictionary-covered text) byte-for-byte — the
 * golden-parity contract, in C. OOV letter-to-sound, text normalization, and the
 * native English G2P are later C increments; today OOV words are skipped.
 *
 * The identical phoneme-id sequence must come out of this and the Python trainer
 * path (train == inference). See docs/PARITY.md.
 */
#ifndef CY_PHONEMIZE_H
#define CY_PHONEMIZE_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct CyPhonemizer CyPhonemizer;

/* core_dir = the techiaith/g2p directory (contains c/tokens.tsv, the
 * data/geiriadur-ynganu-bangor dictionaries, the native English lexicon, and
 * c/data_version.txt). english_mode = "native" (English phones 78-84) or
 * "accented" (English folded to Welsh; default) — match the model's
 * config.json phonemizer.english_mode. NULL on error. */
CyPhonemizer *cyp_create(const char *core_dir, const char *english_mode);
void cyp_destroy(CyPhonemizer *p);

/* Phonemize UTF-8 text into interleaved phoneme ids ([BOS]+[PAD,id]*+[PAD,EOS]).
 * Writes up to max_out ids into out; returns the id count, or -1 on overflow/error. */
int cyp_text_to_ids(CyPhonemizer *p, const char *utf8_text, int32_t *out, int max_out);

/* --- SSML token-level primitives (mirror bangor_g2p; see docs/PARITY.md) --------- */

/* Language codes for cyp_text_to_ids_lang. CYP_LANG_AUTO reproduces cyp_text_to_ids. */
enum { CYP_LANG_AUTO = 0, CYP_LANG_CY = 1, CYP_LANG_EN = 2 };

/* As cyp_text_to_ids, but with an explicit language for the whole utterance (SSML
 * <lang xml:lang="...">), overriding the automatic sentence-level routing. Mirrors
 * bangor_g2p.phonemize(..., lang=None|"cy"|"en"): CYP_LANG_AUTO is byte-for-byte the
 * pre-lang behaviour. Returns the id count, or -1 on overflow/bad lang. */
int cyp_text_to_ids_lang(CyPhonemizer *p, const char *utf8_text, int lang,
                         int32_t *out, int max_out);

/* Author-supplied pronunciation (SSML <phoneme ph="...">) -> phone-token ids, NOT
 * interleaved. alphabet = "bangor" (whitespace-separated ASCII tokens, exact and
 * authoritative) or "ipa" (an IPA string, segmented longest-match-first). Returns the id
 * count, or -1 if the alphabet is unsupported, a symbol has no Bangor equivalent, or a
 * structural token (_ ^ $) was supplied — a typo must be a hard error, not silently
 * mangled audio. Mirrors bangor_g2p.tokens_from_phones. */
int cyp_tokens_from_phones(CyPhonemizer *p, const char *phones, const char *alphabet,
                           int32_t *out, int max_out);

/* Spell a word out letter by letter, Welsh-alphabet style (SSML say-as="characters")
 * -> phone-token ids, NOT interleaved. Longest-match, so the eight digraphs count as
 * single letters ("llan" -> ll, a, n); a digit run reads as one cardinal. Every letter
 * gets a name -- consonants and digraphs from LNAMES, vowels from VSPELLED -- and only an
 * accented vowel, which has no entry, falls back to its lexicon form. Pieces are
 * separated by a ";" pause token. Returns the id count, or -1 on overflow. Mirrors
 * bangor_g2p.letter_tokens. */
int cyp_letter_tokens(CyPhonemizer *p, const char *word, int32_t *out, int max_out);

/* Rule-based Welsh letter-to-sound for OOV words (mirrors bangor_lts.py).
 * Writes the phone-token ids (NOT interleaved) into out; returns the count. */
int cyp_lts(CyPhonemizer *p, const char *word, int32_t *out, int max_out);

/* Welsh text normalization (mirrors welsh_normalize.py): numbers, %, decimals, &,
 * abbreviations, acronym spell-out. Standalone (no CyPhonemizer needed) -- EXCEPT that
 * the acronym pass's vocabulary gate reads a headword set the dictionaries provide:
 * cyp_create loads it, so phonemize callers get it for free, but a harness calling
 * cyp_normalize directly must call cyp_normalize_load_vocab(core_dir) first (returns
 * the headword count, <=0 on failure). With no vocab loaded, every all-caps token is
 * letter-spelled -- which the normalize golden corpus fails loudly on. */
long cyp_normalize_load_vocab(const char *core_dir);
/* Cardinal; above 18 nines (welsh_normalize._CARDINAL_CEILING) digit by digit. int64_t, not
 * long: long is 32 bits on Windows (LLP64), where it wrapped every number of 2^31 and up. */
void cyp_num_to_welsh(int64_t n, char *out, int max_out);
void cyp_normalize(const char *utf8_text, char *out, int max_out);
/* The same, with the language the NUMBERS are read in: CYP_LANG_CY (what cyp_normalize
 * does) or CYP_LANG_EN (British English: "one hundred and twenty three", "the twelfth of
 * march twenty twenty six", "three thirty p·m", "five pounds ninety nine"). Mirrors
 * WelshNormalizer.normalize(text, lang); the words come from english_numbers.py.
 * cyp_text_to_ids_lang chooses this per utterance (explicit lang, else detected from
 * the words), so most callers never call it directly. CYP_LANG_AUTO reads as Welsh. */
void cyp_normalize_lang(const char *utf8_text, int lang, char *out, int max_out);
/* What cyp_text_to_ids (CYP_LANG_AUTO) feeds the phonemizer: the number language detected per
 * sentence/clause from the words (needs the phonemizer's dictionaries, hence the handle).
 * Mirrors BangorG2P.normalize(text) with lang=None. */
void cyp_normalize_auto(CyPhonemizer *p, const char *utf8_text, char *out, int max_out);
/* Text STRUCTURE (docs/text-structure-programme.md §3) -- mirrors BangorG2P.segments. The utterance
 * as rendering units: a sentence, a heading, a list line, each with the boundary that follows it. A
 * line without terminal punctuation takes a full stop (a heading gets the sentence-final fall);
 * brackets and dashes become comma pauses in the normaliser. Numbers and phones are decided per
 * segment. Each segment's ids are a complete BOS..EOS sequence at ids[start .. start+count); render
 * one model pass per segment and insert cyp_boundary_gap_ms(boundary) ms of silence between
 * passes, so device and API sound the same. cyp_text_to_ids is the concatenation of the segments'
 * phones, so both callers agree by construction. Returns the segment count, -1 on overflow. */
enum { CYP_BOUNDARY_END = 0, CYP_BOUNDARY_SENTENCE = 1, CYP_BOUNDARY_LINE = 2, CYP_BOUNDARY_PARAGRAPH = 3 };
typedef struct { int start, count, boundary, number_lang, phone_lang; } CypSegment;
int cyp_segments(CyPhonemizer *p, const char *utf8_text, int lang, CypSegment *segs, int max_segs,
                 int32_t *ids, int max_ids);
int cyp_boundary_gap_ms(int boundary);              /* 250 / 350 / 600 / 0 -- BOUNDARY_GAP_MS */
/* Where each segment and each spoken word came from in the source text -- word and sentence
 * highlighting (mirrors BangorG2P.segment_spans / word_marks / word_starts). Offsets are UTF-8
 * BYTE offsets into utf8_text, end exclusive; Python's are code points. Convert them to the
 * platform's index (UTF-16 for Android, NSRange and SAPI) on the caller's side. Like every
 * cyp_* call that takes a handle, these use process-global buffers and are not reentrant: hold
 * the lock that already guards cyp_segments around them too.
 *
 * cyp_segment_spans: the source span [src_start, src_end) of each segment, parallel to
 * cyp_segments (same text and lang, same order, same count): the sentence/line span with the
 * ASCII whitespace around it trimmed, before any heading '.' is appended. The spans do not depend
 * on lang (it is validated only), so this is cheap -- no normalisation runs -- and pairs with a
 * cyp_segments call that succeeded. Returns the count, -1 on a bad lang or when there are more
 * than max_segs segments (where cyp_segments would truncate to max_segs instead). A text has at
 * most 2049 segments (2048 boundaries plus the tail): size max_segs at 2049 for both calls, or a
 * text past the smaller size is spoken with no sentence or word events. */
int cyp_segment_spans(CyPhonemizer *p, const char *utf8_text, int lang,
                      int *src_start, int *src_end, int max_segs);
/* cyp_word_marks: one mark per source word that starts a new spoken word in its segment. seg is
 * the segment index (as cyp_segments with the same lang); word is the 0-based phone-word ordinal
 * inside that segment where the word's speech starts (phone-word k begins after the k-th WORD_SEP,
 * id 3, of the segment's ids -- cyp_word_starts); src_start/src_end is the source word's byte span.
 * A source word is a run between whitespace (str.isspace) inside the segment's span. Prefix
 * counting: a word's count is the phone-words of the segment's text up to the end of that word,
 * phonemised in the segment's phone_lang, clamped so marks are strictly increasing in `word` and
 * never reach the segment's phone-word count -- so "£9.50" (several spoken words) gets one mark
 * and a lone dash none. From a segment's 32nd word on, the prefix is a window of the 16 to 31
 * words before (same marks on every long text measured), so the cost is linear: one
 * cyp_text_to_ids_lang call per source word on at most 32 words, measured 0.02-0.035 ms per word
 * (12-25 ms for a 4 KB paragraph) at -O2 on an M-series Mac; expect several times that on a
 * phone or a Chromebook. Call it per utterance, off the path to the first audio (after the first
 * piece is queued). Marks are in segment, then source order. Returns the mark count, -1 on a bad
 * lang, when cyp_segments (or a prefix) overflows, or when there are more than max_marks marks. */
typedef struct { int seg, word, src_start, src_end; } CypWordMark;
int cyp_word_marks(CyPhonemizer *p, const char *utf8_text, int lang, CypWordMark *marks, int max_marks);
/* cyp_word_starts: the id index at which each phone-word of ONE segment's interleaved ids begins
 * -- 1 (the PAD after BOS) for word 0, then the index just after each WORD_SEP -- so no platform
 * re-derives the WORD_SEP layout. With per-id model durations d[], word w starts at frame
 * sum(d[0 : starts[w]]). A WORD_SEP directly before EOS starts nothing, so a piece cut just after
 * a WORD_SEP (a segment over the model's id cap, chunked at word boundaries: [..., PAD, 3, EOS])
 * counts only its own words, and ordinals carry across a segment's pieces -- except after a hard
 * split inside one phone-word (one longer than the cap), where the next piece's first phone-word
 * continues the last one and must not be counted again. (A WORD_SEP before [PAD, EOS] does start
 * one, empty: [1,0,20,0,3,0,2] gives [1,5]; no chunker writes that.) No handle and no statics:
 * reentrant. Returns the number of phone-words (0 for an empty [BOS,PAD,EOS]), -1 if ids is NULL
 * or max_starts is too small. */
int cyp_word_starts(const int32_t *ids, int n_ids, int *starts, int max_starts);
void cyp__pause_late(const char *in, char *out);    /* internal: the late pause pass, for cy_phonemize.c */

const char *cyp_data_version(const CyPhonemizer *p);  /* matches the model's config */
int cyp_num_symbols(const CyPhonemizer *p);           /* 256 */

/* --- internal: shared between this library's translation units, NOT part of the ABI
 * (no stability promise; callers outside libcy_phonemize must not use these). --- */
void cyp__lower_strip(const char *in, char *out, int max_out);   /* str.strip().lower() */
int cyp__cp_is_alnum(long cp);                                   /* isdecimal() or isalpha() */
int cyp__cp_is_alpha(long cp);                                   /* str.isalpha() */
int cyp__cp_numeric(long cp);              /* No/Nl: 2 isdigit() (²), 1 isnumeric() only (½), else 0 */
int cyp__cp_decimal_value(long cp);                              /* Nd value 0..9, else -1 */
int cyp__cp_is_space(long cp);                                   /* str.isspace() == re \s */
int cyp__num_words_for_run(const char *digits, int len, char *out); /* int() + num_to_welsh */

#ifdef __cplusplus
}
#endif

#endif /* CY_PHONEMIZE_H */
