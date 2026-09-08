/* C normalize parity test: cyp_normalize_lang(text, lang) must byte-match Python
 * normalize(text, lang) -- the Welsh corpus, then the English one over the same inputs
 * plus the English-only constructs (scripts/emit_c_data.py writes both). */
#include "cy_phonemize.h"
#include "test_common.h"
#include <stdio.h>
#include <string.h>

/* Rows scripts/emit_c_data.py writes; a short corpus is a failure, not a pass. */
enum { N_NORM_ROWS = 2072, N_NORM_EN_ROWS = 2244 };

static int run_corpus(const char *core, const char *file, int lang, int expected) {
    char path[4096];
    snprintf(path, sizeof(path), "%s/c/%s", core, file);
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); return 1; }
    char line[65536];
    int pass = 0, total = 0, fail = 0;
    while (fgets(line, sizeof(line), f)) {
        size_t L = strlen(line);
        while (L && (line[L - 1] == '\n' || line[L - 1] == '\r')) line[--L] = 0;
        char *tab = strchr(line, '\t');
        if (!tab) continue;
        *tab = 0;
        const char *in = line, *exp = tab + 1;
        char got[65536];
        cyp_normalize_lang(in, lang, got, sizeof(got));
        total++;
        if (strcmp(got, exp) == 0) {
            pass++;
        } else {
            fail++;
            if (fail <= 25) printf("FAIL %-18s got [%s] exp [%s]\n", in, got, exp);
        }
    }
    fclose(f);
    fail += check_count(file, total, expected);
    printf("%d/%d C normalize parity (%s)\n", pass, total, file);
    return fail;
}

int main(int argc, char **argv) {
    const char *core = argc > 1 ? argv[1] : "..";
    /* The acronym pass gates on the dictionary headword set; without it every all-caps
     * token letter-spells and the in-vocabulary golden rows ("BBC" -> "bbc") fail. */
    long nvocab = cyp_normalize_load_vocab(core);
    if (nvocab <= 0) { fprintf(stderr, "acronym vocab load failed (core=%s)\n", core); return 2; }
    int fail = run_corpus(core, "normalize_golden.tsv", CYP_LANG_CY, N_NORM_ROWS);
    fail += run_corpus(core, "normalize_golden_en.tsv", CYP_LANG_EN, N_NORM_EN_ROWS);
    return fail ? 1 : 0;
}
