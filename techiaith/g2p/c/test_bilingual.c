/* C bilingual parity test: cyp_text_to_ids in native + accented modes must
 * byte-match Python BangorG2P(english_mode=…).text_to_ids. */
#include "cy_phonemize.h"
#include "test_common.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Rows scripts/emit_c_data.py writes; a short corpus is a failure, not a pass. */
enum { N_BILINGUAL_ROWS = 150 };

static int run_mode(const char *core, const char *mode) {
    CyPhonemizer *p = cyp_create(core, mode);
    if (!p) { fprintf(stderr, "cyp_create(%s) failed\n", mode); return -1; }
    char path[4096];
    snprintf(path, sizeof(path), "%s/c/bilingual_golden_%s.tsv", core, mode);
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); cyp_destroy(p); return -1; }
    char line[65536];
    int pass = 0, total = 0, fail = 0;
    while (fgets(line, sizeof(line), f)) {
        size_t L = strlen(line);
        while (L && (line[L - 1] == '\n' || line[L - 1] == '\r')) line[--L] = 0;
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
        if (gn == en && memcmp(got, exp, sizeof(int32_t) * en) == 0) pass++;
        else { fail++; if (fail <= 10) printf("  FAIL [%s] %-22s got %d exp %d\n", mode, text, gn, en); }
    }
    fclose(f);
    cyp_destroy(p);
    fail += check_count(mode, total, N_BILINGUAL_ROWS);
    printf("%d/%d C bilingual parity (%s)\n", pass, total, mode);
    return fail;
}

int main(int argc, char **argv) {
    const char *core = argc > 1 ? argv[1] : "..";
    int f1 = run_mode(core, "native");
    int f2 = run_mode(core, "accented");
    return (f1 || f2) ? 1 : 0;
}
