/* C golden-parity test: run the golden vectors through libcy_phonemize and assert
 * byte-identical ids vs the frozen Python goldens (Workstream P / P7, P8-in-C). */
#include "cy_phonemize.h"
#include "test_common.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Rows scripts/emit_c_data.py writes; a short corpus is a failure, not a pass. */
enum { N_GOLDEN_ROWS = 42 };

int main(int argc, char **argv) {
    const char *core = argc > 1 ? argv[1] : "..";
    CyPhonemizer *p = cyp_create(core, "accented");
    if (!p) { fprintf(stderr, "cyp_create failed for core_dir=%s\n", core); return 2; }
    printf("data_version=%s num_symbols=%d\n", cyp_data_version(p), cyp_num_symbols(p));

    char path[4096];
    snprintf(path, sizeof(path), "%s/c/golden.tsv", core);
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); cyp_destroy(p); return 2; }

    char line[16384];
    int pass = 0, total = 0, fail = 0;
    while (fgets(line, sizeof(line), f)) {
        char *tab = strchr(line, '\t');
        if (!tab) continue;
        *tab = 0;
        char text[16384];
        snprintf(text, sizeof(text), "%s", line);

        int32_t exp[8192];
        int en = 0;
        for (char *t = strtok(tab + 1, " \r\n"); t; t = strtok(NULL, " \r\n")) exp[en++] = atoi(t);

        int32_t got[8192];
        int gn = cyp_text_to_ids(p, text, got, 8192);
        total++;
        if (gn == en && memcmp(got, exp, sizeof(int32_t) * en) == 0) {
            pass++;
        } else {
            fail++;
            if (fail <= 10) printf("FAIL %-14s got %d ids, expected %d\n", text, gn, en);
        }
    }
    fclose(f);
    cyp_destroy(p);
    fail += check_count("golden", total, N_GOLDEN_ROWS);
    printf("%d/%d C golden parity\n", pass, total);
    return fail ? 1 : 0;
}
