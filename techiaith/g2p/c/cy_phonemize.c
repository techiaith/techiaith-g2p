/* libcy_phonemize — see cy_phonemize.h. Mirrors the Python reference
 * (bangor_g2p.py) for dictionary-covered text: same parser, tokenizer, and
 * [BOS]+[PAD,id]*+[PAD,EOS] interleaving. C99, no dependencies. */
#include "cy_phonemize.h"
#include "cy_english.h"
#include "cy_pos.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* control ids (must match docs/PARITY.md / the id-map) */
enum { PAD = 0, BOS = 1, EOS = 2, SPACE = 3 };
static const char *STRESS_TOK = "\xcb\x88"; /* U+02C8 */
static const char *SYLL_TOK = "|";

/* ---------------- generic string hash (djb2) ---------------- */
static unsigned long djb2(const char *s) {
    unsigned long h = 5381;
    int c;
    while ((c = (unsigned char)*s++)) h = ((h << 5) + h) + c;
    return h;
}

/* token map: symbol -> id */
typedef struct TNode { char *sym; int id; struct TNode *next; } TNode;
/* word map: word -> int32 ids[n] */
typedef struct WNode { char *word; int32_t *ids; int n; struct WNode *next; } WNode;

/* Welsh letter names for isolated consonant letters and digraphs — mirrors
 * bangor_g2p._CY_LETTER_NAMES/_CY_DIGRAPH_NAMES. The lexicons resolve a bare "b"
 * to the naked stop /b/ and have no entry at all for ll/rh/ff/ng/th, so isolated
 * letters are spelled by name instead of looked up. Vowels are absent on purpose
 * (real function words; their letter names are those words). Each entry is a
 * stress mark plus up to three phone tokens, resolved to ids at create time. */
typedef struct { const char *w; int is_digraph; const char *p[3]; } LName;
static const LName LNAMES[] = {
    {"b", 0, {"b", "ii", 0}},  {"c", 0, {"e", "k", 0}},  {"d", 0, {"d", "ii", 0}},
    {"f", 0, {"e", "v", 0}},   {"g", 0, {"e", "g", 0}},  {"h", 0, {"aay", "ch", 0}},
    {"j", 0, {"jh", "ee", 0}}, {"k", 0, {"k", "ee", 0}}, {"l", 0, {"e", "l", 0}},
    {"m", 0, {"e", "m", 0}},   {"n", 0, {"e", "n", 0}},  {"p", 0, {"p", "ii", 0}},
    {"q", 0, {"k", "iu", 0}},  {"r", 0, {"e", "r", 0}},  {"s", 0, {"e", "s", 0}},
    {"t", 0, {"t", "ii", 0}},  {"v", 0, {"v", "ii", 0}}, {"x", 0, {"e", "k", "s"}},
    {"z", 0, {"z", "e", "d"}},
    {"ch", 1, {"e", "x", 0}},  {"dd", 1, {"e", "dh", 0}}, {"ff", 1, {"e", "f", 0}},
    {"ng", 1, {"e", "ng", 0}}, {"ll", 1, {"e", "lh", 0}}, {"ph", 1, {"f", "ii", 0}},
    {"rh", 1, {"rh", "ii", 0}}, {"th", 1, {"e", "th", 0}},
};
#define NLNAMES ((int)(sizeof(LNAMES) / sizeof(LNAMES[0])))

/* English letter names, for ACRONYM runs — mirrors bangor_g2p._EN_LETTER_NAMES.
 * Welsh speech reads acronyms with English letter names (API, TTS, BBC); a digit
 * splits the run (S4C -> "s pedwar c"), so exception acronyms stay Welsh for free.
 * Indexed by letter - 'a'; up to 9 tokens after the stress mark ("w" = double-u). */
static const char *EN_LNAMES[26][9] = {
    /* a */ {"ei", 0}, /* b */ {"b", "ii", 0}, /* c */ {"s", "ii", 0},
    /* d */ {"d", "ii", 0}, /* e */ {"ii", 0}, /* f */ {"e", "f", 0},
    /* g */ {"jh", "ii", 0}, /* h */ {"ei", "ch", 0}, /* i */ {"ai", 0},
    /* j */ {"jh", "ei", 0}, /* k */ {"k", "ei", 0}, /* l */ {"e", "l", 0},
    /* m */ {"e", "m", 0}, /* n */ {"e", "n", 0}, /* o */ {"ou", 0},
    /* p */ {"p", "ii", 0}, /* q */ {"k", "iu", 0}, /* r */ {"aa", "r", 0},
    /* s */ {"e", "s", 0}, /* t */ {"t", "ii", 0}, /* u */ {"j", "uu", 0},
    /* v */ {"v", "ii", 0}, /* w */ {"d", "@", "|", "b", "@", "l", "|", "j", "uu"},
    /* x */ {"e", "k", "s", 0}, /* y */ {"w", "ai", 0}, /* z */ {"z", "e", "d", 0},
};

/* Isolated-VOWEL keystroke names (mirrors bangor_g2p._CY_VOWEL_SOLO). Only applied
 * when the whole utterance is one vowel key, never a one-letter word in a sentence —
 * every vowel is also a real Welsh function word (i="to", o="from", a="and", y="the").
 * 2026-07-27: the owner (native speaker) listened to candidates for the remaining
 * letters and picked long/held renderings for a/e/u/y too; the bare vowels were too
 * short to read as letter names. â was compared and REJECTED (the plain 'aa' fallback
 * was preferred), so it is deliberately absent — do not add it.
 * Used ONLY for the isolated keystroke -- one vowel as the whole utterance. A vowel
 * inside a spell-out run uses VSPELLED below, which holds different lengths on purpose. */
typedef struct { char c; const char *p[3]; } VName;
static const VName VNAMES[] = {
    {'a', {"aa", "aa", 0}},   /* long /aː/ hold (user-picked 2026-07-27) */
    {'e', {"ee", "ee", 0}},   /* long /eː/ hold (user-picked 2026-07-27) */
    {'i', {"i", "ii", 0}},    /* /ɪ iː/ short->long glide (user-picked) */
    {'o', {"oo", "oo", "oo"}},/* long /oː/ hold (user-picked; single was too short) */
    {'u', {"iu", "iu", 0}},   /* /iu/ held twice (user-picked 2026-07-27) */
    {'w', {"uu", 0, 0}},      /* /uː/ Welsh W (not "double-u") */
    {'y', {"@", "@", 0}},     /* /@/ held twice (user-picked 2026-07-27) */
};
#define NVNAMES ((int)(sizeof(VNAMES) / sizeof(VNAMES[0])))

/* Vowel names for a letter inside a SPELL-OUT RUN (mirrors _CY_VOWEL_SPELLED). Distinct
 * from VNAMES because the two contexts were auditioned separately and the owner preferred
 * different lengths: a letter alone has no neighbours to mark it and needs the extra hold,
 * while inside a run the neighbours supply that and the same hold drags. "o" is the clear
 * case -- the single /oː/ was rejected as too short alone, preferred over the triple in a
 * run. Only i/o/y differ from VNAMES; a/e/u/w were auditioned in runs too and kept.
 *
 * y is off the schwa: a stressed isolated /@/ was heard as "yr", and the inventory carries
 * a dedicated @r beside @ (in a bilingual model the English NURSE/lettER vowels live
 * there). "yy" is also what the accented ŷ already yields, so the two now agree.
 *
 * This REPLACES a "plain vowels in spell-out" rule that never delivered plain vowels:
 * a/e/i/o/y are real Welsh function words so word_ids returned the short unstressed WORD,
 * and w -- not a function word -- reached English and came back as a three-syllable
 * "double-you" mid-spelling ("llaw" -> "ell, a, double-you"). */
static const VName VSPELLED[] = {
    {'a', {"aa", "aa", 0}},
    {'e', {"ee", "ee", 0}},
    {'i', {"ii", 0, 0}},      /* was {"i","ii"} -- the glide read as two letters */
    {'o', {"oo", 0, 0}},      /* was {"oo","oo","oo"} -- too slow inside a run */
    {'u', {"iu", "iu", 0}},
    {'w', {"uu", 0, 0}},
    {'y', {"yy", 0, 0}},      /* was {"@","@"} -- the schwa picked up an r */
};
#define NVSPELLED ((int)(sizeof(VSPELLED) / sizeof(VSPELLED[0])))

#define TBITS 10
#define WBITS 20
struct CyPhonemizer {
    TNode *tok[1 << TBITS];
    TNode *ipa[1 << TBITS];    /* IPA spelling -> phone-token id (c/ipa_map.tsv) */
    WNode *word[1 << WBITS];   /* accented all-4 lookup (cy+xx+en+cmudict) */
    WNode *welsh[1 << WBITS];  /* Welsh-only (cy+xx) for native mode */
    WNode *eng[1 << WBITS];    /* native English lexicon (CMUdict) */
    int stress_id, syll_id;
    int english_mode;          /* 0 = accented, 1 = native */
    CyPos *pos_cy;             /* POS taggers; NULL when the model is not installed, */
    CyPos *pos_en;             /* which is supported -- heteronyms take the fallback. */
    int nfold;
    int fold_from[32];
    int32_t fold_to[32][8];
    int fold_to_n[32];
    int32_t lname_ids[NLNAMES][4];  /* resolved Welsh letter-name phone ids */
    int lname_n[NLNAMES];
    int32_t en_lname_ids[26][10];   /* resolved English letter-name phone ids */
    int en_lname_n[26];
    int32_t vname_ids[NVNAMES][4];  /* resolved isolated-vowel letter-name phone ids */
    int vname_n[NVNAMES];
    int32_t vspell_ids[NVSPELLED][4]; /* resolved spell-out vowel letter-name phone ids */
    int vspell_n[NVSPELLED];
    char data_version[64];
};

static int tnode_get(TNode *const *buckets, const char *sym) {
    for (const TNode *n = buckets[djb2(sym) & ((1 << TBITS) - 1)]; n; n = n->next)
        if (strcmp(n->sym, sym) == 0) return n->id;
    return -1;
}
static void tnode_put(TNode **buckets, const char *sym, int id) {
    unsigned long b = djb2(sym) & ((1 << TBITS) - 1);
    TNode *n = (TNode *)malloc(sizeof(TNode));
    n->sym = strdup(sym); n->id = id; n->next = buckets[b]; buckets[b] = n;
}
static int tok_lookup(const CyPhonemizer *p, const char *sym) { return tnode_get(p->tok, sym); }
static void tok_put(CyPhonemizer *p, const char *sym, int id) { tnode_put(p->tok, sym, id); }
/* IPA spelling (1-2 codepoints) -> phone-token id; -1 when it has no Bangor equivalent. */
static int ipa_lookup(const CyPhonemizer *p, const char *sym) { return tnode_get(p->ipa, sym); }
static const WNode *wmap_lookup(WNode *const *buckets, const char *w) {
    for (const WNode *n = buckets[djb2(w) & ((1 << WBITS) - 1)]; n; n = n->next)
        if (strcmp(n->word, w) == 0) return n;
    return NULL;
}
static void wmap_put(WNode **buckets, const char *w, const int32_t *ids, int n) {
    if (wmap_lookup(buckets, w)) return; /* keep first (highest-priority) occurrence */
    unsigned long b = djb2(w) & ((1 << WBITS) - 1);
    WNode *node = (WNode *)malloc(sizeof(WNode));
    node->word = strdup(w);
    node->ids = (int32_t *)malloc(sizeof(int32_t) * (n > 0 ? n : 1));
    memcpy(node->ids, ids, sizeof(int32_t) * n);
    node->n = n; node->next = buckets[b]; buckets[b] = node;
}

static void lower_ascii(char *s) {
    for (; *s; s++) if (*s >= 'A' && *s <= 'Z') *s += 32;
}
static void rstrip(char *s) {
    size_t n = strlen(s);
    while (n && (s[n - 1] == '\n' || s[n - 1] == '\r' || s[n - 1] == ' ' || s[n - 1] == '\t'))
        s[--n] = 0;
}

/* map one dict phone field to id(s); returns 0 ok, -1 if any token unknown */
static int emit_phone_field(const CyPhonemizer *p, const char *field, int32_t *out, int *k) {
    if (strcmp(field, "-") == 0) { out[(*k)++] = p->syll_id; return 0; }
    const char *t = field;
    if (t[0] == '\'') { out[(*k)++] = p->stress_id; t++; }
    if (*t) {
        int id = tok_lookup(p, t);
        if (id < 0) return -1;
        out[(*k)++] = id;
    }
    return 0;
}

/* strip a trailing "(digits)" CMU variant marker from a word, in place */
static void strip_variant(char *w) {
    size_t n = strlen(w);
    if (n < 3 || w[n - 1] != ')') return;
    size_t p = n - 2;
    while (p > 0 && w[p] >= '0' && w[p] <= '9') p--;
    if (w[p] == '(' && p + 1 < n - 1) w[p] = 0;
}

static void load_dict(CyPhonemizer *p, const char *path, WNode **buckets) {
    FILE *f = fopen(path, "r");
    if (!f) return;
    char line[8192];
    int32_t ids[512];
    while (fgets(line, sizeof(line), f)) {
        rstrip(line);
        if (line[0] == 0 || strncmp(line, ";;;", 3) == 0) continue;
        /* drop trailing /ipa/ */
        size_t len = strlen(line);
        if (len && line[len - 1] == '/') {
            long q = (long)len - 2;
            while (q >= 0 && line[q] != '/') q--;
            if (q >= 0) { line[q] = 0; rstrip(line); }
        }
        /* split on spaces */
        char *save = NULL;
        char *word = strtok_r(line, " ", &save);
        if (!word) continue;
        char wbuf[512];
        snprintf(wbuf, sizeof(wbuf), "%s", word);
        strip_variant(wbuf);
        lower_ascii(wbuf);
        /* optional (tag) group after the word */
        char *tok = strtok_r(NULL, " ", &save);
        if (tok && tok[0] == '(') {
            while (tok && tok[strlen(tok) - 1] != ')') tok = strtok_r(NULL, " ", &save);
            tok = strtok_r(NULL, " ", &save);
        }
        int k = 0, bad = 0;
        for (; tok; tok = strtok_r(NULL, " ", &save)) {
            if (k > 500) { bad = 1; break; }
            if (emit_phone_field(p, tok, ids, &k) < 0) { bad = 1; break; }
        }
        if (!bad && k > 0) wmap_put(buckets, wbuf, ids, k);
    }
    fclose(f);
}

/* native English lexicon (cmudict_native.dict): "word<TAB>space-joined tokens" */
static void load_native_english(CyPhonemizer *p, const char *path, WNode **buckets) {
    FILE *f = fopen(path, "r");
    if (!f) return;
    char line[8192];
    int32_t ids[512];
    while (fgets(line, sizeof(line), f)) {
        rstrip(line);
        char *tab = strchr(line, '\t');
        if (!tab) continue;
        *tab = 0;
        const char *word = line;  /* the headword (before the tab) */
        int k = 0, bad = 0;
        char *save = NULL;
        for (char *t = strtok_r(tab + 1, " ", &save); t; t = strtok_r(NULL, " ", &save)) {
            int id = tok_lookup(p, t);
            if (id < 0 || k > 500) { bad = 1; break; }
            ids[k++] = id;
        }
        if (!bad && k > 0) wmap_put(buckets, word, ids, k);
    }
    fclose(f);
}

/* c/ipa_map.tsv: "IPA<TAB>bangor token", emitted from ipa_map.json by
 * scripts/emit_c_data.py — same reason tokens.tsv exists (no JSON parser in the C core).
 * An entry whose token is not in the id map is dropped, so an author's IPA symbol that
 * resolves to nothing is reported as unknown rather than emitting a bogus id. */
static void load_ipa_map(CyPhonemizer *p, const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) return;
    char line[512];
    while (fgets(line, sizeof(line), f)) {
        rstrip(line);
        char *tab = strchr(line, '\t');
        if (!tab) continue;
        *tab = 0;
        int id = tok_lookup(p, tab + 1);
        if (id >= 0) tnode_put(p->ipa, line, id);
    }
    fclose(f);
}

static void load_fold(CyPhonemizer *p, const char *path) {
    FILE *f = fopen(path, "r");
    if (!f) return;
    char line[512];
    while (fgets(line, sizeof(line), f) && p->nfold < 32) {
        rstrip(line);
        char *tab = strchr(line, '\t');
        if (!tab) continue;
        *tab = 0;
        int from = tok_lookup(p, line);
        if (from < 0) continue;
        int k = 0; char *save = NULL;
        for (char *t = strtok_r(tab + 1, " ", &save); t && k < 8; t = strtok_r(NULL, " ", &save)) {
            int id = tok_lookup(p, t);
            if (id >= 0) p->fold_to[p->nfold][k++] = id;
        }
        p->fold_from[p->nfold] = from;
        p->fold_to_n[p->nfold] = k;
        p->nfold++;
    }
    fclose(f);
}

static int fold_ids(const CyPhonemizer *p, const int32_t *in, int n, int32_t *out, int max) {
    int k = 0;
    for (int i = 0; i < n; i++) {
        int folded = 0;
        for (int j = 0; j < p->nfold; j++)
            if (p->fold_from[j] == in[i]) {
                for (int t = 0; t < p->fold_to_n[j] && k < max; t++) out[k++] = p->fold_to[j][t];
                folded = 1; break;
            }
        if (!folded && k < max) out[k++] = in[i];
    }
    return k;
}

static int english_lts_ids(const CyPhonemizer *p, const char *word, int32_t *out, int max) {
    const char *toks[512];
    int nt = cy_english_lts(word, toks, 512);
    int k = 0;
    for (int i = 0; i < nt && k < max; i++) {
        int id = tok_lookup(p, toks[i]);
        if (id >= 0) out[k++] = id;
    }
    return k;
}

/* Defined next to word_ids, which is its only other caller; declared here because
 * cyp_create fills the table once the id map is loaded. */
static void het_load(CyPhonemizer *p);

CyPhonemizer *cyp_create(const char *core_dir, const char *english_mode) {
    CyPhonemizer *p = (CyPhonemizer *)calloc(1, sizeof(CyPhonemizer));
    if (!p) return NULL;
    char path[4096];

    /* tokens.tsv */
    snprintf(path, sizeof(path), "%s/c/tokens.tsv", core_dir);
    FILE *f = fopen(path, "r");
    if (!f) { free(p); return NULL; }
    char line[512];
    while (fgets(line, sizeof(line), f)) {
        char *tab = strchr(line, '\t');
        if (!tab) continue;
        *tab = 0;
        int id = atoi(tab + 1);
        tok_put(p, line, id);
    }
    fclose(f);
    p->stress_id = tok_lookup(p, STRESS_TOK);
    p->syll_id = tok_lookup(p, SYLL_TOK);
    p->english_mode = (english_mode && strcmp(english_mode, "native") == 0) ? 1 : 0;

    /* resolve the letter-name tables (stress + phones) to ids */
    for (int i = 0; i < NLNAMES; i++) {
        int k = 0;
        p->lname_ids[i][k++] = p->stress_id;
        for (int t = 0; t < 3 && LNAMES[i].p[t]; t++) {
            int id = tok_lookup(p, LNAMES[i].p[t]);
            if (id < 0) { k = 0; break; }   /* unknown phone: entry disabled */
            p->lname_ids[i][k++] = id;
        }
        p->lname_n[i] = k > 1 ? k : 0;
    }
    for (int i = 0; i < 26; i++) {
        int k = 0;
        p->en_lname_ids[i][k++] = p->stress_id;
        for (int t = 0; t < 9 && EN_LNAMES[i][t]; t++) {
            int id = tok_lookup(p, EN_LNAMES[i][t]);
            if (id < 0) { k = 0; break; }
            p->en_lname_ids[i][k++] = id;
        }
        p->en_lname_n[i] = k > 1 ? k : 0;
    }
    for (int i = 0; i < NVNAMES; i++) {
        int k = 0;
        p->vname_ids[i][k++] = p->stress_id;
        for (int t = 0; t < 3 && VNAMES[i].p[t]; t++) {
            int id = tok_lookup(p, VNAMES[i].p[t]);
            if (id < 0) { k = 0; break; }
            p->vname_ids[i][k++] = id;
        }
        p->vname_n[i] = k > 1 ? k : 0;
    }
    for (int i = 0; i < NVSPELLED; i++) {
        int k = 0;
        p->vspell_ids[i][k++] = p->stress_id;
        for (int t = 0; t < 3 && VSPELLED[i].p[t]; t++) {
            int id = tok_lookup(p, VSPELLED[i].p[t]);
            if (id < 0) { k = 0; break; }
            p->vspell_ids[i][k++] = id;
        }
        p->vspell_n[i] = k > 1 ? k : 0;
    }

    /* Pronunciation overrides — mirrors bangor_g2p._CY_PRON_OVERRIDE, where the full
     * reasoning lives. Summary: the Bangor dictionary has "mil" as 'm i l (/'mɪl/, SHORT)
     * where standard Welsh is /miːl/, which made every thousand AND every year 1000-2099
     * unintelligible; the owner isolated it by ear on a live service, 2026-07-28.
     *
     * Written in the DICTIONARY's own field syntax ("'m" = stress + m) and pushed through
     * emit_phone_field, the same function load_dict uses, so the two cannot disagree about
     * how stress is encoded. Hand-listing STRESS_TOK here would be a second encoding.
     *
     * Inserted BEFORE the dictionaries so wmap_put's keep-first rule makes the override win
     * with no node mutation. Python instead replaces the entry in tables[0]; the result is
     * identical because its lookup() consults that table first. */
    /* fields[] was [5] (4 phones + NULL) and had to grow: photoshop/powerpoint need 8,
     * and the two-word brand entries need 10. Mirrors bangor_g2p._CY_PRON_OVERRIDE
     * exactly -- the differential fuzz fails if these two tables ever drift apart. */
    static const struct { const char *word; const char *fields[16]; } PRON_OVERRIDE[] = {
        {"mil", {"'m", "ii", "l", NULL}},   /* was 'm i l */
        {"fil", {"'v", "ii", "l", NULL}},   /* soft-mutated, as in "dwy fil" */

        /* BRAND NAMES. bangordict.dict records these with Welsh phonology, which is a
         * defensible editorial choice for Welsh conversation and wrong for a screen reader
         * on an English interface. Only breaks on SHORT utterances -- the sentence router
         * needs ~5 English words, a button label is 1-3. The "|" in those dictionary
         * readings is NOT the defect (ordinary Welsh is full of it); the PHONES are.
         * Values below are the existing cmudict_native entries verbatim. */
        {"youtube",    {"j", "'uu", "t", "j", "uu", "b", NULL}},
        {"google",     {"g", "'uu", "g", "@", "l", NULL}},
        {"twitter",    {"t", "w", "'i", "t", "@r", NULL}},
        {"adobe",      {"@", "d", "'ou", "b", "ii", NULL}},
        {"photoshop",  {"f", "'ou", "t", "ou", "sh", "aa", "p", NULL}},
        {"powerpoint", {"p", "'au", "@r", "p", "oi", "n", "t", NULL}},
        {"ebay",       {"'ii", "b", "ei", NULL}},
        {"iphone",     {"'ai", "f", "ou", "n", NULL}},
        {"ipad",       {"'ai", "p", "æ", "d", NULL}},
        {"android",    {"'æ", "n", "d", "ɹ", "oi", "d", NULL}},

        /* Concatenated brands in NO dictionary. Emitted as TWO WORDS (" ", the word
         * boundary) because the owner tested the spaced forms by ear and preferred them --
         * byte-identical to typing "one drive". Deliberately " " and never "-": the
         * syllable boundary is what makes bangordict's readings sound wrong. */
        {"onedrive",   {"w", "'ʌ", "n", " ", "d", "ɹ", "'ai", "v", NULL}},
        {"chromebook", {"k", "ɹ", "'ou", "m", " ", "b", "'u", "k", NULL}},
        {"firestick",  {"f", "'ai", "@r", " ", "s", "t", "'i", "k", NULL}},
        {"fitbit",     {"'f", "i", "t", " ", "b", "'i", "t", NULL}},
        {"tiktok",     {"t", "'i", "k", " ", "t", "'aa", "k", NULL}},
        /* "deliver" + "ww": "deliver oo" gives Welsh 'oo|o and "uu" gives 'yy|y, both
         * worse. Carries a /w/ onset, so "deliver-WOO" -- best this phoneset offers. */
        {"deliveroo",  {"d", "i", "l", "'i", "v", "@r", " ", "'w", "uu", NULL}},

        /* NOT HERE, deliberately: camera, signal, telegram. Same mechanism, but each is an
         * ordinary Welsh loanword as well as a brand, so an override would break Welsh
         * prose to fix an English label. Owner confirmed they sound fine as they are. */
        {NULL, {NULL}},
    };
    for (int i = 0; PRON_OVERRIDE[i].word; i++) {
        int32_t oids[16];
        int k = 0, bad = 0;
        for (int t = 0; PRON_OVERRIDE[i].fields[t]; t++)
            if (emit_phone_field(p, PRON_OVERRIDE[i].fields[t], oids, &k) < 0) { bad = 1; break; }
        if (bad || k == 0) continue;      /* unknown phone: leave the dictionary form alone */
        wmap_put(p->word, PRON_OVERRIDE[i].word, oids, k);
        wmap_put(p->welsh, PRON_OVERRIDE[i].word, oids, k);
    }

    /* Heteronym phone ids are precomputed in het_load() below, called from here so the
     * id map and emit_phone_field are both ready. */
    het_load(p);

    /* dictionaries — priority order cy -> xx -> en -> cmudict (keep-first wins) */
    const char *dicts[] = {"bangordict.dict", "bangordict.xx.dict",
                           "bangordict.en.dict", "cmudict.dict"};
    for (int i = 0; i < 4; i++) {
        snprintf(path, sizeof(path), "%s/data/geiriadur-ynganu-bangor/%s", core_dir, dicts[i]);
        load_dict(p, path, p->word);
    }
    /* Welsh-only (cy + xx) for native-mode lookup */
    for (int i = 0; i < 2; i++) {
        snprintf(path, sizeof(path), "%s/data/geiriadur-ynganu-bangor/%s", core_dir, dicts[i]);
        load_dict(p, path, p->welsh);
    }
    /* POS models. Absent is fine: het_lookup() then takes each heteronym's fallback,
     * which is the majority-reading behaviour measured at 74.1% correct. */
    snprintf(path, sizeof(path), "%s/data/pos", core_dir);
    p->pos_cy = cy_pos_load(path, "cy");
    p->pos_en = cy_pos_load(path, "en");

    /* native English lexicon + fold map */
    snprintf(path, sizeof(path), "%s/data/english/cmudict_native.dict", core_dir);
    load_native_english(p, path, p->eng);
    snprintf(path, sizeof(path), "%s/c/english_fold.tsv", core_dir);
    load_fold(p, path);
    /* IPA -> token table, for author-supplied <phoneme ph="..." alphabet="ipa"> */
    snprintf(path, sizeof(path), "%s/c/ipa_map.tsv", core_dir);
    load_ipa_map(p, path);

    /* data_version */
    snprintf(path, sizeof(path), "%s/c/data_version.txt", core_dir);
    f = fopen(path, "r");
    if (f) { if (fgets(p->data_version, sizeof(p->data_version), f)) rstrip(p->data_version); fclose(f); }

    /* The normalizer's acronym vocabulary gate reads the same four dictionaries again
     * (headwords only; see cyp_normalize_load_vocab). Failure is not fatal here for the
     * same reason a missing dictionary above is not: the parity corpora catch it loudly,
     * and cyp_create's contract has never been "all data present or NULL". */
    cyp_normalize_load_vocab(core_dir);
    return p;
}

void cyp_destroy(CyPhonemizer *p) {
    if (p) { cy_pos_free(p->pos_cy); cy_pos_free(p->pos_en); p->pos_cy = p->pos_en = NULL; }
    if (!p) return;
    for (int i = 0; i < (1 << TBITS); i++) {
        for (TNode *n = p->tok[i]; n;) { TNode *x = n->next; free(n->sym); free(n); n = x; }
        for (TNode *n = p->ipa[i]; n;) { TNode *x = n->next; free(n->sym); free(n); n = x; }
    }
    for (int i = 0; i < (1 << WBITS); i++) {
        for (WNode *n = p->word[i]; n;) { WNode *x = n->next; free(n->word); free(n->ids); free(n); n = x; }
        for (WNode *n = p->welsh[i]; n;) { WNode *x = n->next; free(n->word); free(n->ids); free(n); n = x; }
        for (WNode *n = p->eng[i]; n;) { WNode *x = n->next; free(n->word); free(n->ids); free(n); n = x; }
    }
    free(p);
}

/* ---------------- Welsh LTS (OOV) — mirrors bangor_lts.py ---------------- */

typedef struct { int kind; int id; char letter; int forced; } Seg; /* kind 0=CONS 1=VDIPH 2=VSINGLE */

static const char *G_CONS2[][2] = {
    {"ng", "ng"}, {"ch", "x"}, {"dd", "dh"}, {"ff", "f"}, {"ll", "lh"}, {"ph", "f"},
    {"rh", "rh"}, {"th", "th"}, {"mh", "mh"}, {"nh", "nh"}, {NULL, NULL}};
static const char *G_CONS1[][2] = {
    {"b", "b"}, {"c", "k"}, {"d", "d"}, {"f", "v"}, {"g", "g"}, {"h", "hh"}, {"j", "jh"},
    {"l", "l"}, {"m", "m"}, {"n", "n"}, {"p", "p"}, {"r", "r"}, {"s", "s"}, {"t", "t"},
    {"k", "k"}, {NULL, NULL}};
static const char *G_DIPH[][2] = {
    {"ae", "aay"}, {"ai", "ai"}, {"au", "ay"}, {"aw", "au"}, {"ei", "ei"}, {"eu", "ey"},
    {"ew", "eu"}, {"ey", "ey"}, {"iw", "iu"}, {"oe", "oy"}, {"oi", "oi"}, {"ou", "ou"},
    {"ow", "ou"}, {"uw", "iu"}, {"wy", "uy"}, {"yw", "yu"}, {NULL, NULL}};
static const char *G_VOW[][3] = {
    {"a", "a", "aa"}, {"e", "e", "ee"}, {"i", "i", "ii"}, {"o", "o", "oo"},
    {"u", "y", "yy"}, {"w", "u", "uu"}, {NULL, NULL, NULL}};

static int is_vowel_letter(char c) {
    return c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u' || c == 'w' || c == 'y';
}

static int map_accent(unsigned cp, char *base, int *forced) {
    switch (cp) {
    case 0xE2: *base = 'a'; *forced = 1; return 1;  /* â */
    case 0xEA: *base = 'e'; *forced = 1; return 1;  /* ê */
    case 0xEE: *base = 'i'; *forced = 1; return 1;  /* î */
    case 0xF4: *base = 'o'; *forced = 1; return 1;  /* ô */
    case 0xFB: *base = 'u'; *forced = 1; return 1;  /* û */
    case 0x175: *base = 'w'; *forced = 1; return 1; /* ŵ */
    case 0x177: *base = 'y'; *forced = 1; return 1; /* ŷ */
    /* Uppercase accented letters — Python normalize() does text.lower() before LTS, so
     * every uppercase accent folds to its lowercase form (same base + forced). Table
     * derived from Python str.lower() over Latin-1 Supp + Latin Ext-A/Additional. */
    case 0xC0: *base = 'a'; *forced = 0; return 1;  /* À */
    case 0xC1: *base = 'a'; *forced = 0; return 1;  /* Á */
    case 0xC2: *base = 'a'; *forced = 1; return 1;  /* Â */
    case 0xC4: *base = 'a'; *forced = 0; return 1;  /* Ä */
    case 0xC8: *base = 'e'; *forced = 0; return 1;  /* È */
    case 0xC9: *base = 'e'; *forced = 0; return 1;  /* É */
    case 0xCA: *base = 'e'; *forced = 1; return 1;  /* Ê */
    case 0xCB: *base = 'e'; *forced = 0; return 1;  /* Ë */
    case 0xCC: *base = 'i'; *forced = 0; return 1;  /* Ì */
    case 0xCD: *base = 'i'; *forced = 0; return 1;  /* Í */
    case 0xCE: *base = 'i'; *forced = 1; return 1;  /* Î */
    case 0xCF: *base = 'i'; *forced = 0; return 1;  /* Ï */
    case 0xD2: *base = 'o'; *forced = 0; return 1;  /* Ò */
    case 0xD3: *base = 'o'; *forced = 0; return 1;  /* Ó */
    case 0xD4: *base = 'o'; *forced = 1; return 1;  /* Ô */
    case 0xD6: *base = 'o'; *forced = 0; return 1;  /* Ö */
    case 0xD9: *base = 'u'; *forced = 0; return 1;  /* Ù */
    case 0xDA: *base = 'u'; *forced = 0; return 1;  /* Ú */
    case 0xDB: *base = 'u'; *forced = 1; return 1;  /* Û */
    case 0xDC: *base = 'u'; *forced = 0; return 1;  /* Ü */
    case 0xDD: *base = 'y'; *forced = 0; return 1;  /* Ý */
    case 0x174: *base = 'w'; *forced = 1; return 1; /* Ŵ */
    case 0x176: *base = 'y'; *forced = 1; return 1; /* Ŷ */
    case 0x178: *base = 'y'; *forced = 0; return 1; /* Ÿ */
    case 0x1E80: *base = 'w'; *forced = 0; return 1; /* Ẁ */
    case 0x1E82: *base = 'w'; *forced = 0; return 1; /* Ẃ */
    case 0x1E84: *base = 'w'; *forced = 0; return 1; /* Ẅ */
    case 0x1EF2: *base = 'y'; *forced = 0; return 1; /* Ỳ */
    /* İ (U+0130) — Python .lower() → "i" + combining dot U+0307 (dropped) → short i. */
    case 0x130: *base = 'i'; *forced = 0; return 1;
    case 0x307: return 0; /* lone combining dot above: unmapped (matches Python drop) */
    case 0xE0: case 0xE1: case 0xE4: *base = 'a'; *forced = 0; return 1;
    case 0xE8: case 0xE9: case 0xEB: *base = 'e'; *forced = 0; return 1;
    case 0xEC: case 0xED: case 0xEF: *base = 'i'; *forced = 0; return 1;
    case 0xF2: case 0xF3: case 0xF6: *base = 'o'; *forced = 0; return 1;
    case 0xF9: case 0xFA: case 0xFC: *base = 'u'; *forced = 0; return 1;
    case 0x1E81: case 0x1E83: case 0x1E85: *base = 'w'; *forced = 0; return 1;
    case 0x1EF3: case 0xFD: case 0xFF: *base = 'y'; *forced = 0; return 1;
    }
    return 0;
}

static unsigned utf8_next(const char *s, int *i) {
    unsigned char c = (unsigned char)s[*i];
    if (c < 0x80) { (*i)++; return c; }
    if ((c >> 5) == 0x6 && s[*i + 1]) {
        unsigned cp = ((c & 0x1F) << 6) | ((unsigned char)s[*i + 1] & 0x3F);
        *i += 2; return cp;
    }
    if ((c >> 4) == 0xE && s[*i + 1] && s[*i + 2]) {
        unsigned cp = ((c & 0x0F) << 12) | (((unsigned char)s[*i + 1] & 0x3F) << 6) |
                      ((unsigned char)s[*i + 2] & 0x3F);
        *i += 3; return cp;
    }
    /* 4-byte / supplementary plane. Without this branch every astral codepoint decoded
     * as U+FFFD one byte at a time, so cyp_letter_tokens could not see one at all and
     * every supplementary Nd digit was silently dropped where Python spells it out —
     * the ND_BLOCK table covered them, but its only caller could not reach them. */
    if ((c >> 3) == 0x1E && s[*i + 1] && s[*i + 2] && s[*i + 3]) {
        unsigned cp = ((c & 0x07) << 18) | (((unsigned char)s[*i + 1] & 0x3F) << 12) |
                      (((unsigned char)s[*i + 2] & 0x3F) << 6) |
                      ((unsigned char)s[*i + 3] & 0x3F);
        *i += 4; return cp;
    }
    (*i)++; return 0xFFFD;
}

static int lts_prep(const char *word, char *base, int *forced, int maxn) {
    int i = 0, n = 0;
    while (word[i] && n < maxn - 1) {
        unsigned cp = utf8_next(word, &i);
        char b; int fl;
        if (cp < 0x80) {
            b = (char)cp; if (b >= 'A' && b <= 'Z') b += 32;
            base[n] = b; forced[n] = 0; n++;
        } else if (map_accent(cp, &b, &fl)) {
            base[n] = b; forced[n] = fl; n++;
        } else { base[n] = '?'; forced[n] = 0; n++; }
    }
    base[n] = 0; return n;
}

static void vow_ids(const CyPhonemizer *p, char letter, int *s, int *l) {
    for (int t = 0; G_VOW[t][0]; t++)
        if (G_VOW[t][0][0] == letter) { *s = tok_lookup(p, G_VOW[t][1]); *l = tok_lookup(p, G_VOW[t][2]); return; }
    *s = *l = -1;
}

static int in_set(int x, const int *a, int n) {
    for (int i = 0; i < n; i++) if (a[i] == x) return 1;
    return 0;
}

int cyp_lts(CyPhonemizer *p, const char *word, int32_t *out, int max_out) {
    char base[512]; int forced[512];
    int n = lts_prep(word, base, forced, 512);

    Seg segs[512]; int ns = 0;
#define PUSH(K, ID, LET, FRC) do { if (ns < 512) { segs[ns].kind = (K); segs[ns].id = (ID); segs[ns].letter = (LET); segs[ns].forced = (FRC); ns++; } } while (0)
    int i = 0;
    while (i < n) {
        char c = base[i];
        if (c == 's' && base[i + 1] == 'i' && i + 2 < n && is_vowel_letter(base[i + 2])) {
            PUSH(0, tok_lookup(p, "sh"), 0, 0); i += 2; continue;
        }
        if (i + 3 <= n && c == 'n' && base[i + 1] == 'g' && base[i + 2] == 'h') {
            PUSH(0, tok_lookup(p, "ngh"), 0, 0); i += 3; continue;
        }
        int matched = 0;
        for (int t = 0; G_CONS2[t][0]; t++)
            if (i + 2 <= n && c == G_CONS2[t][0][0] && base[i + 1] == G_CONS2[t][0][1]) {
                PUSH(0, tok_lookup(p, G_CONS2[t][1]), 0, 0); i += 2; matched = 1; break;
            }
        if (matched) continue;
        for (int t = 0; G_CONS1[t][0]; t++)
            if (c == G_CONS1[t][0][0]) { PUSH(0, tok_lookup(p, G_CONS1[t][1]), 0, 0); i += 1; matched = 1; break; }
        if (matched) continue;
        if (c == 'i' && i + 1 < n && is_vowel_letter(base[i + 1]) && (ns == 0 || segs[ns - 1].kind == 0)) {
            PUSH(0, tok_lookup(p, "j"), 0, 0); i += 1; continue;
        }
        if (c == 'w') {
            char nxt = (i + 1 < n) ? base[i + 1] : 0;
            if (nxt == 'y') { PUSH(1, tok_lookup(p, "uy"), 0, 0); i += 2; continue; }
            if (nxt && is_vowel_letter(nxt)) { PUSH(0, tok_lookup(p, "w"), 0, 0); i += 1; continue; }
            PUSH(2, 0, 'w', forced[i]); i += 1; continue;
        }
        for (int t = 0; G_DIPH[t][0]; t++)
            if (i + 2 <= n && c == G_DIPH[t][0][0] && base[i + 1] == G_DIPH[t][0][1]) {
                PUSH(1, tok_lookup(p, G_DIPH[t][1]), 0, 0); i += 2; matched = 1; break;
            }
        if (matched) continue;
        if (c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u' || c == 'y') {
            PUSH(2, 0, c, forced[i]); i += 1; continue;
        }
        i += 1;
    }
#undef PUSH

    /* postprocess: collapse geminate CONS */
    int j = 0;
    for (int a = 0; a < ns; a++) {
        if (j > 0 && segs[a].kind == 0 && segs[j - 1].kind == 0 && segs[j - 1].id == segs[a].id) continue;
        segs[j++] = segs[a];
    }
    ns = j;
    /* s-cluster devoicing, then nasal assimilation */
    int id_s = tok_lookup(p, "s"), id_b = tok_lookup(p, "b"), id_d = tok_lookup(p, "d"),
        id_g = tok_lookup(p, "g"), id_p = tok_lookup(p, "p"), id_t = tok_lookup(p, "t"),
        id_k = tok_lookup(p, "k"), id_n = tok_lookup(p, "n"), id_ng = tok_lookup(p, "ng");
    for (int a = 0; a + 1 < ns; a++)
        if (segs[a].kind == 0 && segs[a].id == id_s && segs[a + 1].kind == 0) {
            if (segs[a + 1].id == id_b) segs[a + 1].id = id_p;
            else if (segs[a + 1].id == id_d) segs[a + 1].id = id_t;
            else if (segs[a + 1].id == id_g) segs[a + 1].id = id_k;
        }
    for (int a = 0; a + 1 < ns; a++)
        if (segs[a].kind == 0 && segs[a].id == id_n && segs[a + 1].kind == 0 &&
            (segs[a + 1].id == id_k || segs[a + 1].id == id_g))
            segs[a].id = id_ng;

    /* vowel indices + syllables + stress */
    int vidx[512], nsyll = 0, syll_num[512];
    for (int a = 0; a < ns; a++) syll_num[a] = -1;
    for (int a = 0; a < ns; a++) if (segs[a].kind != 0) vidx[nsyll++] = a;
    for (int sy = 0; sy < nsyll; sy++) syll_num[vidx[sy]] = sy;

    int k = 0;
    int stress_tok = tok_lookup(p, "\xcb\x88"), syll_tok = tok_lookup(p, "|"), schwa = tok_lookup(p, "@");
    if (nsyll == 0) {
        if (ns == 0) return 0;
        if (k < max_out) out[k++] = stress_tok;
        for (int a = 0; a < ns; a++) if (k < max_out) out[k++] = segs[a].id;
        return k;
    }
    int stress_syll = (nsyll == 1) ? 0 : nsyll - 2;
    int start_syll_of[512];
    for (int a = 0; a < ns; a++) start_syll_of[a] = -1;
    start_syll_of[0] = 0;
    for (int sy = 1; sy < nsyll; sy++) {
        int kk = vidx[sy], kp = vidx[sy - 1], cc = kk - kp - 1;
        int start = (cc == 0) ? kk : ((cc == 1) ? kp + 1 : kp + 2);
        start_syll_of[start] = sy;
    }
    int lc[9] = {tok_lookup(p, "b"), tok_lookup(p, "d"), tok_lookup(p, "g"), tok_lookup(p, "v"),
                 tok_lookup(p, "dh"), tok_lookup(p, "f"), tok_lookup(p, "th"), tok_lookup(p, "x"),
                 tok_lookup(p, "s")};

    for (int idx = 0; idx < ns; idx++) {
        if (start_syll_of[idx] >= 0) {
            int sy = start_syll_of[idx];
            if (sy > 0 && k < max_out) out[k++] = syll_tok;
            if (sy == stress_syll && k < max_out) out[k++] = stress_tok;
        }
        if (segs[idx].kind == 0 || segs[idx].kind == 1) {
            if (k < max_out) out[k++] = segs[idx].id;
            continue;
        }
        /* VSINGLE resolve */
        int sy = syll_num[idx];
        int is_final = (sy == nsyll - 1), stressed = (sy == stress_syll);
        char letter = segs[idx].letter; int forced_v = segs[idx].forced;
        int short_id, long_id;
        if (letter == 'y') {
            if (!is_final && nsyll > 1) { if (k < max_out) out[k++] = schwa; continue; }
            short_id = tok_lookup(p, "y"); long_id = tok_lookup(p, "yy");
        } else {
            vow_ids(p, letter, &short_id, &long_id);
        }
        int cnt = 0, first = -1;
        for (int jj = idx + 1; jj < ns && segs[jj].kind == 0; jj++) { if (cnt == 0) first = segs[jj].id; cnt++; }
        int long_v = forced_v || (stressed && (cnt == 0 || (cnt == 1 && in_set(first, lc, 9))));
        if (k < max_out) out[k++] = long_v ? long_id : short_id;
    }
    return k;
}

/* Strip surrounding punctuation, keeping ' and - (Welsh clitics/compounds). Mirrors
 * Python w.strip('.,;:!?()"…—'): the ASCII set + the multibyte … (E2 80 A6) and
 * — (E2 80 94). Returns the cleaned start (may be empty); trims trailing in place. */
/* --- punctuation emission (mirrors Python bangor_g2p _PUNCT / _segment) --- */
/* If s begins with an emitted punctuation mark, return its token id and set *adv to
 * the mark's byte length (1 ASCII; 3 for the multibyte … and —); else -1. */
static int punct_head(const CyPhonemizer *p, const char *s, int *adv) {
    if (*s && strchr(".,;:!?()\"", *s)) { char m[2] = { *s, 0 }; *adv = 1; return tok_lookup(p, m); }
    if ((unsigned char)s[0] == 0xE2 && (unsigned char)s[1] == 0x80 &&
        ((unsigned char)s[2] == 0xA6 || (unsigned char)s[2] == 0x94)) {
        char m[4] = { s[0], s[1], s[2], 0 }; *adv = 3; return tok_lookup(p, m);
    }
    return -1;
}
/* If s[0..l) ends with a punctuation mark, return its id and set *back to its byte length; else -1. */
static int punct_tail(const CyPhonemizer *p, const char *s, size_t l, int *back) {
    if (l >= 3 && (unsigned char)s[l - 3] == 0xE2 && (unsigned char)s[l - 2] == 0x80 &&
        ((unsigned char)s[l - 1] == 0xA6 || (unsigned char)s[l - 1] == 0x94)) {
        char m[4] = { s[l - 3], s[l - 2], s[l - 1], 0 }; *back = 3; return tok_lookup(p, m);
    }
    if (l && strchr(".,;:!?()\"", s[l - 1])) { char m[2] = { s[l - 1], 0 }; *back = 1; return tok_lookup(p, m); }
    return -1;
}
/* A core with any letter (ASCII a-z/A-Z or a multibyte >=0x80 byte) is worth
 * phonemizing; mirrors Python's `if core and any(c.isalpha())`. */
static int has_letter(const char *s) {
    for (const unsigned char *c = (const unsigned char *)s; *c; c++)
        if ((*c >= 'a' && *c <= 'z') || (*c >= 'A' && *c <= 'Z') || *c >= 0x80) return 1;
    return 0;
}

/* --- hyphenated runs of single typed letters (mirrors bangor_g2p._hyphen_letter_run) --- */
/* One Welsh alphabet unit: exactly ONE letter (one codepoint str.isalpha() accepts, so
 * 'â' counts as well as 'a'), or one of the eight two-character digraphs that count as a
 * single letter in Welsh orthography. Deliberately NOT a name-table test — the plain
 * vowels have no letter-name entry and must still qualify, exactly as in Python. */
static int is_solo_letter_unit(const char *s, int len) {
    if (len <= 0 || len > 4) return 0;      /* one codepoint is at most 4 bytes... */
    if (len == 2) {                         /* ...and every digraph is exactly two ASCII */
        for (int t = 0; t < NLNAMES; t++)
            if (LNAMES[t].is_digraph && LNAMES[t].w[0] == s[0] && LNAMES[t].w[1] == s[1])
                return 1;
    }
    char one[8];
    memcpy(one, s, (size_t)len);
    one[len] = 0;
    int j = 0;
    unsigned cp = utf8_next(one, &j);
    if (j != len) return 0;                 /* more than one codepoint */
    return cyp__cp_is_alpha((long)cp);
}

/* Is `core` a keyboard-echoed run of single letters joined by '-' ("d-d-d", "b-a-ch")?
 * Then the hyphens are SEPARATORS and each unit becomes its own comma-paced word, just
 * like the commas in "c, a, th". A real compound always has at least one part longer than
 * a single unit ("gogledd-ddwyrain"), so its hyphen stays inside the core and the lexicon
 * key survives — that per-part test is the entire safety property. */
static int hyphen_letter_run(const char *core) {
    if (!strchr(core, '-')) return 0;
    int parts = 0;
    for (const char *q = core;;) {
        const char *m = strchr(q, '-');
        int len = m ? (int)(m - q) : (int)strlen(q);
        if (!is_solo_letter_unit(q, len)) return 0;
        parts++;
        if (!m) break;
        q = m + 1;
    }
    return parts >= 2;                      /* a '-' guarantees this; kept explicit */
}

/* --- unknown hyphenated compounds (mirrors bangor_g2p._hyphen_parts) -------------------
 * Screen readers are full of hyphenated English compounds -- double-tap, drop-down,
 * read-only, sign-in, scroll-bar, check-box, log-out -- and none is in any table. As one
 * token they fall to Welsh letter-to-sound AND starve the sentence router of English
 * evidence, so neighbouring words that are also real Welsh words stay Welsh ("to" -> the
 * Welsh 'to', a roof). Splitting fixes both.
 *
 * THE GUARD: a hyphenated form that IS in a table is never split, which keeps all 511
 * hyphenated Welsh entries (gogledd-ddwyrain, pen-blwydd, e-bost) and the hyphenated
 * English ones (wi-fi, built-in, e-mail) exactly as they were -- splitting "wi-fi" would
 * give "w i v i", so the ordering is load-bearing. Both parts must be independently
 * known, or splitting buys nothing. Parts shorter than 2 chars are excluded so a
 * keyboard-echoed letter run stays with hyphen_letter_run above. */
static int known_word(CyPhonemizer *p, const char *w) {
    return wmap_lookup(p->word, w) != NULL || wmap_lookup(p->eng, w) != NULL;
}

/* UTF-8 CHARACTERS in the first `nbytes` bytes, not bytes. Python's guard counts
 * characters, and Welsh is full of two-byte letters (ŵ ê î ô û ŷ â), so measuring bytes
 * here made "sg-ŵ" and "ê-wyth" pass a guard Python rejects -- the differential fuzz
 * caught it at 9/20000 inputs. Continuation bytes are 10xxxxxx and are not counted. */
static size_t u8len(const char *s, size_t nbytes) {
    size_t n = 0;
    for (size_t i = 0; i < nbytes; i++)
        if (((unsigned char)s[i] & 0xC0) != 0x80) n++;
    return n;
}

static int hyphen_compound(CyPhonemizer *p, const char *core) {
    char buf[256];
    if (!strchr(core, '-')) return 0;
    if (known_word(p, core)) return 0;          /* a real hyphenated entry -- never split */
    if (strlen(core) >= sizeof buf) return 0;
    int parts = 0;
    const char *q = core;
    for (;;) {
        const char *m = strchr(q, '-');
        size_t len = m ? (size_t)(m - q) : strlen(q);
        /* Empty parts are SKIPPED, not rejected: Python builds its list with
         * `[p for p in core.split("-") if p]`, so a leading/trailing/doubled hyphen
         * ("di-dau-") drops the empty string and still splits. Bailing here instead
         * diverged on exactly that shape -- caught by the differential fuzz. */
        if (len) {
            if (len >= sizeof buf || u8len(q, len) < 2) return 0;
            memcpy(buf, q, len); buf[len] = 0;
            if (!known_word(p, buf)) return 0;
            parts++;
        }
        if (!m) break;
        q = m + 1;
    }
    return parts >= 2;
}

/* ---- ACRONYM_JOIN (U+00B7) handling — mirrors bangor_g2p ---- */
#define AJOIN "\xC2\xB7"          /* U+00B7 MIDDLE DOT, welsh_normalize.ACRONYM_JOIN */

/* Is this core one _spell_acronym wrote — i.e. is EVERY marker-separated part a single
 * letter we have an English name for? U+00B7 is a character users can type, so a core can
 * carry one we did not write; treating those as acronyms silently deleted the text
 * (mirrors the guard in bangor_g2p._acronym_tokens). */
static int core_is_acronym(const CyPhonemizer *p, const char *s) {
    if (!strstr(s, AJOIN)) return 0;
    for (const char *q = s;;) {
        const char *m = strstr(q, AJOIN);
        size_t len = m ? (size_t)(m - q) : strlen(q);
        if (len != 1) return 0;                       /* empty or multi-character part */
        unsigned char ch = (unsigned char)q[0];
        if (ch < 'a' || ch > 'z' || p->en_lname_n[ch - 'a'] <= 0) return 0;
        if (!m) return 1;
        q = m + 2;
    }
}

/* HETERONYMS -- mirrors bangor_g2p._HETERONYM, where the reasoning and the MASC
 * measurements live. One spelling, two pronunciations chosen by GRAMMAR; no lexicon here
 * can express that, so this is consulted in word_ids() BEFORE any of them, at exactly the
 * point Python consults _HETERONYM.
 *
 * Rows are (word, tag, phones). The tag==NULL row is the POS-BLIND FALLBACK -- the word's
 * majority reading in MASC -- and is used when there is no tagger, no model, or no branch
 * for the tag that came back. Python is `branch.get(pos) or branch[None]`; this is the same
 * two-step, and diff_fuzz_c_parity fails if the tables drift apart.
 *
 * An earlier version inserted only the fallbacks into p->word/p->eng at load time and
 * replaced them in p->welsh. That could not express a per-occurrence choice, so it is gone:
 * the selection is now made per word, with context, on both sides. */
static const struct { const char *word; const char *tag; const char *fields[16]; }
HETERONYM[] = {
        {"close",    NULL,     {"k", "l", "'ou", "z", NULL}},
        {"close",    "ADJ",    {"k", "l", "'ou", "s", NULL}},
        {"close",    "ADV",    {"k", "l", "'ou", "s", NULL}},
        {"close",    "VERB",   {"k", "l", "'ou", "z", NULL}},
        {"close",    "VPAST",  {"k", "l", "'ou", "z", NULL}},
        {"desert",   NULL,     {"d", "'e", "z", "@r", "t", NULL}},
        {"desert",   "NOUN",   {"d", "'e", "z", "@r", "t", NULL}},
        {"desert",   "VERB",   {"d", "@", "z", "'@r", "t", NULL}},
        {"desert",   "VPAST",  {"d", "@", "z", "'@r", "t", NULL}},
        {"estimate", NULL,     {"'e", "s", "t", "@", "m", "ei", "t", NULL}},
        {"estimate", "NOUN",   {"'e", "s", "t", "@", "m", "@", "t", NULL}},
        {"estimate", "VERB",   {"'e", "s", "t", "@", "m", "ei", "t", NULL}},
        {"estimate", "VPAST",  {"'e", "s", "t", "@", "m", "ei", "t", NULL}},
        {"live",     NULL,     {"l", "'i", "v", NULL}},
        {"live",     "ADJ",    {"l", "'ai", "v", NULL}},
        {"live",     "VERB",   {"l", "'i", "v", NULL}},
        {"object",   NULL,     {"@", "b", "jh", "'e", "k", "t", NULL}},
        {"object",   "NOUN",   {"'aa", "b", "jh", "e", "k", "t", NULL}},
        {"object",   "VERB",   {"@", "b", "jh", "'e", "k", "t", NULL}},
        {"object",   "VPAST",  {"@", "b", "jh", "'e", "k", "t", NULL}},
        {"present",  NULL,     {"p", "ɹ", "'e", "z", "@", "n", "t", NULL}},
        {"present",  "ADJ",    {"p", "ɹ", "'e", "z", "@", "n", "t", NULL}},
        {"present",  "NOUN",   {"p", "ɹ", "'e", "z", "@", "n", "t", NULL}},
        {"present",  "VERB",   {"p", "ɹ", "@", "z", "'e", "n", "t", NULL}},
        {"present",  "VPAST",  {"p", "ɹ", "@", "z", "'e", "n", "t", NULL}},
        {"read",     NULL,     {"ɹ", "'ii", "d", NULL}},
        {"read",     "VERB",   {"ɹ", "'ii", "d", NULL}},
        {"read",     "VPAST",  {"ɹ", "'e", "d", NULL}},
        {"record",   NULL,     {"'ɹ", "e", "k", "@r", "d", NULL}},
        {"record",   "NOUN",   {"'ɹ", "e", "k", "@r", "d", NULL}},
        {"record",   "VERB",   {"ɹ", "@", "k", "'oo", "ɹ", "d", NULL}},
        {"record",   "VPAST",  {"ɹ", "@", "k", "'oo", "ɹ", "d", NULL}},
        {"refuse",   NULL,     {"ɹ", "@", "f", "j", "'uu", "z", NULL}},
        {"refuse",   "NOUN",   {"'ɹ", "e", "f", "j", "uu", "s", NULL}},
        {"refuse",   "VERB",   {"ɹ", "@", "f", "j", "'uu", "z", NULL}},
        {"refuse",   "VPAST",  {"ɹ", "@", "f", "j", "'uu", "z", NULL}},
        {"separate", NULL,     {"s", "'e", "p", "@r", "@", "t", NULL}},
        {"separate", "ADJ",    {"s", "'e", "p", "@r", "@", "t", NULL}},
        {"separate", "VERB",   {"s", "'e", "p", "@r", "ei", "t", NULL}},
        {"separate", "VPAST",  {"s", "'e", "p", "@r", "ei", "t", NULL}},
        {"use",      NULL,     {"j", "'uu", "z", NULL}},
        {"use",      "NOUN",   {"j", "'uu", "s", NULL}},
        {"use",      "VERB",   {"j", "'uu", "z", NULL}},
        {"use",      "VPAST",  {"j", "'uu", "z", NULL}},
        {"wind",     NULL,     {"w", "'i", "n", "d", NULL}},
        {"wind",     "NOUN",   {"w", "'i", "n", "d", NULL}},
        {"wind",     "VERB",   {"w", "'ai", "n", "d", NULL}},
        {NULL, NULL, {NULL}},
};
#define MAX_HET 128
static int32_t HET_IDS[MAX_HET][16];
static int     HET_N[MAX_HET];
static int     HET_ROWS;

static void het_load(CyPhonemizer *p) {
    HET_ROWS = 0;
    for (int i = 0; HETERONYM[i].word && i < MAX_HET; i++) {
        int32_t ids[16];
        int k = 0, bad = 0;
        for (int t = 0; HETERONYM[i].fields[t]; t++)
            if (emit_phone_field(p, HETERONYM[i].fields[t], ids, &k) < 0) { bad = 1; break; }
        HET_N[i] = (bad || k == 0) ? 0 : k;      /* 0 = unusable, skipped at lookup */
        if (!bad && k > 0) memcpy(HET_IDS[i], ids, sizeof(int32_t) * (size_t)k);
        HET_ROWS = i + 1;
    }
}

/* -1 if `s` is not a heteronym. Otherwise the tagged branch for `pos` if there is one,
 * else the fallback -- the same precedence as Python's branch.get(pos) or branch[None]. */
static int het_lookup(const char *s, const char *pos, int32_t *out, int max) {
    int fb = -1;
    for (int i = 0; i < HET_ROWS; i++) {
        if (strcmp(HETERONYM[i].word, s) != 0) continue;
        if (HETERONYM[i].tag == NULL) { fb = i; continue; }
        if (pos && strcmp(HETERONYM[i].tag, pos) == 0 && HET_N[i] > 0) {
            int n = HET_N[i] < max ? HET_N[i] : max;
            memcpy(out, HET_IDS[i], sizeof(int32_t) * (size_t)n);
            return n;
        }
    }
    if (fb >= 0 && HET_N[fb] > 0) {
        int n = HET_N[fb] < max ? HET_N[fb] : max;
        memcpy(out, HET_IDS[fb], sizeof(int32_t) * (size_t)n);
        return n;
    }
    return -1;
}

/* One word -> phone ids: the Welsh letter-name intercept plus the lexicon/LTS routing,
 * i.e. bangor_g2p._word_tokens minus the acronym and solo-vowel intercepts, which the
 * caller decides because they need sentence context. Returns the id count. */
static int word_ids(CyPhonemizer *p, const char *s, int lang_en, const char *pos,
                    int32_t *out, int max) {
    int li = -1;
    if (s[0] && (!s[1] || !s[2])) {   /* 1- or 2-byte core only */
        for (int t = 0; t < NLNAMES; t++)
            if (strcmp(LNAMES[t].w, s) == 0) { li = t; break; }
    }
    /* digraphs are Welsh letters in any context; other single consonants get Welsh
     * names, except that an English-context sentence under native mode keeps CMUdict's */
    if (li >= 0 && p->lname_n[li] > 0 &&
        (LNAMES[li].is_digraph || !(p->english_mode && lang_en))) {
        int n = p->lname_n[li] < max ? p->lname_n[li] : max;
        memcpy(out, p->lname_ids[li], sizeof(int32_t) * (size_t)n);
        return n;
    }
    /* Heteronyms, before either lexicon -- Python's _HETERONYM check sits in exactly this
     * position in _word_tokens, after the letter names and ahead of the english_mode
     * branches. `pos` is NULL unless the caller ran the tagger. */
    {
        int hn = het_lookup(s, pos, out, max);
        if (hn > 0) return hn;
    }
    if (p->english_mode) {            /* native: sentence-aware Welsh/English routing */
        const WNode *wh = wmap_lookup(p->welsh, s);
        const WNode *eh = wmap_lookup(p->eng, s);
        const WNode *hit = NULL;
        if (lang_en) {
            /* English context: the English lexicon wins for any word it knows (shared
             * words -> English); a Welsh-only word is a code-switch. */
            hit = eh ? eh : wh;
            if (!hit) return english_lts_ids(p, s, out, max);
        } else {
            /* Welsh context (default): the Welsh lexicon wins, protecting Welsh words
             * that also exist in English; an English-only word is a code-switch. */
            hit = wh ? wh : eh;
            if (!hit) return cy_classify_word(s) ? english_lts_ids(p, s, out, max)
                                                 : cyp_lts(p, s, out, max);
        }
        int n = hit->n < max ? hit->n : max;
        memcpy(out, hit->ids, sizeof(int32_t) * (size_t)n);
        return n;
    }
    /* accented: all-4 dict -> folded English -> Welsh LTS */
    const WNode *hit = wmap_lookup(p->word, s);
    if (hit) {
        int n = hit->n < max ? hit->n : max;
        memcpy(out, hit->ids, sizeof(int32_t) * (size_t)n);
        return n;
    }
    const WNode *eh = wmap_lookup(p->eng, s);
    if (eh || cy_classify_word(s)) {
        int32_t nat[2048]; int nn;
        if (eh) { nn = eh->n < 2048 ? eh->n : 2048; memcpy(nat, eh->ids, sizeof(int32_t) * (size_t)nn); }
        else { nn = english_lts_ids(p, s, nat, 2048); }
        return fold_ids(p, nat, nn, out, max);
    }
    return cyp_lts(p, s, out, max);
}

/* Flat (non-interleaved) phone-token ids for ALREADY-NORMALIZED text — the C mirror of
 * bangor_g2p.phonemize(text, on_oov="lts", lang=...). ntext must already be lowercased
 * and verbalised by cyp_normalize (or be lowercase ASCII produced by cyp_num_to_welsh),
 * because _segment's own .lower() is folded into that pass here.
 * lang: CYP_LANG_AUTO (sentence-level routing), CYP_LANG_CY, or CYP_LANG_EN.
 * Returns the token count, or -1 on overflow / bad lang. */
static int phonemize_flat(CyPhonemizer *p, const char *ntext, int lang,
                          int32_t *flat, int cap) {
    if (lang < CYP_LANG_AUTO || lang > CYP_LANG_EN) return -1;
    static char buf[65536];
    snprintf(buf, sizeof(buf), "%s", ntext);

    /* Pass 1: tokenize; peel surrounding punctuation and CAPTURE it as pause tokens
     * (mirrors bangor_g2p._segment). Keep the cleaned core for _sentence_lang and the
     * emit loop, plus each token's leading/trailing punct ids. */
    typedef struct { int lead[8], nlead; char *core; int trail[8], ntrail; int gap_before; } Tok;
    static Tok toks[16384];
    int nt = 0, gap = 0;
    /* Python's `words` list: EVERY non-empty core, whether or not it has letters. It is
     * only used for the solo-vowel test below, and counting it exactly is what stops
     * "a $" (two cores, one of them letterless) from being mistaken for a lone keystroke
     * now that all seven vowels have solo names. only_core_ti names the single core's
     * token when there is exactly one and it survived; -1 when the only core was a
     * dropped letterless token, which is never a vowel key. */
    int n_cores = 0, only_core_ti = -1;
    /* Python's `words` list verbatim, for the POS tagger: it must be the SAME sequence
     * Python builds, or a tag lands on the wrong word. Recorded at every site that
     * increments n_cores -- including the letterless core C drops but Python keeps,
     * which has no Tok and so would otherwise shift every later index by one.
     * tok_widx maps a Tok back to its position in that list. */
    static const char *wordlist[16384];
    static int tok_widx[16384];
    int n_wordlist = 0;
    const int comma_id = tok_lookup(p, ",");
    char *save = NULL;
    for (char *w = strtok_r(buf, " \t\r\n", &save); w; w = strtok_r(NULL, " \t\r\n", &save)) {
        Tok t; t.nlead = 0; t.ntrail = 0;
        char *s = w;
        for (int adv, id; (id = punct_head(p, s, &adv)) >= 0; s += adv)
            if (t.nlead < 8) t.lead[t.nlead++] = id;
        size_t l = strlen(s);
        for (int back, id; (id = punct_tail(p, s, l, &back)) >= 0; ) {
            if (t.ntrail < 8) t.trail[t.ntrail++] = id;   /* collected end-first, emitted reversed */
            l -= back; s[l] = 0;
        }
        t.core = s;
        /* INTERIOR peel (mirrors _segment): split the cleaned core at interior _PUNCT
         * runs, so "ie!na" tokenises exactly as "ie! na" does instead of fusing into
         * one LTS nonword with the "!" silently dropped (FOLLOWUPS section G). Marks
         * BEFORE the first "(" of a run trail the left sub-word; marks FROM the first
         * "(" lead the right one ("ty(bach)" == "ty (bach)", "a!(b" == "a! (b"). The
         * first sub-word keeps the token's leading punct, the last its trailing. Every
         * emitted id is already trained (pause ids), so this is a re-tokenisation, not
         * an emission-policy change. Scanning byte-by-byte is safe: punct_head matches
         * ASCII marks or an 0xE2-led sequence, and UTF-8 continuation bytes can never
         * begin either. Each sub-token then flows through the SAME drop / letter-run /
         * append logic a whole token always did; only the first sub-token can carry
         * gap_before. */
        char *rest = s;
        int cur_lead[8], ncur = t.nlead;
        memcpy(cur_lead, t.lead, sizeof cur_lead);
        for (;;) {
            char *run = NULL;
            int adv, id;
            for (char *q = rest; *q; q++)
                if (punct_head(p, q, &adv) >= 0) { run = q; break; }
            int sub_trail[8], nsub = 0;
            int next_lead[8], nnext = 0;
            char *next_rest = NULL;
            if (run) {
                int seen_paren = 0;
                int src[8], nsrc = 0;           /* left-trail marks, in SOURCE order */
                char *e = run;
                while (*e && (id = punct_head(p, e, &adv)) >= 0) {
                    if (!seen_paren && *e == '(') seen_paren = 1;
                    if (seen_paren) { if (nnext < 8) next_lead[nnext++] = id; }
                    else            { if (nsrc < 8) src[nsrc++] = id; }
                    e += adv;
                }
                /* Tok.trail is stored END-FIRST (punct_tail collects backwards and the
                 * emit loop reverses), so the run's left-trail marks go in reversed --
                 * "a).b" must speak ")" then ".", the source order. */
                for (int z = nsrc - 1; z >= 0; z--) sub_trail[nsub++] = src[z];
                *run = 0;                       /* terminate the left sub-core */
                next_rest = e;
            } else {
                for (int z = 0; z < t.ntrail; z++)
                    if (nsub < 8) sub_trail[nsub++] = t.trail[z];
            }
            /* a dropped raw token still breaks letter-run adjacency (Python keeps every
             * segment in its list, so "b - c" is not a run there either) */
            if (ncur == 0 && nsub == 0 && !has_letter(rest)) {
                gap = 1;
                if (*rest) {                      /* a core Python counts, we drop */
                    n_cores++; only_core_ti = -1;
                    if (n_wordlist < 16384) wordlist[n_wordlist++] = rest;
                }
            } else if (hyphen_letter_run(rest)) {
                /* Keyboard echo, not a compound: re-yield each unit as its own word with
                 * a comma pause between them, so the shape is byte-identical to typing
                 * "d, d, d" (mirrors bangor_g2p._segment). The leading punctuation
                 * belongs to the first unit and the trailing punctuation to the last. */
                for (char *q = rest; ; ) {
                    char *m = strchr(q, '-');
                    if (m) *m = 0;
                    Tok u; u.nlead = 0; u.ntrail = 0; u.core = q; u.gap_before = gap;
                    if (q == rest) for (int z = 0; z < ncur; z++) u.lead[u.nlead++] = cur_lead[z];
                    if (m) { if (comma_id >= 0) u.trail[u.ntrail++] = comma_id; }
                    else   { for (int z = 0; z < nsub; z++) u.trail[u.ntrail++] = sub_trail[z]; }
                    gap = 0;
                    if (nt >= (int)(sizeof(toks) / sizeof(toks[0]))) return -1;
                    n_cores++; only_core_ti = nt;
                    if (n_wordlist < 16384) { tok_widx[nt] = n_wordlist; wordlist[n_wordlist++] = u.core; }
                    toks[nt++] = u;
                    if (!m) break;
                    q = m + 1;
                }
            } else if (hyphen_compound(p, rest)) {
                /* Re-yield each part as its own WORD (no comma, unlike the letter-run
                 * branch above): the word separator comes from normal token joining, so
                 * the shape is byte-identical to typing a space instead of the hyphen.
                 * Leading punctuation belongs to the first part, trailing to the last. */
                char *pieces[32]; int npieces = 0;
                for (char *q = rest; ; ) {
                    char *m = strchr(q, '-');
                    if (m) *m = 0;
                    if (*q && npieces < 32) pieces[npieces++] = q;   /* skip empties */
                    if (!m) break;
                    q = m + 1;
                }
                for (int i = 0; i < npieces; i++) {
                    Tok u; u.nlead = 0; u.ntrail = 0; u.core = pieces[i]; u.gap_before = gap;
                    if (i == 0) for (int z = 0; z < ncur; z++) u.lead[u.nlead++] = cur_lead[z];
                    if (i == npieces - 1)
                        for (int z = 0; z < nsub; z++) u.trail[u.ntrail++] = sub_trail[z];
                    gap = 0;
                    if (nt >= (int)(sizeof(toks) / sizeof(toks[0]))) return -1;
                    n_cores++; only_core_ti = nt;
                    if (n_wordlist < 16384) { tok_widx[nt] = n_wordlist; wordlist[n_wordlist++] = u.core; }
                    toks[nt++] = u;
                }
            } else {
                if (nt >= (int)(sizeof(toks) / sizeof(toks[0]))) return -1;
                Tok u; u.nlead = 0; u.ntrail = 0; u.core = rest;
                for (int z = 0; z < ncur; z++) u.lead[u.nlead++] = cur_lead[z];
                for (int z = 0; z < nsub; z++) u.trail[u.ntrail++] = sub_trail[z];
                u.gap_before = gap; gap = 0;
                if (*u.core) {
                    n_cores++; only_core_ti = nt;
                    if (n_wordlist < 16384) { tok_widx[nt] = n_wordlist; wordlist[n_wordlist++] = u.core; }
                }
                toks[nt++] = u;
            }
            if (!run) break;
            rest = next_rest;
            memcpy(cur_lead, next_lead, sizeof cur_lead);
            ncur = nnext;
        }
    }

    /* Sentence language (native routing only) — mirrors bangor_g2p._sentence_lang over
     * the non-empty cleaned cores. Welsh is the default; switch to English only on
     * sustained evidence (English-only words outnumber Welsh-only AND are >=2 and
     * >=1/3 of the run), so a lone loanword can't flip a Welsh utterance.
     * An explicit lang is an author override (SSML <lang xml:lang="...">) and wins
     * outright, exactly as Python's `lang = lang or self._sentence_lang(words)`: the
     * automatic routing is then not consulted at all (it has no side effects). */
    int lang_en = 0;
    if (lang != CYP_LANG_AUTO) {
        lang_en = (lang == CYP_LANG_EN);
    } else {
        int en_only = 0, cy_only = 0;
        for (int i = 0; i < nt; i++) {
            if (!*toks[i].core) continue;
            int in_w = wmap_lookup(p->welsh, toks[i].core) != NULL;
            int in_e = wmap_lookup(p->eng, toks[i].core) != NULL;
            if (in_e && !in_w) en_only++;
            else if (in_w && !in_e) cy_only++;
        }
        int n = nt > 0 ? nt : 1;
        lang_en = (en_only > cy_only && en_only >= 2 && en_only * 3 >= n);
    }

    /* solo vowel: the whole utterance is a single vowel keystroke (mirrors
     * bangor_g2p's `len(words) == 1 and words[0] in _CY_VOWEL_SOLO`) — exactly one
     * non-empty core, and that core is one of the seven vowel letters. A one-letter
     * vowel WORD inside a sentence must never take the letter name. */
    int solo_vowel_ti = -1;
    if (n_cores == 1 && only_core_ti >= 0) {
        const char *s = toks[only_core_ti].core;
        if (s[0] && !s[1])
            for (int v = 0; v < NVNAMES; v++)
                if (VNAMES[v].c == s[0] && p->vname_n[v] > 0) { solo_vowel_ti = only_core_ti; break; }
    }

    int fn = 0, nwords = 0;
    const int CAP = cap;
    /* POS TAGGING, gated exactly as bangor_g2p.phonemize gates it: only run when the
     * utterance actually contains a heteronym, because that is the only thing that reads
     * a tag. Beyond the cost saving, this bounds the blast radius -- every utterance
     * without a heteronym is provably unchanged by the tagger, on both sides, so the
     * parity surface is the inputs it can affect rather than all of them. */
    static const char *pos_tags[16384];
    int have_pos = 0;
    {
        int any_het = 0;
        for (int i = 0; i < n_wordlist && !any_het; i++)
            for (int k = 0; k < HET_ROWS; k++)
                if (strcmp(HETERONYM[k].word, wordlist[i]) == 0) { any_het = 1; break; }
        if (any_het) {
            /* ALWAYS the English tagger -- every HETERONYM row is an English word, so its
             * reading is chosen by an English tag whatever the sentence routed as. Short
             * English sentences route to Welsh (the router wants ~5 English words) and the
             * Welsh tagger cannot tag English. Mirrors bangor_g2p.phonemize. */
            const CyPos *tagger = p->pos_en;
            (void)lang_en;
            if (tagger && n_wordlist > 0 &&
                cy_pos_tag(tagger, wordlist, n_wordlist, pos_tags) == 0)
                have_pos = 1;
        }
    }

    for (int ti = 0; ti < nt; ti++) {
        const char *s = toks[ti].core;
        const int32_t *wids = NULL; int wn = 0; int32_t wbuf[2048];
        if (has_letter(s)) {
            /* Isolated letters are spelled by name, not looked up (mirrors the
             * intercept at the top of bangor_g2p._word_tokens). A core carrying
             * ACRONYM_JOIN gets ENGLISH letter names ONLY if every part is a single
             * named letter; a marker the author typed is a word separator instead, and
             * a core with neither goes straight to word_ids. */
            int vi = -1;
            if (ti == solo_vowel_ti)
                for (int v = 0; v < NVNAMES; v++)
                    if (VNAMES[v].c == s[0] && !s[1]) { vi = v; break; }
            if (vi >= 0) {   /* single typed vowel key, not a word */
                wids = p->vname_ids[vi]; wn = p->vname_n[vi];
            } else if (core_is_acronym(p, s)) {
                /* English letter name per part, WORD_SEP between them — each letter of an
                 * acronym is its own spoken word (mirrors bangor_g2p._acronym_tokens).
                 * core_is_acronym has already established every part is a single a-z
                 * letter, so no part can fail to produce a name. */
                int n = 0;
                for (const char *q = s;;) {
                    const char *m = strstr(q, AJOIN);
                    unsigned char ch = (unsigned char)q[0];
                    if (n > 0 && n < 2048) wbuf[n++] = SPACE;
                    for (int k2 = 0; k2 < p->en_lname_n[ch - 'a'] && n < 2048; k2++)
                        wbuf[n++] = p->en_lname_ids[ch - 'a'][k2];
                    if (!m) break;
                    q = m + 2;
                }
                wids = wbuf; wn = n;
            } else if (strstr(s, AJOIN)) {
                /* A U+00B7 the author typed, not the marker _spell_acronym writes: treat
                 * it as a WORD SEPARATOR and speak every part, so nothing is dropped
                 * (mirrors bangor_g2p._typed_marker_tokens). */
                int n = 0;
                for (const char *q = s;;) {
                    const char *m = strstr(q, AJOIN);
                    size_t len = m ? (size_t)(m - q) : strlen(q);
                    if (len > 0) {
                        /* An over-long part is TRUNCATED, never skipped: in a fix whose
                         * whole thesis is "nothing is silently dropped", dropping the
                         * part would be the same bug in a rarer costume. (The C already
                         * diverges from Python for any word this long — lts_prep's
                         * base[512] — so truncating crosses no new threshold.) */
                        char part[1024];
                        if (len > sizeof(part) - 1) len = sizeof(part) - 1;
                        memcpy(part, q, len); part[len] = 0;
                        int32_t pb[2048];
                        /* An acronym part is not the tagged word: Python tags `words`,
                         * and an acronym is one entry there however many parts it emits.
                         * Passing the whole token's tag to a part would key a heteronym
                         * branch off a different word. NULL = take the fallback. */
                        int pn = word_ids(p, part, lang_en, NULL, pb, 2048);
                        if (pn > 0) {
                            if (n > 0 && n < 2048) wbuf[n++] = SPACE;
                            for (int k2 = 0; k2 < pn && n < 2048; k2++) wbuf[n++] = pb[k2];
                        }
                    }
                    if (!m) break;
                    q = m + 2;
                }
                wids = wbuf; wn = n;
            } else {
                const char *tpos = (have_pos && tok_widx[ti] < n_wordlist)
                                 ? pos_tags[tok_widx[ti]] : NULL;
                wn = word_ids(p, s, lang_en, tpos, wbuf, 2048); wids = wbuf;
            }
            if (wn < 0) wn = 0;
        }
        /* piece = leading punct + word phones + trailing punct (source order); skip a
         * token that produced nothing; WORD_SEP separates successive non-empty pieces. */
        if (toks[ti].nlead + wn + toks[ti].ntrail <= 0) continue;
        if (nwords > 0) { if (fn >= CAP) return -1; flat[fn++] = SPACE; }
        for (int i = 0; i < toks[ti].nlead; i++)       { if (fn >= CAP) return -1; flat[fn++] = toks[ti].lead[i]; }
        for (int i = 0; i < wn; i++)                   { if (fn >= CAP) return -1; flat[fn++] = wids[i]; }
        for (int i = toks[ti].ntrail - 1; i >= 0; i--) { if (fn >= CAP) return -1; flat[fn++] = toks[ti].trail[i]; }
        nwords++;
    }
    return fn;
}

/* English function words that are not Welsh words, as English evidence for number_lang.
 * Same list and reasoning as bangor_g2p._EN_FUNCTION_WORDS: bangordict.dict carries "of",
 * "the", "for", "it", "not" as English loans with Welsh phonology, so dictionary
 * exclusivity sees them as shared and "Tab 1 of 4" has no evidence; the genuinely Welsh
 * homographs ("at", "is", "to", "was", "her", "be", "can", "had", "call") are absent.
 * Sorted (strcmp order) for the binary search. */
static const char *EN_FUNCTION_WORDS[] = {
    "also", "and", "any", "are", "been", "but", "by", "could", "for", "from", "has", "have",
    "he", "here", "his", "how", "in", "it", "its", "more", "most", "my", "not", "of", "on",
    "our", "she", "should", "some", "than", "that", "the", "their", "then", "there", "these",
    "they", "this", "those", "we", "were", "what", "when", "where", "which", "who", "why",
    "will", "with", "would", "you", "your"};
static int en_function_word(const char *w) {
    int lo = 0, hi = (int)(sizeof(EN_FUNCTION_WORDS) / sizeof(EN_FUNCTION_WORDS[0])) - 1;
    while (lo <= hi) {
        int mid = (lo + hi) / 2, c = strcmp(EN_FUNCTION_WORDS[mid], w);
        if (c == 0) return 1;
        if (c < 0) lo = mid + 1; else hi = mid - 1;
    }
    return 0;
}
static int nl_utf8_next(const unsigned char *s, long *cp) {   /* one code point; bad byte = itself */
    unsigned char c = s[0];
    if (c < 0x80) { *cp = c; return 1; }
    int n = (c >= 0xF0) ? 4 : (c >= 0xE0) ? 3 : (c >= 0xC0) ? 2 : 1;
    if (n == 1) { *cp = c; return 1; }
    long v = c & (0xFF >> (n + 1));
    for (int k = 1; k < n; k++) {
        if ((s[k] & 0xC0) != 0x80) { *cp = c; return 1; }
        v = (v << 6) | (s[k] & 0x3F);
    }
    *cp = v; return n;
}
/* Language for DIGIT verbalisation -- mirrors bangor_g2p._number_lang. Maximal runs of
 * alphabetic code points of the raw text, lowercased, scored by dictionary exclusivity
 * over the same two maps the sentence routing uses, plus the function-word list; one
 * English-only word and no Welsh-only word is enough ("Page 3"), because a Welsh "tri"
 * inside an English interface is unintelligible where an English "three" inside Welsh is
 * not. No evidence -> Welsh, the voice's own language. Separate from, and a lower bar
 * than, the phone routing (_sentence_lang), exactly as in Python. */
static int number_lang(CyPhonemizer *p, const char *text) {
    const unsigned char *s = (const unsigned char *)text;
    int en_only = 0, cy_only = 0;
    size_t i = 0;
    while (s[i]) {
        long cp; int n = nl_utf8_next(s + i, &cp);
        if (!cyp__cp_is_alpha(cp)) { i += (size_t)n; continue; }
        size_t start = i;
        while (s[i] && (n = nl_utf8_next(s + i, &cp), cyp__cp_is_alpha(cp))) i += (size_t)n;
        char raw[512], low[512];
        size_t L = i - start;
        if (L >= sizeof(raw)) continue;                 /* no dictionary word is this long */
        memcpy(raw, s + start, L); raw[L] = 0;
        cyp__lower_strip(raw, low, (int)sizeof(low));
        if (en_function_word(low)) { en_only++; continue; }
        int in_w = wmap_lookup(p->welsh, low) != NULL;
        int in_e = wmap_lookup(p->eng, low) != NULL;
        if (in_e && !in_w) en_only++;
        else if (in_w && !in_e) cy_only++;
    }
    return en_only > cy_only ? CYP_LANG_EN : CYP_LANG_CY;
}
int cyp_text_to_ids_lang(CyPhonemizer *p, const char *text, int lang,
                         int32_t *out, int max_out) {
    if (!p || !text || !out) return -1;
    static char nbuf[65536];
    /* Number language: an explicit lang is the caller's word (Python: `lang or
     * self._number_lang(text)`); CYP_LANG_AUTO detects it from the letters. */
    int num_lang = lang != CYP_LANG_AUTO ? lang : number_lang(p, text);
    cyp_normalize_lang(text, num_lang, nbuf, sizeof(nbuf));  /* numbers/%/abbrev/acronyms/de-shout -> lowercased */
    int32_t flat[8192];
    int fn = phonemize_flat(p, nbuf, lang, flat, (int)(sizeof(flat) / sizeof(flat[0])));
    if (fn < 0) return -1;

    /* interleave: [BOS] + [PAD,id]* + [PAD,EOS] */
    int k = 0;
    if (k >= max_out) return -1;
    out[k++] = BOS;
    for (int i = 0; i < fn; i++) {
        if (k + 1 >= max_out) return -1;
        out[k++] = PAD; out[k++] = flat[i];
    }
    if (k + 1 >= max_out) return -1;
    out[k++] = PAD; out[k++] = EOS;
    return k;
}

int cyp_text_to_ids(CyPhonemizer *p, const char *text, int32_t *out, int max_out) {
    return cyp_text_to_ids_lang(p, text, CYP_LANG_AUTO, out, max_out);
}

/* ---- author-supplied pronunciation (mirrors bangor_g2p.tokens_from_phones) ---- */

/* Whitespace between author-supplied phones is Python's str.isspace(), which is the same
 * 29-codepoint set as its regex \s — so cyp__cp_is_space (cy_normalize.c, where the other
 * character-class predicates live) serves both, and a non-breaking or ideographic space
 * in a <phoneme ph="..."> is skipped rather than reported as an unknown IPA symbol. */
static int cp_is_space(unsigned cp) { return cyp__cp_is_space((long)cp); }

/* An author supplies phones, never structure: pad/bos/eos are phonemes_to_ids's to add
 * (mirrors bangor_g2p._AUTHOR_FORBIDDEN). WORD_SEP is deliberately absent — both
 * alphabet paths split on or skip whitespace, so it can never survive as a token. */
static int is_forbidden_token(const char *t) {
    return (t[0] == '_' || t[0] == '^' || t[0] == '$') && !t[1];
}

int cyp_tokens_from_phones(CyPhonemizer *p, const char *phones, const char *alphabet,
                           int32_t *out, int max_out) {
    if (!p || !phones || !alphabet || !out) return -1;
    int k = 0;
    if (strcmp(alphabet, "bangor") == 0) {
        /* whitespace-separated ASCII tokens, exact and authoritative (Python str.split()) */
        int i = 0;
        while (phones[i]) {
            int j = i;
            unsigned cp = utf8_next(phones, &j);
            if (cp_is_space(cp)) { i = j; continue; }
            int start = i;
            while (phones[i]) {                      /* to the next whitespace codepoint */
                int q = i;
                if (cp_is_space(utf8_next(phones, &q))) break;
                i = q;
            }
            char tok[256];
            int len = i - start;
            if (len >= (int)sizeof(tok)) return -1;
            memcpy(tok, phones + start, (size_t)len);
            tok[len] = 0;
            if (is_forbidden_token(tok)) return -1;
            int id = tok_lookup(p, tok);             /* not in the Bangor inventory -> hard error */
            if (id < 0 || k >= max_out) return -1;
            out[k++] = id;
        }
    } else if (strcmp(alphabet, "ipa") == 0) {
        /* longest-match over the IPA table: every key is 1 or 2 CHARACTERS (test-pinned),
         * which is up to 6 BYTES in UTF-8 ("ɪə"), so the window is measured in codepoints.
         * No forbidden-token check is needed on this path: every table value is one of the
         * 65 phones (tests/test_ssml_primitives.py pins that set), and the only other
         * tokens it can emit are the three marks below. */
        int i = 0;
        while (phones[i]) {
            int j = i;
            unsigned cp1 = utf8_next(phones, &j);   /* j = end of the first codepoint */
            if (cp_is_space(cp1)) { i = j; continue; }
            if (cp1 == 0x2C8 || cp1 == 0x2CC || cp1 == '|') {   /* ˈ ˌ | pass through */
                /* U+02C8 = CB 88, U+02CC = CB 8C (NOT CA AC — an easy transposition, and
                 * one the fixed corpus alone would not have caught). */
                const char *mark = cp1 == 0x2C8 ? "\xcb\x88" : cp1 == 0x2CC ? "\xcb\x8c" : "|";
                int id = tok_lookup(p, mark);
                if (id < 0 || k >= max_out) return -1;
                out[k++] = id;
                i = j;
                continue;
            }
            if (phones[j]) {                        /* try the two-codepoint window first */
                int q = j;
                utf8_next(phones, &q);
                char two[16];
                int len = q - i;
                if (len < (int)sizeof(two)) {
                    memcpy(two, phones + i, (size_t)len);
                    two[len] = 0;
                    int id = ipa_lookup(p, two);
                    if (id >= 0) {
                        if (k >= max_out) return -1;
                        out[k++] = id;
                        i = q;
                        continue;
                    }
                }
            }
            char one[8];
            int len = j - i;
            if (len >= (int)sizeof(one)) return -1;
            memcpy(one, phones + i, (size_t)len);
            one[len] = 0;
            int id = ipa_lookup(p, one);
            if (id < 0 || k >= max_out) return -1;  /* no Bangor equivalent -> hard error */
            out[k++] = id;
            i = j;
        }
    } else {
        return -1;                                  /* only "bangor" and "ipa" are supported */
    }
    return k;
}

/* ---- letter-by-letter spell-out (mirrors bangor_g2p.letter_tokens) ---- */

int cyp_letter_tokens(CyPhonemizer *p, const char *word, int32_t *out, int max_out) {
    if (!p || !word || !out) return -1;
    static char text[65536];
    cyp__lower_strip(word, text, sizeof(text));
    const int semi_id = tok_lookup(p, ";");
    int k = 0, npieces = 0;
    int32_t piece[4096];
    int i = 0;
    while (text[i]) {
        int j = i;
        unsigned cp = utf8_next(text, &j);          /* j = end of this codepoint */
        if (!cyp__cp_is_alnum((long)cp)) { i = j; continue; }
        int pn = -1;                                /* -1 = no piece produced yet */
        /* The eight digraphs are checked BEFORE single letters, so "llan" is ll + a + n.
         * The two-codepoint window collapses to a two-BYTE compare here because every
         * digraph is ASCII and no UTF-8 continuation byte can spell one. */
        if (text[i + 1]) {
            char two[3] = {text[i], text[i + 1], 0};
            for (int t = 0; t < NLNAMES; t++)
                if (LNAMES[t].is_digraph && strcmp(LNAMES[t].w, two) == 0 && p->lname_n[t] > 0) {
                    pn = p->lname_n[t];
                    memcpy(piece, p->lname_ids[t], sizeof(int32_t) * (size_t)pn);
                    i += 2;
                    break;
                }
        }
        if (pn < 0 && cyp__cp_decimal_value((long)cp) >= 0) {
            /* A run of DECIMAL digits reads as ONE number word ("s42c" -> s, forty-two,
             * c). Decimal, not "0-9": Python's guard is isdecimal() and its int() accepts
             * any Nd digits, mixed scripts included (int("٣3") == 33), so the run is
             * collected as digit VALUES and re-spelled in ASCII for the verbaliser. */
            char digits[1024];
            int nd = 0, d = i;
            while (text[d]) {
                int q = d;
                int v = cyp__cp_decimal_value((long)utf8_next(text, &q));
                if (v < 0) break;
                if (nd >= (int)sizeof(digits) - 1) return -1;  /* refuse, never overrun */
                digits[nd++] = (char)('0' + v);
                d = q;
            }
            digits[nd] = 0;
            char words[8192];              /* >=7 bytes per digit for the digit-by-digit branch */
            cyp__num_words_for_run(digits, nd, words);
            pn = phonemize_flat(p, words, CYP_LANG_AUTO, piece,
                                (int)(sizeof(piece) / sizeof(piece[0])));
            if (pn < 0) return -1;
            i = d;
        }
        if (pn < 0) {
            char one[8];
            int len = j - i;
            if (len >= (int)sizeof(one)) return -1;
            memcpy(one, text + i, (size_t)len);
            one[len] = 0;
            for (int t = 0; t < NLNAMES; t++)
                if (!LNAMES[t].is_digraph && strcmp(LNAMES[t].w, one) == 0 && p->lname_n[t] > 0) {
                    pn = p->lname_n[t];
                    memcpy(piece, p->lname_ids[t], sizeof(int32_t) * (size_t)pn);
                    break;
                }
            /* A spelled VOWEL takes its letter name from VSPELLED, the same as a
             * consonant takes its from LNAMES. Mirrors Python's `_CY_VOWEL_SPELLED`
             * branch. Note VSPELLED, not VNAMES: those are the isolated-keystroke
             * lengths, and the two were auditioned separately. */
            if (pn < 0 && len == 1) {
                for (int v = 0; v < NVSPELLED; v++)
                    if (VSPELLED[v].c == one[0] && p->vspell_n[v] > 0) {
                        pn = p->vspell_n[v];
                        memcpy(piece, p->vspell_ids[v], sizeof(int32_t) * (size_t)pn);
                        break;
                    }
            }
            if (pn < 0) {
                /* Accented vowels and anything else with no letter-name entry: the
                 * letter's own lexicon/LTS form, via word_ids — the mirror of Python's
                 * `_word_tokens(ch, "lts", "cy", solo_vowel=False)`. NOT phonemize_flat:
                 * that re-derives solo_vowel from this single character, which is
                 * indistinguishable from an isolated keystroke. lang is hardcoded Welsh
                 * there too, hence lang_en = 0. */
                pn = word_ids(p, one, 0, NULL, piece,
                              (int)(sizeof(piece) / sizeof(piece[0])));
                if (pn < 0) pn = 0;
            }
            i = j;
        }
        /* A SEMICOLON PAUSE between successive pieces, not WORD_SEP and no longer a
         * comma: the owner asked for spell-out slower than WORD_SEP ("commas will do",
         * 2026-07-27), then found the comma still too short to keep adjacent letter names
         * apart ("cê î" ran together) and preferred the semicolon across 31 words the
         * same day. Emitted for every piece after the first even if that piece came out
         * empty, which is what Python's list-of-pieces join does. */
        if (npieces > 0) {
            if (k >= max_out || semi_id < 0) return -1;
            out[k++] = semi_id;
        }
        if (k + pn > max_out) return -1;
        memcpy(out + k, piece, sizeof(int32_t) * (size_t)pn);
        k += pn;
        npieces++;
    }
    return k;
}

const char *cyp_data_version(const CyPhonemizer *p) { return p ? p->data_version : ""; }
int cyp_num_symbols(const CyPhonemizer *p) { (void)p; return 256; }
