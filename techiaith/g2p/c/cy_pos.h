/* Averaged-perceptron POS tagger — mirrors techiaith/g2p/pos_tagger.py exactly.
 * See cy_pos.c for why every detail is load-bearing. */
#ifndef CY_POS_H
#define CY_POS_H

#include <stdint.h>

typedef struct CyPos CyPos;

/* Load <dir>/pos_<lang>.bin. Returns NULL if absent or malformed — a supported state,
 * not an error: without a model the caller falls back to each heteronym's majority
 * reading, which is the 74.1%-correct behaviour the fallback table already gives. */
CyPos *cy_pos_load(const char *dir, const char *lang);
void cy_pos_free(CyPos *p);

/* Tag `n` already-lowercased words. Writes n tag-name pointers (into the model's own
 * tag table, valid for the model's lifetime) into out. Returns 0 on success. */
int cy_pos_tag(const CyPos *p, const char *const *words, int n, const char **out);

/* The tag for one word in context, by index — what the phonemizer actually needs. */
const char *cy_pos_tag_at(const CyPos *p, const char *const *words, int n, int i);

#endif
