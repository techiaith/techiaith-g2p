/* C word-marks parity: cyp_segment_spans, cyp_word_marks and cyp_word_starts must match Python
 * BangorG2P.segment_spans / word_marks / word_starts over word_marks_golden.tsv
 * (scripts/emit_c_data.py): text TAB lang TAB "a:e|..." TAB "seg:word:a:e|..." TAB "1 21|1 15",
 * offsets in UTF-8 bytes, "\n" in the text escaped as the two characters. Then the ABI's edges:
 * overflow, a bad lang, empty input, and a piece cut just after a WORD_SEP. */
#include "cy_phonemize.h"
#include "test_common.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

enum { N_WORD_MARK_ROWS = 245 };

static void unescape(char *s) {
    char *w = s;
    for (char *r = s; *r; r++) {
        if (r[0] == '\\' && r[1] == 'n') { *w++ = '\n'; r++; }
        else *w++ = *r;
    }
    *w = 0;
}
static int next_field(char **cur, char **field) {   /* split at the next tab; 0 if none */
    char *tab = strchr(*cur, '\t');
    if (!tab) return 0;
    *tab = 0; *field = *cur; *cur = tab + 1;
    return 1;
}
static int fail_edge(const char *what) { printf("FAIL edge: %s\n", what); return 1; }

int main(int argc, char **argv) {
    const char *core = argc > 1 ? argv[1] : "..";
    CyPhonemizer *p = cyp_create(core, "native");
    if (!p) { fprintf(stderr, "cyp_create failed (core=%s)\n", core); return 2; }
    char path[4096];
    snprintf(path, sizeof(path), "%s/c/word_marks_golden.tsv", core);
    FILE *f = fopen(path, "r");
    if (!f) { perror(path); return 2; }
    static char line[262144], got[262144];
    static CypSegment segs[2049];
    static int32_t ids[32768];
    static int ss[2049], se[2049], starts[8192];
    static CypWordMark marks[8192];
    int pass = 0, total = 0, fail = 0;
    while (fgets(line, sizeof(line), f)) {
        size_t L = strlen(line);
        while (L && (line[L - 1] == '\n' || line[L - 1] == '\r')) line[--L] = 0;
        char *cur = line, *text, *lang_s, *exp_spans, *exp_marks;
        if (!next_field(&cur, &text) || !next_field(&cur, &lang_s) || !next_field(&cur, &exp_spans) ||
            !next_field(&cur, &exp_marks)) continue;
        const char *exp_starts = cur;
        unescape(text);
        int lang = !strcmp(lang_s, "cy") ? CYP_LANG_CY : !strcmp(lang_s, "en") ? CYP_LANG_EN : CYP_LANG_AUTO;
        int nsp = cyp_segment_spans(p, text, lang, ss, se, 2049);
        int nm = cyp_word_marks(p, text, lang, marks, 8192);
        int nseg = cyp_segments(p, text, lang, segs, 2049, ids, 32768);
        /* the same three columns, rendered as the golden renders them */
        size_t o = 0; got[0] = 0;
        for (int k = 0; k < nsp; k++)
            o += (size_t)snprintf(got + o, sizeof(got) - o, "%s%d:%d", k ? "|" : "", ss[k], se[k]);
        o += (size_t)snprintf(got + o, sizeof(got) - o, "\t");
        for (int k = 0; k < nm; k++)
            o += (size_t)snprintf(got + o, sizeof(got) - o, "%s%d:%d:%d:%d", k ? "|" : "",
                                  marks[k].seg, marks[k].word, marks[k].src_start, marks[k].src_end);
        o += (size_t)snprintf(got + o, sizeof(got) - o, "\t");
        int bad_starts = 0;
        for (int k = 0; k < nseg && o < sizeof(got) - 64; k++) {
            int nw = cyp_word_starts(ids + segs[k].start, segs[k].count, starts, 8192);
            if (nw < 0) bad_starts = 1;
            if (k) got[o++] = '|';
            for (int w = 0; w < nw && o < sizeof(got) - 16; w++)
                o += (size_t)snprintf(got + o, sizeof(got) - o, "%s%d", w ? " " : "", starts[w]);
            got[o] = 0;
        }
        static char exp[262144];
        snprintf(exp, sizeof(exp), "%s\t%s\t%s", exp_spans, exp_marks, exp_starts);
        total++;
        /* the spans are parallel to cyp_segments: same count */
        if (nsp >= 0 && nm >= 0 && nseg == nsp && !bad_starts && strcmp(got, exp) == 0) pass++;
        else {
            fail++;
            if (fail <= 10) printf("FAIL %-30.30s [%s] segs=%d spans=%d marks=%d\n   got [%.160s]\n   exp [%.160s]\n",
                                   text, lang_s, nseg, nsp, nm, got, exp);
        }
    }
    fclose(f);
    fail += check_count("word marks", total, N_WORD_MARK_ROWS);
    printf("%d/%d C word marks parity\n", pass, total);

    /* --- the ABI's edges ---------------------------------------------------------------- */
    int edges = 0, edge_fail = 0;
    const char *two = "Bore da. Sut wyt ti?";          /* 2 segments, 5 marks */
    edges++; if (cyp_segment_spans(p, two, CYP_LANG_AUTO, ss, se, 2) != 2) edge_fail += fail_edge("spans fit exactly");
    edges++; if (cyp_segment_spans(p, two, CYP_LANG_AUTO, ss, se, 1) != -1) edge_fail += fail_edge("spans overflow is -1");
    edges++; if (cyp_segment_spans(p, two, 3, ss, se, 2) != -1) edge_fail += fail_edge("spans bad lang is -1");
    edges++; if (cyp_segment_spans(p, "", CYP_LANG_AUTO, ss, se, 2) != 0) edge_fail += fail_edge("spans of empty text");
    edges++; if (cyp_segment_spans(p, " \n\t ", CYP_LANG_AUTO, ss, se, 2) != 0) edge_fail += fail_edge("spans of whitespace");
    edges++; if (cyp_word_marks(p, two, CYP_LANG_AUTO, marks, 5) != 5) edge_fail += fail_edge("marks fit exactly");
    edges++; if (cyp_word_marks(p, two, CYP_LANG_AUTO, marks, 4) != -1) edge_fail += fail_edge("marks overflow is -1");
    edges++; if (cyp_word_marks(p, two, -1, marks, 8) != -1) edge_fail += fail_edge("marks bad lang is -1");
    edges++; if (cyp_word_marks(p, "", CYP_LANG_AUTO, NULL, 0) != 0) edge_fail += fail_edge("marks of empty text");
    {   /* [BOS] PAD a PAD WS PAD b PAD EOS: two words, the second starting after the WORD_SEP */
        const int32_t seg2[] = {1, 0, 20, 0, 3, 0, 21, 0, 2};
        /* a piece cut just after a WORD_SEP (CySynth.chunk): one word, nothing after the SEP */
        const int32_t cut[] = {1, 0, 20, 0, 3, 2};
        const int32_t empty[] = {1, 0, 2};
        edges++; if (cyp_word_starts(seg2, 9, starts, 2) != 2 || starts[0] != 1 || starts[1] != 5) edge_fail += fail_edge("starts of two words");
        edges++; if (cyp_word_starts(seg2, 9, starts, 1) != -1) edge_fail += fail_edge("starts overflow is -1");
        edges++; if (cyp_word_starts(cut, 6, starts, 2) != 1 || starts[0] != 1) edge_fail += fail_edge("starts of a cut piece");
        edges++; if (cyp_word_starts(empty, 3, starts, 2) != 0) edge_fail += fail_edge("starts of an empty segment");
        edges++; if (cyp_word_starts(empty, 3, NULL, 0) != 0) edge_fail += fail_edge("starts of an empty segment, no buffer");
    }
    printf("%d/%d C word marks edges\n", edges - edge_fail, edges);
    fail += edge_fail;
    cyp_destroy(p);
    return fail ? 1 : 0;
}
