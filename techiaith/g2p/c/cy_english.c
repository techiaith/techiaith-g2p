/* English LTS + language-ID in C — mirrors english_g2p.english_lts and
 * lang_id.classify_word (Workstream P / P7). Self-contained (token strings out;
 * cy_phonemize.c maps them to ids). Byte-parity target vs Python. */
#include "cy_english.h"

#include <ctype.h>
#include <string.h>

static const char *STRESS = "\xcb\x88";   /* ˈ */
#define AE  "\xc3\xa6"   /* æ */
#define AH_ "\xca\x8c"   /* ʌ */
#define OPEN_O "\xc9\x92" /* ɒ */
#define REV_R "\xc9\xb9"  /* ɹ */

typedef struct { const char *g; const char *out[3]; int nout; } Digraph;
static const Digraph DIGRAPH[] = {
    {"tch", {"ch"}, 1}, {"igh", {"ai"}, 1}, {"ough", {"oo"}, 1}, {"augh", {"oo"}, 1},
    {"sh", {"sh"}, 1}, {"ch", {"ch"}, 1}, {"th", {"th"}, 1}, {"ph", {"f"}, 1}, {"ck", {"k"}, 1},
    {"ng", {"ng"}, 1}, {"qu", {"k", "w"}, 2}, {"wh", {"w"}, 1}, {"gh", {0}, 0}, {"kn", {"n"}, 1},
    {"wr", {REV_R}, 1}, {"gn", {"n"}, 1},
    {"ar", {"aa", REV_R}, 2}, {"or", {"oo", REV_R}, 2}, {"er", {"@r"}, 1}, {"ir", {"@r"}, 1},
    {"ur", {"@r"}, 1}, {"ee", {"ii"}, 1}, {"ea", {"ii"}, 1}, {"oo", {"uu"}, 1}, {"oa", {"ou"}, 1},
    {"ai", {"ei"}, 1}, {"ay", {"ei"}, 1}, {"oi", {"oi"}, 1}, {"oy", {"oi"}, 1}, {"ou", {"au"}, 1},
    {"ow", {"au"}, 1}, {"au", {"oo"}, 1}, {"aw", {"oo"}, 1}, {"ew", {"j", "uu"}, 2}, {"ie", {"ii"}, 1},
    {0, {0}, 0}};

static int e_is_vowel(char c) { return c && strchr("aeiouy", c) != NULL; }
static int e_is_cons(char c) { return c && strchr("bcdfghjklmnprstvwxz", c) != NULL; }

/* Skip sentinel: a byte that is neither a vowel, a consonant, nor the start of any
 * digraph. It stands in for a Python str.isalpha() letter that is NOT [a-z] (an
 * accented letter): Python keeps such letters in the filtered word — they map to
 * nothing but still BREAK digraph/diphthong adjacency (naïve -> n æ v e, not n ei v).
 * The main loop falls through to `else i++` on it, emitting nothing. */
#define E_SKIP '\x01'

/* Decode one UTF-8 codepoint at s (len bytes remaining); return the codepoint and
 * write its byte-length to *adv. Returns -1 (adv=1) on a malformed lead byte. */
static long e_utf8_decode(const unsigned char *s, int len, int *adv) {
    unsigned char c = s[0];
    if (c < 0x80) { *adv = 1; return c; }
    if ((c & 0xE0) == 0xC0 && len >= 2 && (s[1] & 0xC0) == 0x80) {
        *adv = 2; return ((long)(c & 0x1F) << 6) | (s[1] & 0x3F);
    }
    if ((c & 0xF0) == 0xE0 && len >= 3 && (s[1] & 0xC0) == 0x80 && (s[2] & 0xC0) == 0x80) {
        *adv = 3; return ((long)(c & 0x0F) << 12) | ((long)(s[1] & 0x3F) << 6) | (s[2] & 0x3F);
    }
    if ((c & 0xF8) == 0xF0 && len >= 4 && (s[1] & 0xC0) == 0x80 && (s[2] & 0xC0) == 0x80
        && (s[3] & 0xC0) == 0x80) {
        *adv = 4;
        return ((long)(c & 0x07) << 18) | ((long)(s[1] & 0x3F) << 12)
             | ((long)(s[2] & 0x3F) << 6) | (s[3] & 0x3F);
    }
    *adv = 1; return -1;
}

/* Matches Python str.isalpha() over the Latin codepoints Welsh/English text uses:
 * ASCII letters, Latin-1 Supplement letters (U+00C0..00FF except × ÷), all of Latin
 * Extended-A (U+0100..017F), and Latin Extended Additional letters (U+1E00..1EFF).
 * These are exactly the ranges the reference filter keeps but leaves unmapped. */
static int e_is_unicode_alpha(long cp) {
    if ((cp >= 'A' && cp <= 'Z') || (cp >= 'a' && cp <= 'z')) return 1;
    if (cp >= 0x00C0 && cp <= 0x00FF) return cp != 0x00D7 && cp != 0x00F7;
    if (cp >= 0x0100 && cp <= 0x017F) return 1;
    if (cp >= 0x1E00 && cp <= 0x1EFF) return 1;
    return 0;
}

static const char *VOWEL(char c) {
    switch (c) { case 'a': return AE; case 'e': return "e"; case 'i': return "i";
        case 'o': return OPEN_O; case 'u': return AH_; case 'y': return "i"; } return "";
}
static const char *LONG(char c) {
    switch (c) { case 'a': return "ei"; case 'e': return "ii"; case 'i': return "ai";
        case 'o': return "ou"; case 'u': return "uu"; case 'y': return "ai"; } return "";
}
static const char *CONS(char c) {
    switch (c) { case 'b': return "b"; case 'c': return "k"; case 'd': return "d"; case 'f': return "f";
        case 'g': return "g"; case 'h': return "hh"; case 'j': return "jh"; case 'k': return "k";
        case 'l': return "l"; case 'm': return "m"; case 'n': return "n"; case 'p': return "p";
        case 'r': return REV_R; case 's': return "s"; case 't': return "t"; case 'v': return "v";
        case 'w': return "w"; case 'z': return "z"; } return "";
}
static int is_vowelish(const char *t) {
    static const char *V[] = {"aa", "oo", "ei", "ii", "ai", "ou", "oi", "au", "uu", "@r", 0};
    for (int i = 0; V[i]; i++) if (strcmp(t, V[i]) == 0) return 1;
    return 0;
}

int cy_english_lts(const char *word, const char **out, int max) {
    /* Mirror Python: w = "".join(c for c in word.lower() if c.isalpha()).
     * Keep [a-z] verbatim; keep every other Unicode letter as an E_SKIP sentinel
     * (unmapped but adjacency-breaking); drop non-letters (digits, punct, marks). */
    char w[512]; int wn = 0;
    const unsigned char *ws = (const unsigned char *)word;
    for (int i = 0; ws[i] && wn < 511;) {
        int adv = 1;
        int rem = 0; while (ws[i + rem]) rem++;   /* bytes remaining */
        long cp = e_utf8_decode(ws + i, rem, &adv);
        i += adv;
        if (cp >= 'A' && cp <= 'Z') w[wn++] = (char)(cp + 32);
        else if (cp >= 'a' && cp <= 'z') w[wn++] = (char)cp;
        else if (e_is_unicode_alpha(cp)) w[wn++] = E_SKIP;
    }
    w[wn] = 0;
    if (wn == 0) return 0;
    int long_last = 0;
    if (wn >= 3 && w[wn - 1] == 'e' && !e_is_vowel(w[wn - 2]) && e_is_vowel(w[wn - 3])) {
        w[--wn] = 0; long_last = 1;
    }
    int no = 0, first_vowel = -1, i = 0;
    while (i < wn) {
        char c = w[i];
        int matched = 0;
        for (const Digraph *d = DIGRAPH; d->g; d++) {
            int gl = (int)strlen(d->g);
            if (strncmp(w + i, d->g, gl) == 0) {
                if (first_vowel < 0)
                    for (int t = 0; t < d->nout; t++) if (is_vowelish(d->out[t])) { first_vowel = no; break; }
                for (int t = 0; t < d->nout; t++) if (no < max) out[no++] = d->out[t];
                i += gl; matched = 1; break;
            }
        }
        if (matched) continue;
        if (e_is_vowel(c)) {
            if (first_vowel < 0) first_vowel = no;
            int is_last = 1;
            for (int j = i + 1; j < wn; j++) if (e_is_vowel(w[j])) { is_last = 0; break; }
            if (no < max) out[no++] = (long_last && is_last) ? LONG(c) : VOWEL(c);
            i++;
        } else if (e_is_cons(c)) {
            char nxt = (i + 1 < wn) ? w[i + 1] : 0;
            /* Soft c/g before e,i,y. Python tests `nxt in "eiy"` where nxt is "" at
             * word end, and "" in "eiy" is True — so word-final c/g ALSO soften
             * (dog -> d ɒ jh, mac -> m æ s). Reproduce that (frozen train phonemizer). */
            int soft_next = (nxt == 'e' || nxt == 'i' || nxt == 'y' || nxt == 0);
            if (c == 'c' && soft_next) { if (no < max) out[no++] = "s"; }
            else if (c == 'g' && soft_next) { if (no < max) out[no++] = "jh"; }
            else if (c == 'x') { if (no < max) out[no++] = "k"; if (no < max) out[no++] = "s"; }
            else { if (no < max) out[no++] = CONS(c); }
            i++;
        } else i++;
    }
    if (first_vowel >= 0 && no < max) {
        for (int j = no; j > first_vowel; j--) out[j] = out[j - 1];
        out[first_vowel] = STRESS; no++;
    }
    return no;
}

/* ---------------- language-ID ---------------- */
static const char *EN_STOP[] = {
    "the", "a", "an", "and", "of", "to", "in", "is", "it", "for", "on", "with", "as", "at", "by",
    "this", "that", "he", "she", "they", "we", "you", "was", "are", "be", "have", "has", "not",
    "but", "or", "from", "which", "what", "when", "where", "how", "all", "can", "will", "my",
    "your", "his", "her", 0};
static const char *CY_STOP[] = {
    "y", "yr", "yn", "ac", "ar", "at", "am", "er", "os", "na", "ni", "fe", "mi", "dy", "ei", "eu",
    "ein", "wrth", "gan", "hyn", "hon", 0};

static int in_list(const char *w, const char *const *list) {
    for (int i = 0; list[i]; i++) if (strcmp(w, list[i]) == 0) return 1;
    return 0;
}
static int count_sub(const char *s, const char *sub) {
    int n = 0, sl = (int)strlen(sub);
    for (const char *p = s; (p = strstr(p, sub)); p += sl) n++;
    return n;
}
static int count_bytes2(const char *s, unsigned char b0, unsigned char b1) {
    int n = 0;
    for (int i = 0; s[i] && s[i + 1]; i++)
        if ((unsigned char)s[i] == b0 && (unsigned char)s[i + 1] == b1) n++;
    return n;
}

int cy_classify_word(const char *word) {
    char w[512]; int wn = 0;
    for (int i = 0; word[i] && wn < 511; i++) {
        char c = word[i]; if (c >= 'A' && c <= 'Z') c += 32; w[wn++] = c;
    }
    w[wn] = 0;
    const char *strip = "'-.,;:!?()\"";
    int a = 0, b = wn;
    while (a < b && strchr(strip, w[a])) a++;
    while (b > a && strchr(strip, w[b - 1])) b--;
    char v[512]; int vn = b - a;
    memcpy(v, w + a, vn); v[vn] = 0;
    if (vn == 0) return 0;
    if (in_list(v, EN_STOP)) return 1;
    if (in_list(v, CY_STOP)) return 0;
    int en = 0, cy = 0;
    for (int i = 0; i < vn; i++) if (strchr("kvxzq", v[i])) en++;
    static const char *ec[] = {"ck", "tion", "sh", "wh", "ght", "qu", 0};
    for (int t = 0; ec[t]; t++) en += count_sub(v, ec[t]);
    static const char *wc[] = {"ll", "dd", "ff", "rh", "ngh", "mh", "nh", "wy", 0};
    for (int t = 0; wc[t]; t++) cy += count_sub(v, wc[t]);
    /* Welsh circumflex accents (UTF-8): â ê î ô û (0xC3 0xA2/AA/AE/B4/BB), ŵ ŷ (0xC5 0xB5/B7) */
    cy += count_bytes2(v, 0xC3, 0xA2) + count_bytes2(v, 0xC3, 0xAA) + count_bytes2(v, 0xC3, 0xAE)
        + count_bytes2(v, 0xC3, 0xB4) + count_bytes2(v, 0xC3, 0xBB)
        + count_bytes2(v, 0xC5, 0xB5) + count_bytes2(v, 0xC5, 0xB7);
    int has_wy = 0, has_aeiou = 0;
    for (int i = 0; i < vn; i++) {
        if (v[i] == 'w' || v[i] == 'y') has_wy = 1;
        if (strchr("aeiou", v[i])) has_aeiou = 1;
    }
    if (has_wy && !has_aeiou) cy += 1;
    return en > cy ? 1 : 0;
}
