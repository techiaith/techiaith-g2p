/* C LTS parity test: cyp_lts(word) must byte-match the Python lts() goldens. */
#include "cy_phonemize.h"
#include "test_common.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Rows scripts/emit_c_data.py writes; a short corpus is a failure, not a pass. */
enum { N_LTS_ROWS = 3565 };

int main(int argc, char **argv) {
    const char *core = argc > 1 ? argv[1] : "..";
    CyPhonemizer *p = cyp_create(core, "accented");
    if (!p) { fprintf(stderr, "cyp_create failed\n"); return 2; }
    char path[4096];
    snprintf(path, sizeof(path), "%s/c/lts_golden.tsv", core);
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); cyp_destroy(p); return 2; }

    char line[16384];
    int pass = 0, total = 0, fail = 0;
    while (fgets(line, sizeof(line), f)) {
        char *tab = strchr(line, '\t');
        if (!tab) continue;
        *tab = 0;
        char word[16384];
        snprintf(word, sizeof(word), "%s", line);
        int32_t exp[2048];
        int en = 0;
        for (char *t = strtok(tab + 1, " \r\n"); t; t = strtok(NULL, " \r\n")) exp[en++] = atoi(t);
        int32_t got[2048];
        int gn = cyp_lts(p, word, got, 2048);
        total++;
        if (gn == en && memcmp(got, exp, sizeof(int32_t) * en) == 0) {
            pass++;
        } else {
            fail++;
            if (fail <= 15) {
                printf("FAIL %-16s got %d ids, exp %d\n", word, gn, en);
                int m = gn < en ? gn : en;
                for (int i = 0; i < m; i++)
                    if (got[i] != exp[i]) { printf("     first diff @%d: got %d exp %d\n", i, got[i], exp[i]); break; }
            }
        }
    }
    fclose(f);
    cyp_destroy(p);
    fail += check_count("LTS", total, N_LTS_ROWS);
    printf("%d/%d C LTS parity\n", pass, total);
    return fail ? 1 : 0;
}
