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
 * abbreviations, acronym spell-out. Standalone (no CyPhonemizer needed). */
void cyp_num_to_welsh(long n, char *out, int max_out);        /* cardinal 0..999,999,999 */
void cyp_normalize(const char *utf8_text, char *out, int max_out);

const char *cyp_data_version(const CyPhonemizer *p);  /* matches the model's config */
int cyp_num_symbols(const CyPhonemizer *p);           /* 256 */

/* --- internal: shared between this library's translation units, NOT part of the ABI
 * (no stability promise; callers outside libcy_phonemize must not use these). --- */
void cyp__lower_strip(const char *in, char *out, int max_out);   /* str.strip().lower() */
int cyp__cp_is_alnum(long cp);                                   /* isdecimal() or isalpha() */
int cyp__cp_is_alpha(long cp);                                   /* str.isalpha() */
int cyp__cp_decimal_value(long cp);                              /* Nd value 0..9, else -1 */
int cyp__cp_is_space(long cp);                                   /* str.isspace() == re \s */
int cyp__num_words_for_run(const char *digits, int len, char *out); /* int() + num_to_welsh */

#ifdef __cplusplus
}
#endif

#endif /* CY_PHONEMIZE_H */
