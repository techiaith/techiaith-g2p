/* C segments parity: cyp_segments(text) must match Python BangorG2P.segments -- kinds, languages
 * and each segment's ids -- over segments_golden.tsv (scripts/emit_c_data.py). Newlines in the
 * input column are escaped as the two characters "\n". */
#include "cy_phonemize.h"
#include "test_common.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { N_SEGMENT_ROWS = 177 };

static void unescape(char *s) {
    char *w = s;
    for (char *r = s; *r; r++) {
        if (r[0] == '\\' && r[1] == 'n') { *w++ = '\n'; r++; }
        else *w++ = *r;
    }
    *w = 0;
}
int main(int argc, char **argv) {
    const char *core = argc > 1 ? argv[1] : "..";
    CyPhonemizer *p = cyp_create(core, "native");
    if (!p) { fprintf(stderr, "cyp_create failed (core=%s)\n", core); return 2; }
    char path[4096];
    snprintf(path, sizeof(path), "%s/c/segments_golden.tsv", core);
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); return 2; }
    static char line[262144], got[262144];
    int pass = 0, total = 0, fail = 0;
    while (fgets(line, sizeof(line), f)) {
        size_t L = strlen(line);
        while (L && (line[L - 1] == '\n' || line[L - 1] == '\r')) line[--L] = 0;
        char *tab = strchr(line, '\t');
        if (!tab) continue;
        *tab = 0;
        const char *exp = tab + 1;
        unescape(line);
        static CypSegment segs[2048];
        static int32_t ids[8192];
        int n = cyp_segments(p, line, CYP_LANG_AUTO, segs, 2048, ids, 8192);
        /* rendering: "kind:num:ph:id id id|kind:num:ph:..." */
        size_t o = 0; got[0] = 0;
        for (int k = 0; k < n; k++) {
            o += (size_t)snprintf(got + o, sizeof(got) - o, "%s%d:%d:%d:", k ? "|" : "", segs[k].boundary, segs[k].number_lang, segs[k].phone_lang);
            for (int i = 0; i < segs[k].count && o < sizeof(got) - 16; i++)
                o += (size_t)snprintf(got + o, sizeof(got) - o, "%s%d", i ? " " : "", ids[segs[k].start + i]);
        }
        total++;
        if (n >= 0 && strcmp(got, exp) == 0) pass++;
        else { fail++; if (fail <= 10) printf("FAIL %-30.30s got [%.80s] exp [%.80s]\n", line, got, exp); }
    }
    fclose(f);
    fail += check_count("segments", total, N_SEGMENT_ROWS);
    printf("%d/%d C segments parity\n", pass, total);
    cyp_destroy(p);
    return fail ? 1 : 0;
}
