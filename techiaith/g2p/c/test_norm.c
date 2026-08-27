/* C normalize parity test: cyp_normalize(text) must byte-match Python normalize(). */
#include "cy_phonemize.h"
#include "test_common.h"

#include <stdio.h>
#include <string.h>

/* Rows scripts/emit_c_data.py writes; a short corpus is a failure, not a pass. */
enum { N_NORM_ROWS = 1986 };

int main(int argc, char **argv) {
    const char *core = argc > 1 ? argv[1] : "..";
    /* The acronym pass gates on the dictionary headword set; without it every all-caps
     * token letter-spells and the in-vocabulary golden rows ("BBC" -> "bbc") fail. */
    long nvocab = cyp_normalize_load_vocab(core);
    if (nvocab <= 0) { fprintf(stderr, "acronym vocab load failed (core=%s)\n", core); return 2; }
    char path[4096];
    snprintf(path, sizeof(path), "%s/c/normalize_golden.tsv", core);
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); return 2; }

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
        cyp_normalize(in, got, sizeof(got));
        total++;
        if (strcmp(got, exp) == 0) {
            pass++;
        } else {
            fail++;
            if (fail <= 15) printf("FAIL %-18s got [%s] exp [%s]\n", in, got, exp);
        }
    }
    fclose(f);
    fail += check_count("normalize", total, N_NORM_ROWS);
    printf("%d/%d C normalize parity\n", pass, total);
    return fail ? 1 : 0;
}
