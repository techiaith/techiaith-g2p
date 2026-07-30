/* English LTS + language-ID helpers (Workstream P / P7). See cy_english.c. */
#ifndef CY_ENGLISH_H
#define CY_ENGLISH_H

/* Rule-based English G2P -> native phone token STRINGS (OOV fallback). Returns count. */
int cy_english_lts(const char *word, const char **out, int max);

/* Word-level language id: 1 = English, 0 = Welsh (default). */
int cy_classify_word(const char *word);

#endif
