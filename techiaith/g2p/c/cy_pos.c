/* Averaged-perceptron POS tagger, mirroring techiaith/g2p/pos_tagger.py.
 *
 * WHY INTEGER-ONLY. tests/diff_fuzz_c_parity.py asserts Python and C emit byte-identical
 * phoneme ids. A float score would differ in the last bit between Python's doubles and
 * C's on some platform and some input, and the harness would surface it as a phoneme
 * divergence long after the cause was forgotten. Weights arrive pre-averaged and
 * quantised from scripts/gen_pos_data.py; nothing here divides.
 *
 * THREE THINGS MUST MATCH THE PYTHON EXACTLY, and the fuzz fails if any drifts:
 *   1. the feature byte strings built in build_features(),
 *   2. integer accumulation of int16 weights into an int32 score,
 *   3. argmax with ties going to the LOWEST tag index. Not a detail: a word whose
 *      features all miss scores zero for every tag, and without a fixed rule Python's
 *      loop and this one could pick different tags, then cascade through tag history.
 *
 * Words arrive already lowercased (welsh_normalize.normalize() lowercases before
 * _segment), so there is no case folding here -- and therefore no Unicode case tables
 * in C, which is what makes this port tractable at all.
 */
#include "cy_pos.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAGIC          "TPOS"
#define FORMAT_VERSION 1
/* Matches pos_tagger._MAX_FEATURE. A longer feature is dropped on BOTH sides:
 * truncating here while Python kept the full string would be a divergence that only a
 * pathological input reveals. */
#define MAX_FEATURE 1000
#define FEAT_BUF    (MAX_FEATURE + 64)
#define MAX_TAGS    64
#define N_FEATURES  19

struct CyPos {
    unsigned char *raw;               /* whole file, owned */
    int ntags;
    char tag[MAX_TAGS][16];           /* copied out: the file does not nul-terminate */
    unsigned int nfeat;
    const unsigned char *offsets;     /* nfeat+1 little-endian u32, into raw */
    const unsigned char *blob;
    unsigned int blob_len;
};

static int rd_u16(const unsigned char *p) { return p[0] | (p[1] << 8); }
static unsigned int rd_u32(const unsigned char *p) {
    return (unsigned int)p[0] | ((unsigned int)p[1] << 8)
         | ((unsigned int)p[2] << 16) | ((unsigned int)p[3] << 24);
}
static int rd_i16(const unsigned char *p) {
    int v = p[0] | (p[1] << 8);
    return v >= 0x8000 ? v - 0x10000 : v;
}

CyPos *cy_pos_load(const char *dir, const char *lang) {
    char path[1024];
    snprintf(path, sizeof(path), "%s/pos_%s.bin", dir, lang);
    FILE *f = fopen(path, "rb");
    if (!f) return NULL;
    if (fseek(f, 0, SEEK_END) != 0) { fclose(f); return NULL; }
    long len = ftell(f);
    if (len < 20) { fclose(f); return NULL; }
    if (fseek(f, 0, SEEK_SET) != 0) { fclose(f); return NULL; }
    unsigned char *raw = (unsigned char *)malloc((size_t)len);
    if (!raw) { fclose(f); return NULL; }
    size_t got = fread(raw, 1, (size_t)len, f);
    fclose(f);
    if (got != (size_t)len) { free(raw); return NULL; }

    long off = 0;
    if (memcmp(raw, MAGIC, 4) != 0) { free(raw); return NULL; }
    off = 4;
    int version = rd_u16(raw + off); off += 2;
    off += 2;                                   /* scale, informational on this side */
    if (version != FORMAT_VERSION) { free(raw); return NULL; }
    int ll = raw[off]; off += 1 + ll;           /* lang string; known from the filename */
    if (off + 2 > len) { free(raw); return NULL; }

    CyPos *p = (CyPos *)calloc(1, sizeof(*p));
    if (!p) { free(raw); return NULL; }
    p->raw = raw;
    p->ntags = rd_u16(raw + off); off += 2;
    if (p->ntags <= 0 || p->ntags > MAX_TAGS) { cy_pos_free(p); return NULL; }
    for (int i = 0; i < p->ntags; i++) {
        if (off >= len) { cy_pos_free(p); return NULL; }
        int tl = raw[off]; off += 1;
        if (tl <= 0 || tl >= (int)sizeof(p->tag[0]) || off + tl > len) {
            cy_pos_free(p); return NULL;
        }
        memcpy(p->tag[i], raw + off, (size_t)tl);
        p->tag[i][tl] = '\0';
        off += tl;
    }
    if (off + 8 > len) { cy_pos_free(p); return NULL; }
    p->nfeat = rd_u32(raw + off); off += 4;
    p->blob_len = rd_u32(raw + off); off += 4;
    if (off + 4L * ((long)p->nfeat + 1) > len) { cy_pos_free(p); return NULL; }
    p->offsets = raw + off;
    off += 4L * ((long)p->nfeat + 1);
    if (off + (long)p->blob_len > len) { cy_pos_free(p); return NULL; }
    p->blob = raw + off;
    return p;
}

void cy_pos_free(CyPos *p) {
    if (!p) return;
    free(p->raw);
    free(p);
}

/* Ascending byte order, shorter-prefix-first -- exactly Python's sort of bytes keys,
 * which gen_pos_data.export() used to lay the blob out. memcmp on the common prefix
 * then length, NOT strcmp: keys may contain any byte and are not nul-terminated. */
static int key_cmp(const unsigned char *a, int alen, const char *b, int blen) {
    int n = alen < blen ? alen : blen;
    int c = memcmp(a, b, (size_t)n);
    if (c) return c;
    return alen - blen;
}

/* Binary search the blob in place. No hash map is built at load: one map per language
 * would cost ~80 bytes of malloc overhead per feature, ~40 MB for both, against the
 * voice extension's 375 MB jetsam limit with a 91 MB CoreML model already resident. */
static const unsigned char *lookup(const CyPos *p, const char *key, int klen, int *nw) {
    unsigned int lo = 0, hi = p->nfeat;
    while (lo < hi) {
        unsigned int mid = lo + (hi - lo) / 2;
        unsigned int o = rd_u32(p->offsets + 4 * mid);
        const unsigned char *e = p->blob + o;
        int elen = rd_u16(e);
        int c = key_cmp(e + 2, elen, key, klen);
        if (c == 0) { *nw = e[2 + elen]; return e + 3 + elen; }
        if (c < 0) lo = mid + 1; else hi = mid;
    }
    return NULL;
}

/* Build the 19 feature strings for position i. Mirrors PosTagger.features byte for
 * byte. Suffix/prefix slices are by BYTE, matching Python's w[-3:] on a bytes object;
 * splitting mid-UTF-8 is deliberate and harmless because the feature is an opaque key
 * and both sides slice identically -- the only property that matters. */
static int build_features(char buf[N_FEATURES][FEAT_BUF], int len_out[N_FEATURES],
                          const char *const *words, int n, int i,
                          const char *p1, const char *p2) {
    const char *w   = words[i];
    const char *pw  = i > 0     ? words[i - 1] : "<s>";
    const char *ppw = i > 1     ? words[i - 2] : "<s2>";
    const char *nw  = i + 1 < n ? words[i + 1] : "</s>";
    const char *nnw = i + 2 < n ? words[i + 2] : "</s2>";
    int wl = (int)strlen(w);
    int k = 0;

    /* one/two-part concatenations, written through a helper-free pattern so the exact
     * byte sequence is visible next to the Python it mirrors */
#define EMIT1(pfx, a) do {                                                            \
        int al = (int)strlen(a);                                                      \
        int pl = (int)sizeof(pfx) - 1;                                                \
        if (pl + al <= MAX_FEATURE) {                                                 \
            memcpy(buf[k], pfx, (size_t)pl);                                          \
            memcpy(buf[k] + pl, a, (size_t)al);                                       \
            len_out[k] = pl + al; k++;                                                \
        } else { len_out[k] = -1; k++; }                                              \
    } while (0)
#define EMIT_SLICE(pfx, base, blen) do {                                              \
        int pl = (int)sizeof(pfx) - 1;                                                \
        memcpy(buf[k], pfx, (size_t)pl);                                              \
        memcpy(buf[k] + pl, base, (size_t)(blen));                                    \
        len_out[k] = pl + (blen); k++;                                                \
    } while (0)
#define EMIT_JOIN(pfx, a, b) do {                                                     \
        int al = (int)strlen(a), bl = (int)strlen(b);                                 \
        int pl = (int)sizeof(pfx) - 1;                                                \
        if (pl + al + 1 + bl <= MAX_FEATURE) {                                        \
            memcpy(buf[k], pfx, (size_t)pl);                                          \
            memcpy(buf[k] + pl, a, (size_t)al);                                       \
            buf[k][pl + al] = '|';                                                    \
            memcpy(buf[k] + pl + al + 1, b, (size_t)bl);                              \
            len_out[k] = pl + al + 1 + bl; k++;                                       \
        } else { len_out[k] = -1; k++; }                                              \
    } while (0)

    memcpy(buf[k], "b", 1); len_out[k] = 1; k++;      /* bias */
    EMIT1("w=", w);
    EMIT_SLICE("suf1=", w + (wl >= 1 ? wl - 1 : 0), wl >= 1 ? 1 : 0);
    EMIT_SLICE("suf2=", w + (wl >= 2 ? wl - 2 : 0), wl >= 2 ? 2 : wl);
    EMIT_SLICE("suf3=", w + (wl >= 3 ? wl - 3 : 0), wl >= 3 ? 3 : wl);
    EMIT_SLICE("suf4=", w + (wl >= 4 ? wl - 4 : 0), wl >= 4 ? 4 : wl);
    EMIT_SLICE("pre1=", w, wl >= 1 ? 1 : 0);
    EMIT_SLICE("pre3=", w, wl >= 3 ? 3 : wl);
    EMIT1("p1=", p1);
    EMIT1("p2=", p2);
    EMIT_JOIN("p1p2=", p1, p2);
    EMIT1("pw=", pw);
    EMIT1("ppw=", ppw);
    EMIT1("nw=", nw);
    EMIT1("nnw=", nnw);
    EMIT_JOIN("p1|w=", p1, w);
    EMIT_JOIN("pw|w=", pw, w);
    EMIT_JOIN("w|nw=", w, nw);
    {   /* shape: has-digit, has-hyphen. Python tests the raw bytes, so do the same. */
        int d = 0, h = 0;
        for (const char *q = w; *q; q++) {
            unsigned char c = (unsigned char)*q;
            if (c >= '0' && c <= '9') d = 1;
            if (c == '-') h = 1;
        }
        int pl = (int)sizeof("shape=") - 1;
        memcpy(buf[k], "shape=", (size_t)pl);
        buf[k][pl] = d ? 'D' : '-';
        buf[k][pl + 1] = h ? 'H' : '-';
        len_out[k] = pl + 2; k++;
    }
#undef EMIT1
#undef EMIT_SLICE
#undef EMIT_JOIN
    return k;
}

int cy_pos_tag(const CyPos *p, const char *const *words, int n, const char **out) {
    if (!p || n < 0) return -1;
    const char *p1 = "<s>", *p2 = "<s2>";
    for (int i = 0; i < n; i++) {
        char buf[N_FEATURES][FEAT_BUF];
        int flen[N_FEATURES];
        int nf = build_features(buf, flen, words, n, i, p1, p2);
        int score[MAX_TAGS];
        for (int t = 0; t < p->ntags; t++) score[t] = 0;
        for (int j = 0; j < nf; j++) {
            if (flen[j] < 0) continue;                 /* over MAX_FEATURE: dropped */
            int nw = 0;
            const unsigned char *ws = lookup(p, buf[j], flen[j], &nw);
            if (!ws) continue;
            for (int m = 0; m < nw; m++) {
                int t = ws[3 * m];
                if (t < p->ntags) score[t] += rd_i16(ws + 3 * m + 1);
            }
        }
        int best = 0;
        for (int t = 1; t < p->ntags; t++)
            if (score[t] > score[best]) best = t;      /* ties -> lowest index */
        out[i] = p->tag[best];
        p2 = p1; p1 = p->tag[best];
    }
    return 0;
}

const char *cy_pos_tag_at(const CyPos *p, const char *const *words, int n, int i) {
    if (!p || i < 0 || i >= n) return NULL;
    const char **all = (const char **)malloc(sizeof(char *) * (size_t)n);
    if (!all) return NULL;
    const char *r = NULL;
    if (cy_pos_tag(p, words, n, all) == 0) r = all[i];
    free(all);
    return r;
}
