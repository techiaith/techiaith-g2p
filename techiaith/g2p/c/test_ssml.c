/* C parity test for the SSML token-level primitives: the forced-language override,
 * letter-by-letter spell-out, and author-supplied phones must all byte-match the Python
 * reference (bangor_g2p.phonemize(lang=...), letter_tokens, tokens_from_phones).
 *
 * Corpora (scripts/emit_c_data.py, native english_mode — the only mode whose word
 * routing consults lang):
 *   lang_golden.tsv    text<TAB>(-|cy|en)<TAB>interleaved ids
 *   spell_golden.tsv   word<TAB>phone-token ids
 *   phones_golden.tsv  alphabet<TAB>phones<TAB>phone-token ids
 * A missing or unparseable corpus is a hard failure, not a silent 0/0.
 */
#include "cy_phonemize.h"
#include "test_common.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Rows scripts/emit_c_data.py writes for each corpus; see test_common.h for why a
 * short corpus has to be a failure rather than a quiet "0/0 ... parity" pass. */
enum { N_LANG_ROWS = 21, N_SPELL_ROWS = 15, N_PHONES_ROWS = 8 };

/* Parse a space-separated id list into exp[]; returns the count (-1 if it overflows). */
static int parse_ids(char *s, int32_t *exp, int max) {
    int n = 0;
    for (char *t = strtok(s, " \r\n"); t; t = strtok(NULL, " \r\n")) {
        if (n >= max) return -1;
        exp[n++] = (int32_t)atoi(t);
    }
    return n;
}

static void report(const char *name, int32_t *got, int gn, int32_t *exp, int en,
                   const char *label, int *pass, int *fail) {
    if (gn == en && (en == 0 || memcmp(got, exp, sizeof(int32_t) * (size_t)en) == 0)) {
        (*pass)++;
        return;
    }
    (*fail)++;
    if (*fail <= 10) {
        printf("  FAIL %s [%s] got %d ids:", name, label, gn);
        for (int i = 0; i < gn && i < 40; i++) printf(" %d", got[i]);
        printf("\n              exp %d ids:", en);
        for (int i = 0; i < en && i < 40; i++) printf(" %d", exp[i]);
        printf("\n");
    }
}

/* --- forced language ------------------------------------------------------------ */
static int run_lang(CyPhonemizer *p, const char *core) {
    char path[4096];
    snprintf(path, sizeof(path), "%s/c/lang_golden.tsv", core);
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); return -1; }
    char line[65536];
    int pass = 0, total = 0, fail = 0;
    while (fgets(line, sizeof(line), f)) {
        char *t1 = strchr(line, '\t');
        if (!t1) continue;
        *t1 = 0;
        char *t2 = strchr(t1 + 1, '\t');
        if (!t2) { fprintf(stderr, "malformed lang row: %s\n", line); fclose(f); return -1; }
        *t2 = 0;
        const char *text = line;      /* NUL-terminated at the first tab, above */
        const char *ls = t1 + 1;
        int lang = strcmp(ls, "cy") == 0 ? CYP_LANG_CY
                 : strcmp(ls, "en") == 0 ? CYP_LANG_EN
                 : strcmp(ls, "-") == 0 ? CYP_LANG_AUTO : -1;
        if (lang < 0) { fprintf(stderr, "unknown lang %s\n", ls); fclose(f); return -1; }
        int32_t exp[8192];
        int en = parse_ids(t2 + 1, exp, 8192);
        if (en < 0) { fprintf(stderr, "id overflow: %s\n", text); fclose(f); return -1; }
        int32_t got[8192];
        /* lang=- must go through the ORIGINAL entry point, so the wrapper is exercised
         * (a lang argument that broke it would otherwise pass unnoticed here). */
        int gn = lang == CYP_LANG_AUTO ? cyp_text_to_ids(p, text, got, 8192)
                                      : cyp_text_to_ids_lang(p, text, lang, got, 8192);
        total++;
        char label[320];
        snprintf(label, sizeof(label), "%.8s|%.300s", ls, text);  /* name the input in failures */
        report("lang", got, gn, exp, en, label, &pass, &fail);
    }
    fclose(f);
    fail += check_count("lang", total, N_LANG_ROWS);
    printf("%d/%d C lang parity\n", pass, total);
    return fail;
}

/* --- letter-by-letter spell-out ------------------------------------------------- */
static int run_spell(CyPhonemizer *p, const char *core) {
    char path[4096];
    snprintf(path, sizeof(path), "%s/c/spell_golden.tsv", core);
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); return -1; }
    char line[65536];
    int pass = 0, total = 0, fail = 0;
    while (fgets(line, sizeof(line), f)) {
        char *tab = strchr(line, '\t');
        if (!tab) continue;
        *tab = 0;
        const char *word = line;      /* NUL-terminated at the tab, above */
        int32_t exp[8192];
        int en = parse_ids(tab + 1, exp, 8192);
        if (en < 0) { fprintf(stderr, "id overflow: %s\n", word); fclose(f); return -1; }
        int32_t got[8192];
        int gn = cyp_letter_tokens(p, word, got, 8192);
        total++;
        report("spell", got, gn, exp, en, word, &pass, &fail);
    }
    fclose(f);
    fail += check_count("spell", total, N_SPELL_ROWS);
    printf("%d/%d C spell parity\n", pass, total);
    return fail;
}

/* --- author-supplied phones ----------------------------------------------------- */
static int run_phones(CyPhonemizer *p, const char *core) {
    char path[4096];
    snprintf(path, sizeof(path), "%s/c/phones_golden.tsv", core);
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); return -1; }
    char line[65536];
    int pass = 0, total = 0, fail = 0;
    while (fgets(line, sizeof(line), f)) {
        char *t1 = strchr(line, '\t');
        if (!t1) continue;
        *t1 = 0;
        char *t2 = strchr(t1 + 1, '\t');
        if (!t2) { fprintf(stderr, "malformed phones row: %s\n", line); fclose(f); return -1; }
        *t2 = 0;
        const char *alphabet = line, *phones = t1 + 1;  /* both NUL-terminated above */
        int32_t exp[8192];
        int en = parse_ids(t2 + 1, exp, 8192);
        if (en < 0) { fprintf(stderr, "id overflow: %s\n", phones); fclose(f); return -1; }
        int32_t got[8192];
        int gn = cyp_tokens_from_phones(p, phones, alphabet, got, 8192);
        total++;
        report("phones", got, gn, exp, en, phones, &pass, &fail);
    }
    fclose(f);
    fail += check_count("phones", total, N_PHONES_ROWS);
    printf("%d/%d C phones parity\n", pass, total);
    return fail;
}

/* --- rejection cases ------------------------------------------------------------ */
/* Not corpus-driven: a TSV of id sequences cannot express "this must be refused", and
 * refusal is the whole point of the feature — an author's typo has to surface as an
 * error the API can turn into a 400, never as silently mangled audio. Mirrors
 * tests/test_ssml_primitives.py's three rejection tests. */
static int run_reject(CyPhonemizer *p) {
    static const struct { const char *phones, *alphabet, *why; } BAD[] = {
        {"b zzz n", "bangor", "token outside the inventory"},
        {"b\xC7\x83n", "ipa", "IPA symbol with no Bangor equivalent"},   /* "bǃn" */
        {"_", "bangor", "structural token _"},
        {"^", "bangor", "structural token ^"},
        {"$", "bangor", "structural token $"},
        {"ban", "x-sampa", "unsupported alphabet"},
    };
    int n = (int)(sizeof(BAD) / sizeof(BAD[0])), pass = 0, fail = 0;
    for (int i = 0; i < n; i++) {
        int32_t out[256];
        int r = cyp_tokens_from_phones(p, BAD[i].phones, BAD[i].alphabet, out, 256);
        if (r < 0) pass++;
        else { fail++; printf("  FAIL reject [%s/%s] %s: accepted, returned %d ids\n",
                              BAD[i].alphabet, BAD[i].phones, BAD[i].why, r); }
    }
    printf("%d/%d C phones rejection\n", pass, n);
    return fail;
}

int main(int argc, char **argv) {
    const char *core = argc > 1 ? argv[1] : "..";
    CyPhonemizer *p = cyp_create(core, "native");
    if (!p) { fprintf(stderr, "cyp_create(native) failed\n"); return 2; }
    int f1 = run_lang(p, core);
    int f2 = run_spell(p, core);
    int f3 = run_phones(p, core);
    int f4 = run_reject(p);
    cyp_destroy(p);
    if (f1 < 0 || f2 < 0 || f3 < 0) return 2;   /* corpus missing or malformed */
    return (f1 || f2 || f3 || f4) ? 1 : 0;
}
