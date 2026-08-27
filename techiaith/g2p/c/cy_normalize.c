/* Welsh text normalization in C — mirrors welsh_normalize.py (Workstream P / P7).
 * cyp_num_to_welsh (cardinals 0..999,999,999) + cyp_normalize (numbers, %, decimals,
 * &, abbreviations, acronym spell-out). Byte-parity target vs the Python reference. */
#include "cy_phonemize.h"
#include "cy_emoji_data.h"

#include <ctype.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>

static const char *UNITS[10] = {"", "un", "dau", "tri", "pedwar", "pump", "chwech", "saith", "wyth", "naw"};
/* The traditional (vigesimal) two-digit forms are NOT here: general cardinals are decimal
 * (see two_digit below) and the clock has its own MINUTE_TRAD / HOUR_TRAD tables, so a
 * third copy would be dead weight. welsh_normalize._VIG_UNDER_20 keeps them, with the BTC
 * quote and the provenance, if the question is ever reopened for cardinals. */
/* 7 and 8 take "gant". BTC style guide, "Treiglo ai peidio": "Ni threiglir enwau heblaw
 * 'cant', 'punt' a 'ceiniog' yn feddal ar ol 'saith' ac 'wyth'" -- so those three DO.
 * Mirrors welsh_normalize._HUNDREDS, where the full reasoning lives. */
static const char *HUNDREDS[10] = {"", "cant", "dau gant", "tri chant", "pedwar cant", "pum cant", "chwe chant", "saith gant", "wyth gant", "naw cant"};

/* The same BTC rule for the sites that build "<numeral> <noun>" at runtime: the noun is
 * soft-mutated iff the word immediately before it is "saith" or "wyth". Mirrors
 * welsh_normalize._soft_after_saith_wyth. */
static int ends_with_saith_or_wyth(const char *s) {
    size_t n = strlen(s);
    if (n >= 5 && !strcmp(s + n - 5, "saith")) return (n == 5) || s[n - 6] == ' ';
    if (n >= 4 && !strcmp(s + n - 4, "wyth")) return (n == 4) || s[n - 5] == ' ';
    return 0;
}

/* Mirrors welsh_normalize._SAITH_WYTH_SOFT / _soft_after_saith_wyth -- a table, not
 * inline branches, so the two implementations cannot drift on which nouns are in it. */
static const struct { const char *plain, *soft; } SAITH_WYTH_SOFT[] = {
    {"cant", "gant"}, {"punt", "bunt"}, {"ceiniog", "geiniog"}, {NULL, NULL}};
static const char *soft_after_saith_wyth(const char *numeral, const char *noun) {
    if (!ends_with_saith_or_wyth(numeral)) return noun;
    for (int i = 0; SAITH_WYTH_SOFT[i].plain; i++)
        if (!strcmp(SAITH_WYTH_SOFT[i].plain, noun)) return SAITH_WYTH_SOFT[i].soft;
    return noun;
}

/* BTC "Y lluosog ynteu'r unigol", third branch: for 11 and up, where it is "arferol rhoi'r
 * hyn a gyfrifir yn y canol", use "o" + plural -- "un ar ddeg o filltiroedd", not
 * "un filltir ar ddeg". Mirrors welsh_normalize._MID_NUMERAL_PLURAL / _counted_noun, where
 * the verbatim rule and what is derived are set out. The three traditional counted nouns we
 * emit, not the metric loanwords. */
static const struct { const char *sing, *plur; } MID_NUMERAL_PLURAL[] = {
    {"punt", "bunnoedd"}, {"ceiniog", "geiniogau"}, {"blynedd", "flynyddoedd"},
    {NULL, NULL}};

/* A vigesimal numeral with a joiner, i.e. one whose customary form has a middle for the
 * noun to sit in ("un filltir ar ddeg"). A simple word (ugain, deugain, can) has none. */
static int is_compound_numeral(const char *num) {
    char pad[640];
    snprintf(pad, sizeof(pad), " %s ", num);
    return strstr(pad, " ar ") != NULL || strstr(pad, " a ") != NULL;
}

/* "<numeral> <noun>" or "<numeral> o <plural>", per BTC's three branches. */
/* `cap` is the size of `b`. Hardcoding 700 truncated silently for a numeral built by
 * cyp__num_words_for_run, whose worst case is ~3.6 KB (a pathological digit run read
 * digit-by-digit) -- snprintf is safe, but the result was a clipped word. */
static void counted_noun(char *b, size_t cap, const char *numeral, long n,
                         const char *singular) {
    if (n >= 11 && is_compound_numeral(numeral)) {
        for (int i = 0; MID_NUMERAL_PLURAL[i].sing; i++)
            if (!strcmp(MID_NUMERAL_PLURAL[i].sing, singular)) {
                snprintf(b, cap, "%s o %s", numeral, MID_NUMERAL_PLURAL[i].plur);
                return;
            }
    }
    snprintf(b, cap, "%s %s", numeral, soft_after_saith_wyth(numeral, singular));
}


static void app(char *b, const char *w) {
    if (!w[0]) return;
    if (b[0]) strcat(b, " ");
    strcat(b, w);
}

/* DECIMAL two-digit forms, for the contexts BTC excepts from the vigesimal rule
 * ("rhifau cyn ac ar ol pwyntiau degol", "rhifau blynyddoedd"). Mirrors
 * welsh_normalize._TENS_DEC / _two_digit_dec, where the verbatim exception list lives. */
static const char *TENS_DEC[10] = {"", "", "dau ddeg", "tri deg", "pedwar deg", "pum deg",
                                   "chwe deg", "saith deg", "wyth deg", "naw deg"};
static void two_digit_dec(char *b, int tu) {
    if (tu == 0) return;
    if (tu < 10) { app(b, UNITS[tu]); return; }
    if (tu == 10) { app(b, "deg"); return; }
    if (tu < 20) { app(b, "un deg"); app(b, UNITS[tu - 10]); return; }
    app(b, TENS_DEC[tu / 10]);
    if (tu % 10) app(b, UNITS[tu % 10]);
}
/* cardinal_dec -- a cardinal in the DECIMAL register for the contexts BTC excepts -- was
 * DELETED here on 2026-07-28. It indexed HUNDREDS[n / 100], a 10-entry array, with no bound
 * on n; see pass_decimal, its only caller, for what that did and what replaced it. Python
 * keeps the name as a delegate because BTC excepts decimals in their own right and that is
 * where the exception must reappear if the vigesimal question is reopened; a C copy that
 * only forwards is dead weight, the same call made for the vigesimal tables. */
/* 0-99 for general cardinals: the DECIMAL register, i.e. exactly two_digit_dec.
 *
 * REVERTED 2026-07-27 with the Python side. Making every cardinal vigesimal was too wide a
 * reading of BTC; the clock keeps the traditional numerals (HOUR_TRAD / MINUTE_TRAD are
 * separate tables) and that is where the question belonged. VIG_UNDER_20 / VIG_DECADE /
 * VIG_JOIN below are retained as documentation of the traditional forms and are no longer
 * reached by cardinals -- this function is the single line to change if it is reopened. */
static void two_digit(char *b, int tu) {
    two_digit_dec(b, tu);
}
static void below_thousand(char *b, int n) {
    if (n / 100) app(b, HUNDREDS[n / 100]);
    if (n % 100) two_digit(b, n % 100);
}


/* "cant"/"gant"/"chant" -> "can"/"gan"/"chan" directly before ANY noun we emit, not only
 * before a scale word. BTC style guide, "Y ffurfiau cyswllt": "Defnyddir y ffurfiau
 * cyswllt 'pum' (5), 'chwe' (6) a 'can' (100) yn gyffredinol ee ... 'can metr', 'can
 * merch'." Mirrors welsh_normalize._reduce_cant, where the full quote lives. Only a
 * TRAILING cant reduces, which is what keeps "150 m" as "cant pum deg metr". */
static void reduce_cant(char *s) {
    size_t n = strlen(s);
    if (n >= 5 && !strcmp(s + n - 5, "chant")) { strcpy(s + n - 5, "chan"); return; }
    if (n >= 4 && !strcmp(s + n - 4, "gant")) { strcpy(s + n - 4, "gan"); return; }
    if (n >= 4 && !strcmp(s + n - 4, "cant")) { strcpy(s + n - 4, "can"); return; }
}
/* Trailing pump/chwech/cant -> pum/chwe/can, for a numeral phrase that ends directly before a
 * noun. Mirrors welsh_normalize._reduce_connected. A DECIMAL numeral has no single value to
 * look up in MASC_BEFORE_NOUN -- "3.5 kg" ends in "pump", which reduces before a noun exactly
 * as a bare 5 would -- so the connected-form rule has to be positional, about the word that
 * touches the noun. That is already what reduce_cant does for "cant"; this is BTC's other two.
 * Owner 2026-07-28: "Tri pwynt pum cilogram". */
static void reduce_connected(char *s) {
    size_t n = strlen(s);
    if (n >= 4 && !strcmp(s + n - 4, "pump")) { strcpy(s + n - 4, "pum"); return; }
    if (n >= 6 && !strcmp(s + n - 6, "chwech")) { strcpy(s + n - 6, "chwe"); return; }
    reduce_cant(s);
}

/* Feminine-agreeing scale multipliers (mil/miliwn are feminine) — mirrors
 * welsh_normalize._MIL_SPECIAL / _MILIWN_SPECIAL, where the reasoning lives.
 * Language decision 2026-07-26: 1 takes "un" ("1000" -> "un mil", not bare "mil"), and
 * 5/6 take their pre-nominal reductions "pum"/"chwe" rather than falling through to
 * below_thousand's citation "pump"/"chwech".
 * Language decision 2026-07-27 (Welsh Government BTC style guide): "miliwn" and "biliwn"
 * are NEVER mutated, because m -> f and b -> f are the same soft mutation and a spoken
 * "dwy filiwn" cannot be told apart from two million and two billion — so miliwn's 2 is
 * "dwy miliwn" (feminine numeral, no mutation). "mil" is not covered by that guide and
 * nothing else mutates to "fil", so "dwy fil" keeps its mutation. */
static const char *mil_special(int m) {
    switch (m) { case 1: return "un mil"; case 2: return "dwy fil"; case 3: return "tair mil";
        case 4: return "pedair mil"; case 5: return "pum mil"; case 6: return "chwe mil";
        case 10: return "deg mil"; } return NULL;
}
static const char *miliwn_special(int m) {
    switch (m) { case 1: return "un miliwn"; case 2: return "dwy miliwn"; case 3: return "tair miliwn";
        case 4: return "pedair miliwn"; case 5: return "pum miliwn"; case 6: return "chwe miliwn";
        case 10: return "deg miliwn"; } return NULL;
}
/* "biliwn" is MASCULINE where mil/miliwn are feminine ("dau biliwn", not "dwy biliwn") --
 * a deliberate asymmetry the owner closed: the no-mutation rule above is what keeps 2m and
 * 2bn apart in speech, so the numeral's gender carries no disambiguating load.
 * ADDED 2026-07-28. The billion multiplier was previously assembled as
 * num_to_welsh(billions) + " biliwn", which bypassed scale() and so missed both the
 * connected forms and reduce_cant: "pump biliwn", "chwech biliwn", "cant biliwn". The
 * first is the same defect piper-lleol issue #3 raises against "pump miliwn" -- fixed for
 * miliwn then, missed for biliwn because that path did not share this code.
 * Owner 2026-07-28: "Mae angen newid 'pump' i 'pum' o flaen enw fel 'biliwn'". */
static const char *biliwn_special(int m) {
    switch (m) { case 1: return "un biliwn"; case 2: return "dau biliwn"; case 3: return "tri biliwn";
        case 4: return "pedwar biliwn"; case 5: return "pum biliwn"; case 6: return "chwe biliwn";
        case 10: return "deg biliwn"; } return NULL;
}
static void scale(char *b, int mult, const char *word, const char *(*special)(int)) {
    const char *sp = special(mult);
    if (sp) { app(b, sp); return; }
    char body[256] = "";
    below_thousand(body, mult);
    if (mult % 100 == 0) reduce_cant(body);
    app(b, body); app(b, word);
}

void cyp_num_to_welsh(long n, char *out, int max) {
    (void)max;
    out[0] = 0;
    if (n < 0) { strcpy(out, "minws "); char t[512]; cyp_num_to_welsh(-n, t, 512); strcat(out, t); return; }
    if (n == 0) { strcpy(out, "sero"); return; }
    if (n == 10) { strcpy(out, "deg"); return; }
    /* 18 nines, mirroring welsh_normalize._CARDINAL_CEILING: the widest run that fits a
     * long, and what cyp__num_words_for_run already caps digit runs at. Was 999,999,999
     * until 2026-07-28, which made a literal "1000000000" read "un dim dim dim dim dim dim
     * dim dim dim" -- nine "dim"s -- while "£3bn" said "tri biliwn". Same amount, and only
     * the magnitude-suffix spelling escaped, because only scaled_cardinal named billions. */
    if (n > 999999999999999999L) {
        char s[32]; snprintf(s, sizeof(s), "%ld", n);
        for (int i = 0; s[i]; i++) app(out, s[i] == '0' ? "dim" : UNITS[s[i] - '0']);
        return;
    }
    long billions = n / 1000000000L, r1 = n % 1000000000L;
    long millions = r1 / 1000000, r = r1 % 1000000, thousands = r / 1000, rest = r % 1000;
    if (billions) {
        /* No signed-off Welsh word above "biliwn" -- that one took a GPC attestation (see
         * scaled_cardinal) -- so a multiplier of 1000+ stacks "biliwn" rather than
         * inventing "triliwn". Recursion is bounded at depth 2: n of <=18 digits makes
         * this argument <=9 digits, which takes the tiers below. */
        if (billions <= 999) scale(out, (int)billions, "biliwn", biliwn_special);
        else { char bb[512]; cyp_num_to_welsh(billions, bb, sizeof(bb)); app(out, bb); app(out, "biliwn"); }
    }
    if (millions) scale(out, (int)millions, "miliwn", miliwn_special);
    if (thousands) scale(out, (int)thousands, "mil", mil_special);
    if (rest) below_thousand(out, (int)rest);
    if (!out[0]) strcpy(out, "sero");
}

/* ---------------- normalize ---------------- */
/* Word char for boundary tests. Python's re \b runs on Unicode: ASCII alnum/_ plus
 * Unicode *letters* (â ê … Ŵ) are \w, but symbols/punctuation (— … £ ’ · ° × ÷) are
 * NOT. Byte-level isalnum can't see multibyte letters, so we decode the actual
 * codepoint at the boundary and test letter-ness — matching Python's \b exactly
 * (e.g. "âee" has no boundary before "ee", but "dog—" does after "dog"). */
static int cp_is_word(long cp) {
    if (cp < 0x80) return isalnum((int)cp) || cp == '_';
    if (cp >= 0x00C0 && cp <= 0x00FF) return cp != 0x00D7 && cp != 0x00F7; /* À-ÿ minus × ÷ */
    if (cp >= 0x0100 && cp <= 0x017F) return 1;   /* Latin Extended-A (all letters) */
    if (cp >= 0x0180 && cp <= 0x024F) return 1;   /* Latin Extended-B (letters) */
    if (cp >= 0x1E00 && cp <= 0x1EFF) return 1;   /* Latin Extended Additional (letters) */
    return 0;  /* other non-ASCII (— … £ ’ ​ · ° etc.) are not \w */
}
/* Python's \s (str patterns) for one codepoint. Verified by enumeration to be exactly
 * the 29 codepoints re matches and str.isspace() accepts — the two sets are identical.
 * NOT just ASCII: a non-breaking space between a number and its unit ("5<NBSP>km") is
 * standard typesetting and reaches us from real text.
 * Shared with cy_phonemize.c (cyp_tokens_from_phones skips whitespace the same way). */
int cyp__cp_is_space(long cp) {
    if (cp == 0x20 || (cp >= 0x09 && cp <= 0x0D) || (cp >= 0x1C && cp <= 0x1F)) return 1;
    if (cp == 0x85 || cp == 0xA0 || cp == 0x1680) return 1;
    if (cp >= 0x2000 && cp <= 0x200A) return 1;
    if (cp == 0x2028 || cp == 0x2029 || cp == 0x202F || cp == 0x205F || cp == 0x3000) return 1;
    return 0;
}
/* Decode the UTF-8 codepoint that STARTS at s[j] (j is a codepoint boundary). */
static long cp_at(const char *s, int j) {
    unsigned char c = (unsigned char)s[j];
    if (c < 0x80) return c;
    if ((c & 0xE0) == 0xC0 && s[j + 1]) return ((long)(c & 0x1F) << 6) | ((unsigned char)s[j + 1] & 0x3F);
    if ((c & 0xF0) == 0xE0 && s[j + 1] && s[j + 2])
        return ((long)(c & 0x0F) << 12) | (((unsigned char)s[j + 1] & 0x3F) << 6) | ((unsigned char)s[j + 2] & 0x3F);
    if ((c & 0xF8) == 0xF0 && s[j + 1] && s[j + 2] && s[j + 3])
        return ((long)(c & 0x07) << 18) | (((unsigned char)s[j + 1] & 0x3F) << 12)
             | (((unsigned char)s[j + 2] & 0x3F) << 6) | ((unsigned char)s[j + 3] & 0x3F);
    return 0xFFFD;
}
/* Decode the codepoint that ENDS just before byte index i (i > 0): scan back over
 * UTF-8 continuation bytes (0x80..0xBF) to the lead byte, then decode forward. */
static long cp_before(const char *s, int i) {
    int k = i - 1;
    while (k > 0 && ((unsigned char)s[k] & 0xC0) == 0x80) k--;
    return cp_at(s, k);
}
/* Boundary helpers: is the char AFTER index j (a codepoint start) a word char?
 * is the char BEFORE index i a word char? Match Python's \b over Unicode letters. */
static int word_after(const char *s, int j) { return s[j] && cp_is_word(cp_at(s, j)); }
static int word_before(const char *s, int i) { return i > 0 && cp_is_word(cp_before(s, i)); }
/* Defined below, next to the digit-sequence pass that named it; forward declared here
 * for pass_percent's trailing separator. */
static int digit_seq_sep(const char *s, int j);
/* Defined below (the Unicode-\s helper); forward declared for the passes above it whose
 * whitespace loops were ASCII-only until the 2026-08-21 sweep (percent, math/degree,
 * ampersand, date-month) -- "8<NBSP>x<NBSP>9" was the ONE divergence the 1.5M-case
 * differential still found. */
static int re_space_len(const char *s, int j);

/* Acronyms spell out as isolated lower-case LETTERS (the G2P names each letter,
 * language-aware); the old letter-name-word table ("bi", "èc", "ce"...) is gone —
 * those words weren't in any lexicon, so LTS/CMUdict mangled them. Consecutive
 * digits inside a code read as ONE number (A55 -> "a pum deg pump"), matching
 * welsh_normalize._spell_acronym. Leading zeros strip like Python int() ("007"
 * -> "saith"); a stripped run longer than 18 digits mirrors num_to_welsh's
 * digit-by-digit branch (n > 999,999,999) without overflowing a long.
 * Non-static: pass_unit below and cy_phonemize.c's cyp_letter_tokens read digit runs
 * the same way, and one shared implementation cannot drift from itself. */
int cyp__num_words_for_run(const char *s, int len, char *out) {
    int z = 0;
    while (z < len - 1 && s[z] == '0') z++;   /* keep at least one digit */
    s += z; len -= z;
    if (len > 18) {
        out[0] = 0;
        for (int i = 0; i < len; i++) app(out, s[i] == '0' ? "dim" : UNITS[s[i] - '0']);
        return (int)strlen(out);
    }
    long v = 0;
    for (int i = 0; i < len; i++) v = v * 10 + (s[i] - '0');
    cyp_num_to_welsh(v, out, 512);
    return (int)strlen(out);
}

/* Widest comma-stripped digit run we compact into a local buffer; longer runs are read
 * digit-by-digit straight from the source, which needs no buffer. Matches CUR_DIGITS on
 * the currency path. Any run over 18 digits reads digitwise on both sides anyway, so where
 * this bound bites, the two implementations already agree. */
#define NUM_RUN_DIGITS 512

/* Digit run -> words, THOUSANDS COMMAS TOLERATED, written straight into the caller's
 * buffer. Returns the length written.
 *
 * ADDED 2026-07-28 to replace parse_int_strip_commas + cyp_num_to_welsh at the percent,
 * decimal and integer passes. That pair built a `long` from the run and silently OVERFLOWED
 * it at 19 digits: "9999999999999999999" wrapped negative, so cyp_num_to_welsh took its
 * n < 0 branch and read "minws wyth pedwar pedwar chwech saith..." where Python says
 * nineteen "naw"s. It bypassed the >18-digit guard cyp__num_words_for_run has had all
 * along, which is exactly why the guard could not save it. Pre-existing, and invisible to
 * make check because no parity row is anywhere near that long.
 *
 * Writing into the caller's buffer rather than a temp also retires three `char nb[512]`
 * locals that a digitwise run could have overflowed once the overflow stopped truncating
 * the output for them. */
static int num_words_run_commas(const char *s, int len, char *out) {
    char d[NUM_RUN_DIGITS];
    int nd = 0;
    for (int i = 0; i < len; i++) {
        if (s[i] == ',') continue;
        if (nd >= (int)sizeof(d) - 1) {          /* absurd run: digitwise, no buffer needed */
            out[0] = 0;
            for (int k = 0; k < len; k++)
                if (s[k] != ',') app(out, s[k] == '0' ? "dim" : UNITS[s[k] - '0']);
            return (int)strlen(out);
        }
        d[nd++] = s[i];
    }
    d[nd] = 0;
    return cyp__num_words_for_run(d, nd, out);
}

/* Magnitude suffix on a currency amount: in "£5m" the "m" is MILLION, not metres.
 * Case-insensitive, and it must sit directly against the amount. Declared up here
 * because pass_acronym needs it too — see pound_magnitude_token. Mirrors
 * welsh_normalize._MAGNITUDE_ZEROS. */
static const struct { const char *sym; int zeros; } MAGNITUDE[] = {
    {"bn", 9}, {"m", 6}, {"k", 3}, {NULL, 0}};

/* "£5M": the [A-Z0-9] run at s[i..j) is a currency amount whose magnitude suffix
 * happens to be upper case, so the acronym pass would claim it as a code before
 * pass_currency ever sees it ("£5M" -> "£pump m": the amount spelled as a number, "M"
 * as a letter, £ left dangling). The test is deliberately narrow — digits, then exactly
 * one magnitude suffix, with the £ (and at most the single space pass_currency allows)
 * directly before — so "£5MB" and a bare "5M" are still codes. No two of {bn, m, k} can
 * match the same tail, so the first hit is the only hit and this stays equivalent to
 * Python's for/else. Mirrors welsh_normalize._pound_magnitude_token. */
static int pound_magnitude_token(const char *s, int i, int j) {
    int len = j - i, sl = 0;
    for (int u = 0; MAGNITUDE[u].sym; u++) {
        int L = (int)strlen(MAGNITUDE[u].sym);
        if (len > L && strncasecmp(s + j - L, MAGNITUDE[u].sym, (size_t)L) == 0) { sl = L; break; }
    }
    if (!sl) return 0;
    for (int t = i; t < j - sl; t++) if (!isdigit((unsigned char)s[t])) return 0;
    int p = i;
    if (p > 0 && s[p - 1] == ' ') p--;
    return p >= 2 && (unsigned char)s[p - 2] == 0xC2 && (unsigned char)s[p - 1] == 0xA3;
}

/* "7PM": the [A-Z0-9] run at s[i..j) is an upper-case clock form -- digits plus a bare
 * meridiem marker -- which the acronym pass would otherwise claim as a code before
 * pass_time ever runs ("7PM" -> "saith p·m", and "3:00PM" collapsed outright because
 * "00PM" was eaten). Same stand-aside shape as pound_magnitude_token above.
 *
 * Two admissions, mirroring pound's narrowness. A 1-2 digit run <= 23 is a colonless
 * hour ("7PM", "10YB" -- and "00PM", the minute fragment of "3:00PM", is 0). A run of
 * 24-59 stands aside only as a minute field: exactly two digits, [0-5] first, directly
 * after "digit:" or "digit." ("3:45PM", "7.30PM"). Everything else stays a code:
 * standalone "PM" (the Prime Minister) has no digits, "45PM" alone fails both tests,
 * and the UPPERCASE DOTTED forms ("7P.M.") never reach here at all -- the [A-Z0-9]
 * token there is "7P", not marker-shaped, so they stay spelled out: a recorded
 * limitation, identical in both implementations. Mirrors
 * welsh_normalize._clock_marker_token. */
static int clock_marker_token(const char *s, int i, int j) {
    int len = j - i;
    if (len < 3 || len > 4) return 0;
    const char *mk = s + j - 2;
    if (!((mk[0] == 'A' && mk[1] == 'M') || (mk[0] == 'P' && mk[1] == 'M') ||
          (mk[0] == 'Y' && (mk[1] == 'B' || mk[1] == 'P' || mk[1] == 'H')))) return 0;
    for (int t = i; t < j - 2; t++) if (!isdigit((unsigned char)s[t])) return 0;
    /* 1-2 digits by the len gate above; same inline read as pass_time's hv (atoin is
     * defined further down the file). */
    int v = len == 3 ? s[i] - '0' : (s[i] - '0') * 10 + (s[i + 1] - '0');
    if (v <= 23) return 1;
    return len == 4 && s[i] >= '0' && s[i] <= '5'
        && i >= 2 && (s[i - 1] == ':' || s[i - 1] == '.') && isdigit((unsigned char)s[i - 2]);
}

/* one abbreviation rule */
typedef struct { const char *pat; int ci; int wb_end; int opt_dot; const char *repl; } Abbrev;
static const Abbrev ABBREV[] = {
    {"e.e.", 1, 0, 0, "er enghraifft"},
    {"ee", 1, 1, 0, "er enghraifft"},
    {"h.y.", 1, 0, 0, "hynny yw"},
    {"hy", 1, 1, 0, "hynny yw"},
    {"ayyb", 1, 1, 0, "ac yn y blaen"},
    {"ayb", 1, 1, 0, "ac yn y blaen"},
    {"d.s.", 1, 0, 0, "dalier sylw"},
    {"Dr", 0, 1, 1, "doctor"},
    {"Mrs", 0, 1, 1, "musus"},
    {"Mr", 0, 1, 1, "mistar"},
    {"Ms", 0, 1, 1, "ms"},
    {NULL, 0, 0, 0, NULL}};

static int ci_streq(const char *a, const char *b, int len, int ci) {
    for (int i = 0; i < len; i++) {
        char x = a[i], y = b[i];
        if (ci) { x = (char)tolower((unsigned char)x); y = (char)tolower((unsigned char)y); }
        if (x != y) return 0;
    }
    return 1;
}

static void pass_abbrev(const char *in, char *out, const Abbrev *ab) {
    int i = 0, o = 0, pl = (int)strlen(ab->pat);
    while (in[i]) {
        int wb_before = !word_before(in, i);
        if (wb_before && ci_streq(in + i, ab->pat, pl, ab->ci)) {
            int end = i + pl;
            int ok = 1;
            if (ab->wb_end) { /* \b after: next char non-word (or end) */
                if (word_after(in, end)) ok = 0;
            }
            if (ok) {
                int adv = pl;
                if (ab->opt_dot && in[end] == '.') adv++;
                strcpy(out + o, ab->repl); o += (int)strlen(ab->repl);
                i += adv;
                continue;
            }
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

/* ---- the acronym vocabulary gate — mirrors welsh_normalize._acronym_vocab ----
 *
 * Letter-spelling is an OOV fallback, not the reading of every all-caps token: an
 * all-caps token whose lowercase form the pronunciation dictionaries know is a real
 * word (or a lexicalised acronym — they carry "bbc", "nato", "dvla" with spoken
 * forms), and the right reading is the word itself. Only a token the dictionaries do
 * NOT know keeps the spell-out (HMS, WJEC, USB).
 *
 * Membership rule, byte-identical to the Python side's _VOCAB_HEADWORD regex
 * ([A-Za-z]{2,} at line start, terminated by space/tab/\r/end-of-line, lowercased):
 * see _acronym_vocab in welsh_normalize.py, which reads the same four files.
 *
 * This is the one normalizer table too large to generate as C source the way the
 * emoji table is (140k headwords, ~1.2 MB that the data directory already ships), so
 * it is loaded at runtime instead: cyp_create loads it for every phonemize caller, and
 * a bare-cyp_normalize harness (test_norm.c, the ctypes tests) must call
 * cyp_normalize_load_vocab itself. Forgetting is loud, not silent: normalize_golden.tsv
 * pins in-vocabulary rows ("BBC" -> "bbc"), which an unloaded (empty) vocab fails. */
static char *g_avocab_pool = NULL;      /* every headword, lowercased, NUL-terminated */
static const char **g_avocab = NULL;    /* sorted, deduped pointers into the pool */
static int g_avocab_n = 0;

static int avocab_cmp(const void *a, const void *b) {
    return strcmp(*(const char *const *)a, *(const char *const *)b);
}

long cyp_normalize_load_vocab(const char *core_dir) {
    static const char *dicts[] = {"bangordict.dict", "bangordict.xx.dict",
                                  "bangordict.en.dict", "cmudict.dict"};
    free(g_avocab_pool); g_avocab_pool = NULL;
    free(g_avocab); g_avocab = NULL;
    g_avocab_n = 0;
    size_t pool_cap = 1u << 21, pool_len = 0;   /* ~1.2 MB of headwords fits first try */
    size_t n_cap = 1u << 16, n = 0;
    char *pool = (char *)malloc(pool_cap);
    size_t *offs = (size_t *)malloc(n_cap * sizeof *offs);
    if (!pool || !offs) { free(pool); free(offs); return -1; }
    char line[65536];
    for (int d = 0; d < 4; d++) {
        char path[4096];
        snprintf(path, sizeof(path), "%s/data/geiriadur-ynganu-bangor/%s", core_dir, dicts[d]);
        FILE *f = fopen(path, "r");
        if (!f) { free(pool); free(offs); return -1; }
        while (fgets(line, sizeof(line), f)) {
            int k = 0;
            while ((line[k] >= 'A' && line[k] <= 'Z') || (line[k] >= 'a' && line[k] <= 'z')) k++;
            if (k < 2) continue;
            if (line[k] != ' ' && line[k] != '\t' && line[k] != '\r' &&
                line[k] != '\n' && line[k] != 0) continue;   /* not a whole first field */
            if (pool_len + (size_t)k + 1 > pool_cap) {
                pool_cap *= 2;
                char *np = (char *)realloc(pool, pool_cap);
                if (!np) { fclose(f); free(pool); free(offs); return -1; }
                pool = np;
            }
            if (n == n_cap) {
                n_cap *= 2;
                size_t *no = (size_t *)realloc(offs, n_cap * sizeof *no);
                if (!no) { fclose(f); free(pool); free(offs); return -1; }
                offs = no;
            }
            offs[n++] = pool_len;
            for (int t = 0; t < k; t++)
                pool[pool_len++] = (char)tolower((unsigned char)line[t]);
            pool[pool_len++] = 0;
        }
        fclose(f);
    }
    const char **ptrs = (const char **)malloc((n ? n : 1) * sizeof *ptrs);
    if (!ptrs) { free(pool); free(offs); return -1; }
    for (size_t t = 0; t < n; t++) ptrs[t] = pool + offs[t];
    free(offs);
    qsort(ptrs, n, sizeof *ptrs, avocab_cmp);
    size_t m = 0;
    for (size_t t = 0; t < n; t++)
        if (m == 0 || strcmp(ptrs[m - 1], ptrs[t]) != 0) ptrs[m++] = ptrs[t];
    g_avocab_pool = pool;
    g_avocab = ptrs;
    g_avocab_n = (int)m;
    return (long)m;
}

static int avocab_has(const char *w) {
    int lo = 0, hi = g_avocab_n - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        int c = strcmp(w, g_avocab[mid]);
        if (c == 0) return 1;
        if (c < 0) hi = mid - 1; else lo = mid + 1;
    }
    return 0;
}

static void pass_acronym(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        char c = in[i];
        int is_au = (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
        int wb_before = !word_before(in, i);
        if (is_au && wb_before) {
            int j = i;
            while (in[j] && ((in[j] >= 'A' && in[j] <= 'Z') || (in[j] >= '0' && in[j] <= '9'))) j++;
            int len = j - i;
            int wb_after = !word_after(in, j);
            int uppers = 0, digits = 0;
            for (int t = i; t < j; t++) {
                if (in[t] >= 'A' && in[t] <= 'Z') uppers++;
                else digits++;   /* the char class is [A-Z0-9] */
            }
            /* >=2 caps (BBC, HMS) — or one cap plus a digit, covering codes read
             * letter-by-letter (A55, 3D, S4C). Pure digits fall to the number pass, a
             * £-prefixed magnitude amount ("£5M") falls to pass_currency, and an
             * upper-case clock form ("7PM", the "00PM" of "3:00PM") falls to pass_time. */
            if (len >= 2 && wb_after && (uppers >= 2 || (uppers >= 1 && digits >= 1))
                && !pound_magnitude_token(in, i, j)
                && !clock_marker_token(in, i, j)) {
                /* The vocabulary gate (see cyp_normalize_load_vocab above): a pure-letter
                 * token whose lowercase form the dictionaries know is a word merely
                 * capitalised — read it, don't spell it. Digit-bearing tokens (S4C, A55)
                 * are codes and never reach the gate. The 128 cap is safe, not a parity
                 * hole: the longest dictionary headword is 58 bytes, so a longer token
                 * cannot be in the vocabulary on either side. Mirrors the
                 * tok.lower()-in-_acronym_vocab() branch of _spell_acronym. */
                if (digits == 0 && len < 128) {
                    char low[128];
                    for (int t = 0; t < len; t++)
                        low[t] = (char)tolower((unsigned char)in[i + t]);
                    low[len] = 0;
                    if (avocab_has(low)) {
                        memcpy(out + o, low, (size_t)len);
                        o += len;
                        i = j;
                        continue;
                    }
                }
                /* Consecutive letters are joined by ACRONYM_JOIN (U+00B7, UTF-8 C2 B7) so
                 * the G2P knows they came from an acronym; a digit run breaks the join and
                 * becomes a number word (S4C -> "s pedwar c", its letters left isolated and
                 * therefore Welsh-named). Mirrors welsh_normalize._spell_acronym. */
                int t = i, first = 1, prev_letter = 0;
                while (t < j) {
                    int cur_letter = !(in[t] >= '0' && in[t] <= '9');
                    if (!first) {
                        if (prev_letter && cur_letter) {
                            out[o++] = (char)0xC2;
                            out[o++] = (char)0xB7;
                        } else {
                            out[o++] = ' ';
                        }
                    }
                    first = 0;
                    if (!cur_letter) {
                        int ds = t;
                        while (t < j && in[t] >= '0' && in[t] <= '9') t++;
                        o += cyp__num_words_for_run(in + ds, t - ds, out + o);
                    } else {
                        out[o++] = (char)tolower((unsigned char)in[t]);
                        t++;
                    }
                    prev_letter = cur_letter;
                }
                i = j;
                continue;
            }
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

/* parse_int_strip_commas was DELETED 2026-07-28: it built a long from a digit run and
 * silently overflowed at 19 digits. num_words_run_commas replaced all three of its callers
 * (percent, decimal, integer) and never forms an integer at all. */

static void pass_percent(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        if (isdigit((unsigned char)in[i])) {
            int j = i;
            while (isdigit((unsigned char)in[j]) || in[j] == ',') j++;
            int ws = j;   /* \s* is Unicode (re_space_len), not ASCII -- the sweep */
            for (int sl; (sl = re_space_len(in, ws)); ) ws += sl;
            if (in[ws] == '%') {
                o += num_words_run_commas(in + i, j - i, out + o);
                strcpy(out + o, " y cant"); o += 7;
                /* "50%x" -> "... y cant x": the "%" sits between the digits and the
                 * letter, so the digit/letter splitter never sees a boundary here.
                 * Mirrors _percent_repl's _sep_if_latin_tail. */
                if (digit_seq_sep(in, ws + 1)) out[o++] = ' ';
                i = ws + 1;
                continue;
            }
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

static void pass_decimal(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        if (isdigit((unsigned char)in[i])) {
            int a = i;
            while (isdigit((unsigned char)in[a])) a++;
            if (in[a] == '.' && isdigit((unsigned char)in[a + 1])) {
                int b = a + 1;
                while (isdigit((unsigned char)in[b])) b++;
                /* DECIMAL on BOTH sides: BTC excepts "rhifau cyn ac ar ol pwyntiau
                 * degol" from the vigesimal rule -- "20.15" is "dau ddeg pwynt un pump",
                 * and the guide names "ugain pwynt pymtheg" as wrong. */
                /* FIXED 2026-07-28. This read
                 *     cardinal_dec(nb, parse_int_strip_commas(in + i, a - i))
                 * and cardinal_dec was HUNDREDS[n / 100] plus the last two digits -- correct
                 * only below 1000, with nothing here bounding the integer part of a decimal.
                 * HUNDREDS has 10 entries, so "1000.5" indexed [10] and SEGFAULTED, while
                 * "1234.56" indexed [12], came back empty and silently dropped the "12":
                 * "tri deg pedwar pwynt pump chwech", which is 34.56. Python raised KeyError
                 * on both. No parity row has a decimal at or above 1000, so make check saw
                 * none of it.
                 * num_words_run_commas is the same register (decimal, since the vigesimal
                 * revert) with neither the out-of-bounds nor the long overflow. */
                o += num_words_run_commas(in + i, a - i, out + o);
                strcpy(out + o, " pwynt"); o += 6;
                for (int d = a + 1; d < b; d++) {
                    const char *db = in[d] == '0' ? "sero" : UNITS[in[d] - '0'];
                    out[o++] = ' '; strcpy(out + o, db); o += (int)strlen(db);
                }
                i = b;
                continue;
            }
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

/* ---- digit SEQUENCES (phone numbers) vs digit QUANTITIES -------------------------------
 * Mirrors welsh_normalize._PHONE / _DIGIT_SEQ / _DIGIT_NAMES, where the full reasoning and
 * the espeak evidence live. Summary: a digit run that STARTS WITH ZERO is a sequence, not an
 * amount, and reads digit by digit. That rule is taken from the piper-cy voice -- espeak-ng's
 * cy voice reads "0123" as "nul un dau tri" and "123" as "cant dau ddeg tri". We keep the
 * rule and reject espeak's word: it says "nul", which is not standard Welsh for zero; the
 * owner chose "dim" (2026-07-28).
 * Citation forms, unreduced -- an isolated digit has no following noun, so BTC's connected
 * forms (pum/chwe) do not apply. */
static const char *DIGIT_NAMES[10] = {"dim", "un", "dau", "tri", "pedwar",
                                      "pump", "chwech", "saith", "wyth", "naw"};

/* One codepoint of the separator class [space, NBSP, hyphen], or 0. NBSP because web copy is
 * full of it and every other whitespace test in this file is Unicode-aware. */
static int phone_sep_len(const char *s, int i) {
    if (s[i] == ' ' || s[i] == '-') return 1;
    if ((unsigned char)s[i] == 0xC2 && (unsigned char)s[i + 1] == 0xA0) return 2;
    return 0;
}

/* The TAIL of _PHONE -- `(?:[  -]?\d{2,4}){1,3}` and the closing `(?!\d)` -- searched in the
 * regex engine's own order, so C settles on the same split Python does. `done` is how many
 * tail groups are already consumed, `nd` the digit total including the leading group. On
 * success `*end` is the index one past the run and `*ndigits` the digit total.
 *
 * WHY BACKTRACKING, and why the ORDER is the specification, not just the answer:
 * Python's `{1,3}` is greedy, so it takes one more group before it settles; `[  -]?` is
 * greedy, so a separator is consumed when one is there; and `\d{2,4}` is greedy, so 4 digits
 * are tried before 3 before 2. Only when every continuation fails does the engine accept the
 * current position, and accepting needs `(?!\d)` to hold. A single greedy left-to-right walk
 * -- which is what this function used to be -- gets a DIFFERENT split whenever a non-leading
 * group has 5 digits: on "0800 12345" the greedy walk takes "1234", cannot make a 2-digit
 * group out of the lone "5", and gives up with `(?!\d)` failing on that "5"; Python
 * re-splits the same digits 3+2 through the zero-width separator and matches. Measured
 * 2026-07-29: "0800 12345x" and "07700 90012x" verbalised digit-by-digit in Python and as
 * fused cardinals in C, and "0800 12345"/"07700 90012" had been divergent since before the
 * (?!\d) change -- the differential fuzzers simply never generated a 5-digit second group.
 *
 * BOUNDED: depth is at most 3, and each level tries at most 2 separator choices x 3 lengths,
 * so at most 6^3 = 216 continuations per leading-group candidate. There is no loop and no
 * unbounded scan; it always terminates. */
static int phone_tail(const char *s, int j, int done, int nd, int *end, int *ndigits) {
    if (done < 3) {
        int sep = phone_sep_len(s, j);
        /* `[  -]?` greedy: separator first (when one is present), then the empty branch.
         * The empty branch cannot succeed while a separator IS present -- \d{2,4} would
         * have to match the separator character -- so it costs one failed digit test. */
        for (int use = (sep ? 1 : 0); use >= 0; use--) {
            int b = j + (use ? sep : 0);
            int avail = 0;
            while (avail < 4 && isdigit((unsigned char)s[b + avail])) avail++;
            for (int g = avail; g >= 2; g--)                 /* \d{2,4} greedy: 4, 3, 2 */
                if (phone_tail(s, b + g, done + 1, nd + g, end, ndigits)) return 1;
        }
    }
    /* `{1,3}` needs at least one tail group, and `(?!\d)` says the run ends where the
     * digits end -- not at a word boundary, so a following letter does not block it. */
    if (done >= 1 && !isdigit((unsigned char)s[j])) { *end = j; *ndigits = nd; return 1; }
    return 0;
}

/* Length of the _PHONE MATCH at s[i], or 0 if the pattern does not match there. Shape:
 * optional "(", a leading-zero group of 2-5 digits, optional ")", then 1-3 further groups of
 * 2-4 digits separated by one separator. Mirrors _PHONE, whose leading group is
 * `\(?\b0\d{1,4}\)?`; `\b` itself is the caller's digit_seq_start_ok.
 *
 * The 9-11-digit test is NOT here, and that is the point: in Python it lives inside
 * `_phone_repl`, which runs AFTER the match and cannot make the engine look for a different
 * split -- a phone-shaped match with the wrong digit total is handed back unchanged. So this
 * function returns the FIRST match in the engine's backtracking order together with its digit
 * total, and the caller decides. Backtracking to a shorter leading group after a count
 * failure would find a split Python never saw. The digit total is what tells a phone number
 * from prose that merely begins with a zero, and the whole run must be claimed at once --
 * reading the first group as digits and the rest as cardinals is no more usable than the
 * original. */
static int phone_match_len(const char *s, int i, int *ndigits) {
    int j = i;
    /* `\(?` greedy. Its not-taken branch is futile and is therefore not tried: without the
     * "(" the next atom is `\b0`, and "(" is not "0". */
    if (s[j] == '(') j++;
    if (s[j] != '0') return 0;
    int avail = 0;                                   /* `0\d{1,4}`: 1-4 digits after the 0 */
    while (avail < 4 && isdigit((unsigned char)s[j + 1 + avail])) avail++;
    for (int g = avail; g >= 1; g--) {               /* greedy: 4, then 3, 2, 1 */
        int k = j + 1 + g;
        /* `\)?` greedy, and futile to un-take for the same reason as `\(?`: ")" starts
         * neither the separator class nor \d, so the tail could not match without it. */
        if (s[k] == ')') k++;
        int end = 0, nd = 0;
        if (phone_tail(s, k, 0, 1 + g, &end, &nd)) { *ndigits = nd; return end - i; }
    }
    return 0;
}

/* A leading zero only means "sequence" at the START of a number: never after a digit, a
 * thousands comma or a decimal point. Without this the "000" group of "1,000" was claimed --
 * word_before() is false after a comma -- and "un mil" became "un dim dim dim". The parity
 * corpus caught it on the first regeneration, which is what it is for. Mirrors
 * _DIGIT_SEQ's (?<![\w,.]) lookbehind -- the \w half is word_before(), and is why a run
 * inside a word ("a007") is left alone (d27543e). */
static int digit_seq_start_ok(const char *s, int i) {
    if (i == 0) return 1;
    char pv = s[i - 1];
    if (pv == ',' || pv == '.') return 0;
    if (isdigit((unsigned char)pv)) return 0;
    return !word_before(s, i);
}

/* The same question for _PHONE, whose lookbehind is the LAXER (?<![\d,.]) with the \b sitting
 * AFTER the optional "(": `(?<![\d,.])\(?\b0`. So a run opened by "(" needs only "no digit,
 * comma or dot immediately before" -- a letter or "_" there does not block it, and Python
 * matches the phone in "a(01248) 382000". A run opened by "0" has the \b directly before it,
 * which is exactly digit_seq_start_ok's word_before test, so the two agree there.
 *
 * Sharing one guard therefore made C refuse a bracketed phone number preceded by a letter
 * while Python claimed it. What C then did is worth stating exactly, because the obvious
 * guess is wrong: it did NOT hand the number to the cardinal pass. The phone pass declined,
 * the digits fell through to the leading-zero digit-sequence pass and were spelled out, and
 * the "(" -- which no pass had consumed -- survived into the output. So
 * "a(01248) 382000" gave C "a(dim un dau ..." against Python's "adim un dau ...": the same
 * digits, plus a stray bracket. Pre-existing (it predates the grouping fix above), found
 * 2026-07-29 by an exhaustive normalize-text differential over the alphabet "0-9 ()-_,.x". */
static int phone_start_ok(const char *s, int i) {
    if (s[i] != '(') return digit_seq_start_ok(s, i);
    if (i == 0) return 1;
    char pv = s[i - 1];
    return pv != ',' && pv != '.' && !isdigit((unsigned char)pv);
}

/* Bounds-checked append; defined below (shared with pass_fraction/pass_unit), forward
 * declared here so spell_digits/pass_digit_seq can use it too. Needed because the
 * trailing-separator write below makes this pass emit more bytes than it used to, and
 * cyp_normalize's shared 64 KB arena has no guard of its own against that
 * (docs/FOLLOWUPS.md SS G). */
static int put_n(char *out, int o, int max, const char *s, int len);

/* Every digit in s[i..i+len) as its own word; separators and brackets are dropped. When
 * `sep` is set, one trailing space is appended after the spelled run -- mirrors Python's
 * shared _sep_after_spelled_digits, used by both _digit_seq_repl and _phone_repl: without
 * it "0800x" became "dim wyth dim dimx", the verbalised run fused onto the letters and LTS
 * saw one nonword. Callers decide `sep` via digit_seq_sep, below. Returns the new offset,
 * or -1 if the arena has no room left (see put_n). */
static int spell_digits(char *out, int o, int max, const char *s, int i, int len, int sep) {
    /* Spaces go only BETWEEN the digit words, never before the first. Python's
     * " ".join(...) substitutes in place and adds no leading space, so inserting one here
     * diverged on "90:00" -- an out-of-range clock whose digits fall through to this pass --
     * where C said "naw deg: dim dim" and Python "naw deg:dim dim". */
    int first = 1;
    for (int k = i; k < i + len; k++)
        if (isdigit((unsigned char)s[k])) {
            if (!first) { o = put_n(out, o, max, " ", 1); if (o < 0) return -1; }
            first = 0;
            const char *w = DIGIT_NAMES[s[k] - '0'];
            o = put_n(out, o, max, w, (int)strlen(w));
            if (o < 0) return -1;
        }
    if (sep) { o = put_n(out, o, max, " ", 1); if (o < 0) return -1; }
    return o;
}

/* _PHONE then _DIGIT_SEQ, in that order and for the same reason Python runs them that way:
 * the phone pattern spans the whole grouped number, and the leading-zero pattern would
 * otherwise eat its first group and leave the rest to the cardinal pass. */
/* ---- math operators, degrees, emails/URLs, Roman numerals ------------------------------
 * All four are characters or tokens that were previously left in the text, where they either
 * GLUED their neighbours into a nonword or were read as a phone. "5+3" normalised to
 * "pump+tri"; "+" is not a phone so it vanished and the model heard "pumptri". "@" is worse:
 * it IS a phone in the Bangor inventory (the schwa), so an email was read as a vowel.
 * Wording from the owner, 2026-07-28: "Pump plws tri", "dau lluosi tri",
 * "Pump gradd celsiws", "Post at bangor dot ac dot wc", "Penod pedwar".
 * Mirrors welsh_normalize._MATH_OPS / _DEGREE / _EMAIL_OR_URL / _ROMAN. */
static int is_ascii_digit(char c) { return c >= '0' && c <= '9'; }

/* (?<=\d)\s*(op)\s*(?=\d) for + and x/X/×, and the degree sign with an optional scale. */
/* ---- emoji -----------------------------------------------------------------------------
 * Mirrors welsh_normalize's emoji pass. Names come from espeak-ng's cy voice (CLDR-derived)
 * and are extracted, not translated -- see welsh_normalize._EMOJI for the provenance and for
 * why the sweep was restricted to genuine emoji blocks.
 *
 * The table is GENERATED C rather than a runtime file load: cyp_normalize() is a bare
 * (in, out, max) function with no data-dir handle -- the parity harness calls it directly --
 * so it cannot read a TSV the way cyp_create() reads ipa_map.tsv. One source of truth stays
 * the TSV; scripts/emit_c_data.py turns it into cy_emoji_data.h.
 *
 * EMOJI_CY is sorted longest-sequence-first by the generator, so taking the FIRST hit is the
 * longest-match rule -- that is what stops a two-codepoint flag matching half of itself. */

/* U+FE0F, U+FE0E and U+200D are presentation marks, not content: "❤️" is "❤" plus FE0F and
 * must find the same name. Length of one at s[i], or 0. */
static int emoji_skip_len(const char *s, int i) {
    unsigned char a = (unsigned char)s[i], b = (unsigned char)s[i+1], c = (unsigned char)s[i+2];
    if (a == 0xEF && b == 0xB8 && (c == 0x8F || c == 0x8E)) return 3;   /* FE0F / FE0E */
    if (a == 0xE2 && b == 0x80 && c == 0x8D) return 3;                  /* ZWJ */
    return 0;
}

static void pass_emoji(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        int sk = emoji_skip_len(in, i);
        if (sk) { i += sk; continue; }          /* drop presentation marks before matching */
        int hit = -1;
        if ((unsigned char)in[i] >= 0xC2) {     /* only multi-byte sequences can be emoji */
            for (int k = 0; EMOJI_CY[k].seq; k++) {
                size_t L = strlen(EMOJI_CY[k].seq);
                if (!strncmp(in + i, EMOJI_CY[k].seq, L)) { hit = k; break; }
            }
        }
        if (hit >= 0) {
            /* Spaces on BOTH sides: an emoji sits directly against a word often enough
             * ("Da iawn👍"), and without them the name would glue to it -- the same nonword
             * failure the symbol passes were fixed for. pass_lower_collapse tidies the rest. */
            out[o++] = ' ';
            const char *w = EMOJI_CY[hit].name;
            strcpy(out + o, w); o += (int)strlen(w);
            out[o++] = ' ';
            i += (int)strlen(EMOJI_CY[hit].seq);
            continue;
        }
        /* TAG characters (U+E0020-U+E007F, F3 A0 80..BF in UTF-8) are checked AFTER the table,
         * not before: they are PART of the national-flag sequences, which are in the table and
         * sorted longest-first. Whatever reaches here is a tag flag we have no name for, and
         * would otherwise pass through as raw codepoints. */
        if ((unsigned char)in[i] == 0xF3 && (unsigned char)in[i+1] == 0xA0
            && (unsigned char)in[i+2] == 0x80) { i += 4; continue; }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

static void pass_math_deg(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        int prev_digit = (o > 0 && is_ascii_digit(out[o - 1]));
        if (prev_digit) {
            int j = i;   /* every \s* here is Unicode (re_space_len) -- the sweep */
            for (int sl; (sl = re_space_len(in, j)); ) j += sl;
            int oplen = 0; const char *word = NULL;
            if (in[j] == '+') { oplen = 1; word = "plws"; }
            else if (in[j] == 'x' || in[j] == 'X') { oplen = 1; word = "lluosi"; }
            else if ((unsigned char)in[j] == 0xC3 && (unsigned char)in[j + 1] == 0x97) { oplen = 2; word = "lluosi"; }  /* U+00D7 */
            if (word) {
                int k = j + oplen;
                for (int sl; (sl = re_space_len(in, k)); ) k += sl;
                if (is_ascii_digit(in[k])) {
                    o += sprintf(out + o, " %s ", word);
                    i = k;
                    continue;
                }
            }
            /* degree sign U+00B0, optionally followed by C or F */
            if ((unsigned char)in[j] == 0xC2 && (unsigned char)in[j + 1] == 0xB0) {
                int k = j + 2;
                for (int sl; (sl = re_space_len(in, k)); ) k += sl;
                if ((in[k] == 'C' || in[k] == 'c') && !word_after(in, k + 1)) {
                    o += sprintf(out + o, " gradd celsiws"); i = k + 1; continue;
                }
                if ((in[k] == 'F' || in[k] == 'f') && !word_after(in, k + 1)) {
                    o += sprintf(out + o, " gradd fahrenheit"); i = k + 1; continue;
                }
                o += sprintf(out + o, " gradd"); i = j + 2; continue;
            }
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

static int url_label_char(char c) {
    return isalnum((unsigned char)c) || c == '-' || c == '_' || c == '+' || c == '%';
}

/* Emit one dot-separated label run, mapping the labels whose spoken form is not the letters.
 * Only "uk" -> "wc", the one the owner gave; any other label is read as written. */
static void emit_labels(char *out, int *o, const char *s, int a, int b) {
    int first = 1, k = a;
    while (k < b) {
        int st = k;
        while (k < b && s[k] != '.') k++;
        int len = k - st;
        if (len > 0) {
            if (!first) { strcpy(out + *o, " dot "); *o += 5; }
            first = 0;
            if (len == 2 && (s[st] == 'u' || s[st] == 'U') && (s[st+1] == 'k' || s[st+1] == 'K')) {
                strcpy(out + *o, "wc"); *o += 2;
            } else if (len == 3 && (s[st]|32) == 'w' && (s[st+1]|32) == 'w' && (s[st+2]|32) == 'w') {
                /* Spelled letter by letter: read as a word "www" is unpronounceable. The "·"
                 * separator is what pass_acronym already uses to make the G2P name each letter
                 * (BBC -> "b·b·c"), so this routes into the same path rather than adding one.
                 * Owner 2026-07-28: "We should fix www". */
                strcpy(out + *o, "w·w·w"); *o += (int)strlen("w·w·w");
            } else {
                memcpy(out + *o, s + st, (size_t)len); *o += len;
            }
        }
        if (k < b) k++;    /* skip the '.' */
    }
}

/* An email address or a www./http(s):// URL. Anything else containing a dot is left alone --
 * "bangor.ac.uk" with no scheme and no www is indistinguishable from a sentence-final word
 * followed by an abbreviation, and Python draws the same line. */
static void pass_email_url(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        if (!word_before(in, i)) {
            /* scheme, then www. or an authority with at least one dot */
            int j = i;
            if (!strncmp(in + j, "https://", 8)) j += 8;
            else if (!strncmp(in + j, "http://", 7)) j += 7;
            int body = j, at = -1, dots = 0;
            while (url_label_char(in[j]) || in[j] == '.' || in[j] == '@') {
                if (in[j] == '@') { if (at >= 0) break; at = j; }
                else if (in[j] == '.') dots++;
                j++;
            }
            while (j > body && (in[j - 1] == '.' || in[j - 1] == '-')) j--;   /* trailing punctuation */
            int is_url = (body != i) || (!strncmp(in + body, "www.", 4));
            int ok = (j - body) > 3 && dots >= 1 && (at >= 0 || is_url);
            if (ok) {
                if (at >= 0) {
                    emit_labels(out, &o, in, body, at);
                    strcpy(out + o, " at "); o += 4;
                    emit_labels(out, &o, in, at + 1, j);
                } else {
                    emit_labels(out, &o, in, body, j);
                }
                i = j;
                continue;
            }
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

static int roman_char(char c) {
    return c=='M'||c=='D'||c=='C'||c=='L'||c=='X'||c=='V'||c=='I';
}
static int roman_val(char c) {
    switch (c) { case 'M': return 1000; case 'D': return 500; case 'C': return 100;
                 case 'L': return 50; case 'X': return 10; case 'V': return 5;
                 case 'I': return 1; } return 0;
}
/* Words that are also strings of Roman letters; without this "MIX" reads "mil naw". */
static const char *ROMAN_NOT[] = {"MIX","DID","MILL","DIM","MI","DI","LI","CI","MC","DC",
                                  "CD","ID","DILL","CILL","MILI","LID","LIM","MIL",NULL};
/* Value of a CANONICAL Roman numeral, or -1. Canonical by ROUND-TRIP: converted to an integer
 * and back it must come out identical, which is what rejects "IIII", "VV", "IC" and "XXXX"
 * without a second grammar to maintain. Python does exactly this, and for the same reason:
 * the first attempt encoded the grammar as a regex, every group of which was optional, so it
 * matched the EMPTY STRING and "DID" came out as "serodid". */
static long roman_value(const char *t, int len) {
    long total = 0; int prev = 0;
    for (int k = len - 1; k >= 0; k--) {
        int v = roman_val(t[k]);
        total += (v < prev) ? -v : v;
        if (v > prev) prev = v;
    }
    if (total < 1 || total > 3999) return -1;
    static const struct { int v; const char *sym; } R[] = {
        {1000,"M"},{900,"CM"},{500,"D"},{400,"CD"},{100,"C"},{90,"XC"},{50,"L"},
        {40,"XL"},{10,"X"},{9,"IX"},{5,"V"},{4,"IV"},{1,"I"},{0,NULL}};
    char back[32]; int b = 0; long n = total;
    for (int r = 0; R[r].sym; r++)
        while (n >= R[r].v) { strcpy(back + b, R[r].sym); b += (int)strlen(R[r].sym); n -= R[r].v; }
    back[b] = 0;
    if (b != len || strncmp(back, t, (size_t)len) != 0) return -1;
    return total;
}

/* MOVED UP 2026-07-28: pass_roman needs it for regnal ordinals and sits above the date
 * passes that were its only previous users. Same table, unchanged. */
/* ---------------- dates & ordinals ---------------- */
static const char *ORD[32][2] = {
    {0, 0}, {"cyntaf", "cyntaf"}, {"ail", "ail"}, {"trydydd", "trydedd"},
    {"pedwerydd", "pedwaredd"}, {"pumed", "pumed"}, {"chweched", "chweched"},
    {"seithfed", "seithfed"}, {"wythfed", "wythfed"}, {"nawfed", "nawfed"}, {"degfed", "degfed"},
    {"unfed ar ddeg", "unfed ar ddeg"}, {"deuddegfed", "deuddegfed"},
    {"trydydd ar ddeg", "trydedd ar ddeg"}, {"pedwerydd ar ddeg", "pedwaredd ar ddeg"},
    {"pymthegfed", "pymthegfed"}, {"unfed ar bymtheg", "unfed ar bymtheg"},
    {"ail ar bymtheg", "ail ar bymtheg"}, {"deunawfed", "deunawfed"},
    {"pedwerydd ar bymtheg", "pedwaredd ar bymtheg"}, {"ugeinfed", "ugeinfed"},
    {"unfed ar hugain", "unfed ar hugain"}, {"ail ar hugain", "ail ar hugain"},
    {"trydydd ar hugain", "trydedd ar hugain"}, {"pedwerydd ar hugain", "pedwaredd ar hugain"},
    {"pumed ar hugain", "pumed ar hugain"}, {"chweched ar hugain", "chweched ar hugain"},
    {"seithfed ar hugain", "seithfed ar hugain"}, {"wythfed ar hugain", "wythfed ar hugain"},
    {"nawfed ar hugain", "nawfed ar hugain"}, {"degfed ar hugain", "degfed ar hugain"},
    {"unfed ar ddeg ar hugain", "unfed ar ddeg ar hugain"}};

/* Mirrors welsh_normalize._ROMAN_STRUCTURAL. Lower-cased comparison, so "Pennod" and "PENNOD"
 * behave alike -- pass_deshout has already folded genuinely shouty text by this point. */
static const char *ROMAN_STRUCTURAL[] = {
    "pennod","rhan","cyfrol","adran","atodiad","llyfr","tabl","ffigur","cam","gwers","uned",
    "rhif","fersiwn","dosbarth","categori","lefel","cyfnod",
    "chapter","part","volume","section","appendix","book","table","figure",NULL};

static int roman_prev_is_structural(const char *s, int i) {
    int e = i;
    while (e > 0 && (s[e - 1] == ' ' || s[e - 1] == '\t')) e--;
    int b = e;
    while (b > 0 && (isalpha((unsigned char)s[b - 1]) || (unsigned char)s[b - 1] >= 0x80
                     || s[b - 1] == '\'')) b--;
    int len = e - b;
    if (len <= 0 || len > 24) return 0;
    char w[32];
    for (int k = 0; k < len; k++) {
        char c = s[b + k];
        w[k] = (c >= 'A' && c <= 'Z') ? (char)(c + 32) : c;
    }
    w[len] = 0;
    for (int k = 0; ROMAN_STRUCTURAL[k]; k++)
        if (!strcmp(ROMAN_STRUCTURAL[k], w)) return 1;
    return 0;
}

static void pass_roman(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        if (roman_char(in[i]) && !word_before(in, i)) {
            int j = i;
            while (roman_char(in[j])) j++;
            int len = j - i;
            if (len >= 2 && !word_after(in, j)) {
                int skip = 0;
                for (int k = 0; ROMAN_NOT[k]; k++)
                    if ((int)strlen(ROMAN_NOT[k]) == len && !strncmp(ROMAN_NOT[k], in + i, (size_t)len)) { skip = 1; break; }
                long v = skip ? -1 : roman_value(in + i, len);
                if (v > 0) {
                    char nb[512];
                    /* A Roman numeral after a PERSONAL NAME is a regnal number and takes the
                     * ORDINAL with its article ("Elisabeth yr ail"); after a structural noun it
                     * is a plain cardinal ("Pennod pedwar"). Owner confirmed both, 2026-07-28.
                     * No reliable signal says "personal name", so the DEFAULT is the ordinal and
                     * the exception is the structural nouns -- that vocabulary is small and nearly
                     * closed, where the set of names is not. Mirrors welsh_normalize's
                     * _ROMAN_STRUCTURAL, which carries the full reasoning. */
                    if (roman_prev_is_structural(in, i) || v > 31 || v < 1) {
                        cyp_num_to_welsh(v, nb, sizeof(nb));
                    } else {
                        const char *ordw = ORD[v][0];
                        nb[0] = 0;
                        app(nb, strchr("aeiouwyh", ordw[0]) ? "yr" : "y");
                        app(nb, ordw);
                    }
                    strcpy(out + o, nb); o += (int)strlen(nb);
                    i = j;
                    continue;
                }
            }
            while (i < j) out[o++] = in[i++];
            continue;
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

/* True if the spelled run at s[..j) should get a trailing separator before s[j]: mirrors
 * Python's "tail.isalpha() or tail == '_'" (both _digit_seq_repl and _phone_repl, via the
 * shared _sep_after_spelled_digits -- Fix round 1 gave _phone_repl the same separator
 * logic _digit_seq_repl already had, because a 9-11-digit leading-zero run is claimed by
 * _PHONE, not _DIGIT_SEQ, and _phone_repl used to return the spelled digits bare).
 *
 * Deliberately NOT word_after/cp_is_word: \w also matches digits, which happens to be
 * moot here (the run has already consumed every adjacent digit, so s[j] can never itself
 * be one), but "word" is the wrong concept to reach for when the rule is about letters.
 * cyp__cp_is_alpha is str.isalpha() over the same Latin domain cp_is_word knows -- see its
 * own KNOWN GAP note -- plus the explicit "_" Python ORs in, which isalpha() itself never
 * matches. That domain restriction is real and pre-existing, not introduced or widened
 * here: a letter outside it (Greek "α", Cyrillic "д", CJK "中", and even some Latin-1
 * letters below U+00C0 such as "ª"/"µ") still reads as a non-letter and the run stays
 * fused to it, in both cp_is_word and cyp__cp_is_alpha alike, because the latter defers to
 * the former outside ASCII. Closing that needs real Unicode letter tables shared across
 * every \b-based pass in this file, not a change to this one call site. */
static int digit_seq_sep(const char *s, int j) {
    if (!s[j]) return 0;
    long cp = cp_at(s, j);
    return cyp__cp_is_alpha(cp) || cp == '_';
}

static void pass_digit_seq(const char *in, char *out, int max) {
    int i = 0, o = 0;
    /* Python runs _PHONE.sub and _DIGIT_SEQ.sub as TWO passes; this is one. Almost all of
     * that fuses harmlessly, because a claimed run is replaced by Welsh words that neither
     * pattern can match again -- but re.sub's scan position does not fuse. When _phone_repl
     * DECLINES a match on the digit total it returns the span unchanged, and re.sub resumes
     * AFTER that span: no position inside a declined match can start another _PHONE match.
     * _DIGIT_SEQ, being a separate pass over the whole text, still sees every position. So
     * only the phone half is suppressed, up to this offset.
     *
     * The shape, measured 2026-07-29: C verbalises a phone-shaped TAIL that Python leaves as
     * a cardinal, because Python's re.sub never re-examines a position inside a declined
     * match and C, as one pass, did. "012 058 513715" is the clearest instance -- 12 digits
     * so _phone_repl declines the whole thing, while "058 513715" inside it is 9 and C
     * claimed it. Others of the same shape: "01 01442-58225", "01-09-65 44739",
     * "012 0326 28967-0", "012 04979690 56", "0123 0974 80 407".
     *
     * Deliberately NOT stating how many of those six this fix newly closed versus how many
     * were already divergent: two independent reviews put the split at 4+2 and 3+3, and the
     * discrepancy was never resolved by measurement. `make fuzz` is what asserts the current
     * state, and it is green; a count nobody re-derived would be exactly the kind of stale
     * number this file has been bitten by twice. */
    int phone_scan = 0;
    while (in[i]) {
        int nd = 0, plen = 0, mlen = 0;
        if (i >= phone_scan && (in[i] == '(' || in[i] == '0') && phone_start_ok(in, i))
            mlen = phone_match_len(in, i, &nd);
        if (mlen > 0) {
            if (nd >= 9 && nd <= 11) plen = mlen;    /* _phone_repl verbalises it */
            else phone_scan = i + mlen;              /* declined: re.sub skips the span */
        }
        if (plen > 0) {
            /* Fix round 1: _phone_repl now separates too (see digit_seq_sep above), so
             * this branch is no longer sep=0. Before that fix, a UK phone-shaped run
             * (9-11 digits) FUSED into a following letter while the same digits at length
             * 8 or 12 correctly separated -- "0800123456x" -> "...pump chwechx" -- purely
             * because of which of the two patterns happened to claim the run. Both must
             * agree, or the digit-register rule ("leading zero -> read digit by digit,
             * kept a separate word") silently breaks for exactly the UK phone lengths. */
            int sep = digit_seq_sep(in, i + plen);
            int no = spell_digits(out, o, max, in, i, plen, sep);
            if (no < 0) goto done;
            o = no;
            i += plen;
            continue;
        }
        /* any other leading-zero run of 2+ digits: "007", "0044", an extension. The run
         * ends where the DIGITS end (isdigit), not at a word boundary -- mirrors Python's
         * (?!\d), which replaced a trailing \b on _DIGIT_SEQ (welsh_normalize.py): with \b,
         * "0800x" never matched at all (0->x is word-to-word, no boundary) and fell
         * through to the cardinal pass, where int("0800") silently ate both leading
         * zeros. */
        if (in[i] == '0' && isdigit((unsigned char)in[i + 1]) && digit_seq_start_ok(in, i)) {
            int j = i;
            while (isdigit((unsigned char)in[j])) j++;
            /* One trailing space if a letter or "_" follows, so the spelled run stays a
             * separate word ("0800x" -> "dim wyth dim dim x", not "...dim dimx"). */
            int sep = digit_seq_sep(in, j);
            int no = spell_digits(out, o, max, in, i, j - i, sep);
            if (no < 0) goto done;
            o = no;
            i = j;
            continue;
        }
        if (o + 1 >= max) goto done;
        out[o++] = in[i++];
    }
done:
    out[o] = 0;
}

static void pass_integer(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        if (isdigit((unsigned char)in[i])) {
            int j = i;
            while (isdigit((unsigned char)in[j]) || in[j] == ',') j++;
            o += num_words_run_commas(in + i, j - i, out + o);
            i = j;
            continue;
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

static int amp_is_vowel(unsigned char c) {
    c = (unsigned char)tolower(c);
    return c == 'a' || c == 'e' || c == 'i' || c == 'o' || c == 'u' || c == 'w' || c == 'y' || c == '/';
}
static void pass_amp(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        if (in[i] == '&') {
            int j = i + 1;   /* \s* is Unicode (re_space_len), not ASCII -- the sweep */
            for (int sl; (sl = re_space_len(in, j)); ) j += sl;
            unsigned char nxt = (unsigned char)in[j];
            /* [A-Za-z] or accented À-ÿ (0xC3 0x80..0xBF leading byte) */
            int is_letter = isalpha(nxt) || nxt == 0xC3;
            if (is_letter) {
                const char *conj = amp_is_vowel(nxt) ? "ac" : "a";
                strcpy(out + o, conj); o += (int)strlen(conj);
                out[o++] = ' ';
                i = j;
                continue;
            }
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

/* Lowercase an uppercase accented codepoint the way Python str.lower() does, for the
 * Latin ranges Welsh/English text uses. Returns the lowercase codepoint, or the input
 * unchanged if it has no mapping here. İ (U+0130) is special: Python yields "i"+U+0307,
 * but the combining dot is phonetically inert, so we fold to plain 'i'. */
static long lower_accent_cp(long cp) {
    if (cp >= 'A' && cp <= 'Z') return cp + 32;
    if (cp == 0x0130) return 'i';                                       /* İ -> i (NOT ı; before generic rule) */
    if (cp == 0x0131) return 0x0131;                                    /* ı dotless-i: already lowercase */
    if (cp >= 0x00C0 && cp <= 0x00DE && cp != 0x00D7) return cp + 0x20; /* À-Þ minus × -> à-þ */
    if (cp >= 0x0100 && cp <= 0x0177 && (cp & 1) == 0) return cp + 1;   /* Latin Ext-A even=upper */
    if (cp == 0x0178) return 0x00FF;                                    /* Ÿ -> ÿ */
    if (cp >= 0x1E00 && cp <= 0x1EFF && (cp & 1) == 0) return cp + 1;   /* Latin Ext Additional */
    return cp;
}
/* Append codepoint cp to out[o] as UTF-8; return new offset. */
static int put_cp(char *out, int o, long cp) {
    if (cp < 0x80) { out[o++] = (char)cp; }
    else if (cp < 0x800) {
        out[o++] = (char)(0xC0 | (cp >> 6)); out[o++] = (char)(0x80 | (cp & 0x3F));
    } else if (cp < 0x10000) {
        out[o++] = (char)(0xE0 | (cp >> 12)); out[o++] = (char)(0x80 | ((cp >> 6) & 0x3F));
        out[o++] = (char)(0x80 | (cp & 0x3F));
    } else {
        out[o++] = (char)(0xF0 | (cp >> 18)); out[o++] = (char)(0x80 | ((cp >> 12) & 0x3F));
        out[o++] = (char)(0x80 | ((cp >> 6) & 0x3F)); out[o++] = (char)(0x80 | (cp & 0x3F));
    }
    return o;
}
/* Byte length of the UTF-8 sequence led by byte c. */
static int utf8_len(unsigned char c) {
    if (c < 0x80) return 1;
    if ((c & 0xE0) == 0xC0) return 2;
    if ((c & 0xF0) == 0xE0) return 3;
    if ((c & 0xF8) == 0xF0) return 4;
    return 1;
}
static void pass_lower_collapse(const char *in, char *out) {
    int i = 0, o = 0, prev_space = 1; /* strip leading */
    /* Unicode-lowercase (Python .lower(), Latin domain) + collapse whitespace runs.
     * The collapse mirrors Python's closing `re.sub(r"\s+", " ", text).strip()`, and its
     * \s is UNICODE: a non-breaking or ideographic space that no earlier pass consumed
     * must collapse to a plain " " here, exactly as Python does. Reading it as ASCII
     * left "a<NBSP>b" as "a<NBSP>b" where Python says "a b" — and because this runs on
     * EVERY output, that one test accounted for ~76% of all whitespace divergences. */
    while (in[i]) {
        unsigned char b = (unsigned char)in[i];
        if (cyp__cp_is_space(cp_at(in, i))) {
            if (!prev_space) { out[o++] = ' '; prev_space = 1; }
            i += utf8_len(b);
        } else if (b < 0x80) {
            char c = (char)b; if (c >= 'A' && c <= 'Z') c += 32;
            out[o++] = c; prev_space = 0; i++;
        } else {
            int adv = utf8_len(b);
            long cp = cp_at(in, i);
            if (cp == 0x0130) {
                /* İ -> "i" + U+0307 (Python str.lower()); the combining dot is inert in
                 * LTS but must be KEPT so it breaks adjacency (İİ -> i i, not the ii glide). */
                o = put_cp(out, o, 'i');
                o = put_cp(out, o, 0x0307);
            } else {
                o = put_cp(out, o, lower_accent_cp(cp));
            }
            prev_space = 0; i += adv;
        }
    }
    while (o > 0 && out[o - 1] == ' ') o--; /* strip trailing */
    out[o] = 0;
}

/* -------- internal helpers shared with cy_phonemize.c (cyp_letter_tokens) -------- */

/* Start of each Unicode Nd (decimal-digit) block: value = cp - start, 0..9.
 * 65 blocks, 650 codepoints. It relies on every Nd block being a clean run of ten,
 * which was checked over the whole codepoint space when the table was produced -- but
 * this table is NOT emitted by scripts/emit_c_data.py and nothing regenerates or
 * re-asserts it automatically. It is hand-pasted from the one-liner below, and what
 * actually keeps it honest is tests/test_ssml_primitives.py, which walks every
 * codepoint against unicodedata and drives them through cyp_letter_tokens.
 *
 * The next line is PARSED by tests/test_ssml_primitives.py — keep the exact spelling,
 * and update it whenever the table is regenerated. It is how a table built under one
 * Unicode version and corpora built under another become a test failure rather than a
 * silent divergence in what a user hears.
 *
 * ND_TABLE_UNICODE_VERSION = 13.0.0
 *
 * REGENERATE together with the corpora, under ONE interpreter (see README.md — three
 * are in play in this project and the deployed API has the oldest tables):
 *   python -c "import unicodedata as u; nd=[c for c in range(0x110000) if
 *   u.category(chr(c))=='Nd']; print([hex(c) for c in nd[::10]])"
 */
static const long ND_BLOCK[] = {
    0x0030, 0x0660, 0x06F0, 0x07C0, 0x0966, 0x09E6, 0x0A66, 0x0AE6, 0x0B66, 0x0BE6, 0x0C66,
    0x0CE6, 0x0D66, 0x0DE6, 0x0E50, 0x0ED0, 0x0F20, 0x1040, 0x1090, 0x17E0, 0x1810, 0x1946,
    0x19D0, 0x1A80, 0x1A90, 0x1B50, 0x1BB0, 0x1C40, 0x1C50, 0xA620, 0xA8D0, 0xA900, 0xA9D0,
    0xA9F0, 0xAA50, 0xABF0, 0xFF10, 0x104A0, 0x10D30, 0x11066, 0x110F0, 0x11136, 0x111D0, 0x112F0,
    0x11450, 0x114D0, 0x11650, 0x116C0, 0x11730, 0x118E0, 0x11950, 0x11C50, 0x11D50, 0x11DA0, 0x16A60,
    0x16B50, 0x1D7CE, 0x1D7D8, 0x1D7E2, 0x1D7EC, 0x1D7F6, 0x1E140, 0x1E2F0, 0x1E950, 0x1FBF0,
};
#define N_ND_BLOCK ((int)(sizeof(ND_BLOCK) / sizeof(ND_BLOCK[0])))

/* Python str.isdecimal() for one codepoint, returning the digit's VALUE (0..9) or -1.
 * isdecimal, not isdigit: '²' and '①' are isdigit but int() rejects them, which is
 * exactly the crash this pins on the Python side. '٣' (Arabic-Indic three) IS decimal
 * and must read as "tri" in both implementations. */
int cyp__cp_decimal_value(long cp) {
    for (int i = 0; i < N_ND_BLOCK; i++)
        if (cp >= ND_BLOCK[i] && cp < ND_BLOCK[i] + 10) return (int)(cp - ND_BLOCK[i]);
    return -1;
}

/* The guard at the top of bangor_g2p.letter_tokens: `ch.isdecimal() or ch.isalpha()`.
 * ASCII via isalnum(), then Unicode decimal digits, then letters via cp_is_word.
 *
 * KNOWN GAP: cp_is_word knows only the four Latin ranges it lists, so any LETTER outside
 * them reads as non-alnum here and is skipped, where Python — which does consider it a
 * letter — produces an empty piece and therefore one extra word separator. Not just
 * non-Latin scripts ('α', 'д', '中'): it also misses characters that ARE Latin, among
 * them 'ª' (U+00AA), 'µ' (U+00B5), and the whole of IPA Extensions (U+0250..) and
 * Phonetic Extensions (U+1D00..) — which is an awkward gap for a phonemizer. Closing it
 * needs real Unicode letter tables. The decimal half above is closed instead because it
 * is a bounded 65-entry table, and because '٣' verbalising as "tri" is behaviour the
 * Python side already had and must not regress. (65, matching ND_BLOCK and canonical.py's
 * CANONICAL_UNICODE = 13.0.0. This said 68 -- the Unicode 15 figure -- which is the same
 * stale count b63670f corrected forty lines above and missed here.) */
int cyp__cp_is_alnum(long cp) {
    if (cp < 0x80) return isalnum((int)cp);
    if (cyp__cp_decimal_value(cp) >= 0) return 1;
    return cp_is_word(cp);
}
/* Python str.isalpha() for one codepoint, over the same Latin domain — ASCII via
 * isalpha(), then the letter ranges cp_is_word() knows (all letters). Carries the same
 * KNOWN GAP described above: a letter outside those four Latin ranges reads as a
 * non-letter. Shared with pass_deshout below and with cy_phonemize.c, which needs it to
 * recognise a hyphenated run of single typed letters ("d-d-d"); one implementation so the
 * two cannot drift. */
int cyp__cp_is_alpha(long cp) {
    if (cp < 0x80) return isalpha((int)cp);
    return cp_is_word(cp);
}
/* (cyp__lower_strip lives below, next to the lowercasing helpers it shares.) */


static const char *MONTHS[12] = {"ionawr", "chwefror", "mawrth", "ebrill", "mai", "mehefin",
                                 "gorffennaf", "awst", "medi", "hydref", "tachwedd", "rhagfyr"};
static const char *MONTH_MUT[12] = {"ionawr", "chwefror", "fawrth", "ebrill", "fai", "fehefin",
                                    "orffennaf", "awst", "fedi", "hydref", "dachwedd", "ragfyr"};

static int atoin(const char *s, int len) { int v = 0; for (int i = 0; i < len; i++) v = v * 10 + (s[i] - '0'); return v; }

/* " a"/" ac" before a year's final element, with the aspirate mutation "a" triggers.
 * Mirrors welsh_normalize._year_join. BTC: 'dwy fil ac un deg un' (vowel -> ac),
 * 'dwy fil a dau ddeg tri' (consonant -> a), 'a thri ar hugain' / 'a phedwar ugain'. */
static void year_join(char *b, const char *rest) {
    if (strchr("aeiouwy", rest[0])) { app(b, "ac"); app(b, rest); return; }
    app(b, "a");
    char first[64]; size_t k = 0;
    while (rest[k] && rest[k] != ' ' && k < sizeof(first) - 2) { first[k] = rest[k]; k++; }
    first[k] = 0;
    const char *tail = rest[k] == ' ' ? rest + k + 1 : NULL;
    char mut[66];
    if (first[0] == 'c' || first[0] == 'p' || first[0] == 't') {
        mut[0] = first[0] == 'c' ? 'c' : first[0] == 'p' ? 'p' : 't';
        mut[1] = 'h';
        snprintf(mut + 2, sizeof(mut) - 2, "%s", first + 1);
        app(b, mut);
    } else {
        app(b, first);
    }
    if (tail) app(b, tail);
}

/* A year in the register the owner chose ("mil naw wyth deg"). Mirrors
 * welsh_normalize.year_words -- see there for the BTC examples and what is derived. */
static void year_words(char *b, long y) {
    b[0] = 0;
    if (y >= 1000 && y <= 1999) {
        long r = y - 1000; int hundreds = (int)(r / 100), tu = (int)(r % 100);
        app(b, "mil");
        if (hundreds) app(b, UNITS[hundreds]);
        if (tu) two_digit_dec(b, tu);
        return;
    }
    if (y >= 2000 && y <= 2099) {
        char rest[128]; rest[0] = 0;
        two_digit_dec(rest, (int)(y - 2000));
        app(b, "dwy fil");
        if (rest[0]) year_join(b, rest);
        return;
    }
    cyp_num_to_welsh(y, b, 512);
}

static void date_words(char *b, int d, int m, long y) {
    const char *ordw = ORD[d][0];
    b[0] = 0;
    app(b, strchr("aeiouwyh", ordw[0]) ? "yr" : "y");
    app(b, ordw); app(b, "o"); app(b, MONTH_MUT[m - 1]);
    if (y >= 0) { char yb[512]; year_words(yb, y); app(b, yb); }
}

static void pass_date_num(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        int wb = !word_before(in, i);
        if (wb && isdigit((unsigned char)in[i])) {
            int j = i, ds = i;
            while (isdigit((unsigned char)in[j])) j++;
            int dl = j - ds;
            if (dl >= 1 && dl <= 2 && in[j] == '/') {
                int ms = ++j;
                while (isdigit((unsigned char)in[j])) j++;
                int ml = j - ms;
                if (ml >= 1 && ml <= 2 && in[j] == '/') {
                    int ys = ++j;
                    while (isdigit((unsigned char)in[j])) j++;
                    int yl = j - ys;
                    if (yl >= 2 && yl <= 4 && !(word_after(in, j))) {
                        int d = atoin(in + ds, dl), m = atoin(in + ms, ml);
                        long y = atoin(in + ys, yl);
                        if (d >= 1 && d <= 31 && m >= 1 && m <= 12) {
                            char db[512]; date_words(db, d, m, y);
                            strcpy(out + o, db); o += (int)strlen(db); i = j; continue;
                        }
                    }
                }
            }
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

static int match_month(const char *s, int *mnum) {  /* longest month name at s (ci); return len or 0 */
    for (int m = 0; m < 12; m++) {
        int L = (int)strlen(MONTHS[m]);
        if (strncasecmp(s, MONTHS[m], L) == 0 && !(word_after(s, L))) {
            *mnum = m + 1; return L;
        }
    }
    return 0;
}

static void pass_date_month(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        int wb = !word_before(in, i);
        if (wb && isdigit((unsigned char)in[i])) {
            int j = i, ds = i;
            while (isdigit((unsigned char)in[j])) j++;
            int dl = j - ds;
            /* \s+ (>=1) then the skip loops: Unicode via re_space_len -- the sweep */
            if (dl >= 1 && dl <= 2 && re_space_len(in, j)) {
                int ws = j; for (int sl; (sl = re_space_len(in, ws)); ) ws += sl;
                int mnum;
                int ml = match_month(in + ws, &mnum);
                if (ml) {
                    int k = ws + ml;
                    long y = -1;
                    int save = k;
                    int ws2 = k; for (int sl; (sl = re_space_len(in, ws2)); ) ws2 += sl;
                    int ys = ws2; while (isdigit((unsigned char)in[ys])) ys++;
                    if (ys - ws2 == 4 && !(word_after(in, ys))) {
                        y = atoin(in + ws2, 4); save = ys;
                    }
                    int d = atoin(in + ds, dl);
                    if (d >= 1 && d <= 31) {
                        char db[512]; date_words(db, d, mnum, y);
                        strcpy(out + o, db); o += (int)strlen(db); i = save; continue;
                    }
                }
            }
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

static const char *ORD_SUF[] = {"af", "il", "ydd", "edd", "ed", "fed", "eg", "ain", 0};
static void pass_ordinal(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        int wb = !word_before(in, i);
        if (wb && isdigit((unsigned char)in[i])) {
            int j = i;
            while (isdigit((unsigned char)in[j])) j++;
            int n = atoin(in + i, j - i);
            if (n >= 1 && n <= 31) {
                for (int t = 0; ORD_SUF[t]; t++) {
                    int L = (int)strlen(ORD_SUF[t]);
                    if (strncmp(in + j, ORD_SUF[t], L) == 0 &&
                        !(word_after(in, j + L))) {
                        const char *w = ORD[n][strcmp(ORD_SUF[t], "edd") == 0 ? 1 : 0];
                        strcpy(out + o, w); o += (int)strlen(w);
                        i = j + L; goto next;
                    }
                }
            }
        }
        out[o++] = in[i++];
    next:;
    }
    out[o] = 0;
}

/* ---------------- fractions and units ---------------- */
/* Mirrors welsh_normalize._FRACTION / _UNIT, inserted between the ordinal and currency
 * passes exactly as in Python. Both regexes are anchored by \b on each side, so the
 * boundary tests go through word_before/word_after (Unicode-aware) rather than
 * isalnum() on raw bytes. */

/* Byte length of the whitespace codepoint at s[j], or 0 if it is not whitespace — the
 * `\s?` in _UNIT, which matches ONE codepoint and may be multibyte. Python's \s is
 * Unicode (cyp__cp_is_space), so an ASCII-only test here would leave "5<NBSP>km" as
 * "pump<NBSP>km" where Python says "pum cilomedr" — a complete divergence on text that
 * is merely well typeset. (The other numeric passes in this file still take an
 * ASCII-only view of \s; that is a pre-existing divergence of the same class, measured
 * and reported, not fixed here.) */
static int re_space_len(const char *s, int j) {
    if (!s[j] || !cyp__cp_is_space(cp_at(s, j))) return 0;
    return utf8_len((unsigned char)s[j]);
}

/* Append len bytes at out[o], or -1 if that would not leave room for the terminating
 * NUL. pass_fraction and pass_unit are the file's largest expanders (a unit match grows
 * its source span by up to ~4.5x, "2l" -> "dau litr"), which is what made an unbounded
 * write in THEM reachable: they check before writing rather than running off the end of
 * cyp_normalize's 64 KB arena, and stop (truncating) when a replacement will not fit.
 *
 * READ THIS BEFORE TRUSTING THE BOUND. It fixes the unbounded write in these two passes.
 * It does NOT make cyp_normalize safe: the arena is shared, every other pass is still
 * unbounded, and a mixed input whose digits these passes decline still overflows —
 * in pass_integer, one pass later, at exactly the size it did before the bound existed.
 * Smallest overflowing input, bisected under ASan (none <=64K = no overflow found):
 *
 *     repeated input        origin/main   before the bound   with the bound
 *     "123456789 "              8212           8212              8212     <- global floor
 *     "3kg 987654321 "         10321           9467              9467     <- UNCHANGED
 *     "3kg 4 "                 30254          18742             18742     <- UNCHANGED
 *     "2l "                    39335          21849          none <=64K
 *     "1/2 "                   37467          37467          none <=64K
 *
 * So: pure unit/fraction runs no longer overflow at all, mixed ones are exactly as bad
 * as before, and these passes do lower some thresholds relative to main (30254 -> 18742)
 * because verbalising a unit genuinely produces more text. The lowest figure reachable
 * through a unit/fraction construct is 9467, above the 8212-byte pre-existing floor that
 * plain digits hit on every build, so the OVERALL worst case is unchanged.
 *
 * pass_currency's magnitude suffix is a BIGGER expander than either of these ("£5m" ->
 * "pum miliwn o bunnoedd" is 4 bytes to 21, ~5.2x) and is NOT bounded — it is the same
 * unbounded shape as every pass other than these two. Re-bisected after adding it, on
 * the same harness (figures are multiples of the pattern length, hence 8200 where the
 * table above says 8212):
 *
 *     repeated input        before the suffix      with it
 *     "123456789 "               8200               8200     <- global floor, UNCHANGED
 *     "3kg 987654321 "           9464               9464     <- UNCHANGED
 *     "£5 "                     21846              21846     <- plain currency, UNCHANGED
 *     "£999m "              none <=89532           10086     <- the new low-water mark
 *     "£5m "                none <=81536           11400
 *     "£2.5m "                  21846              11568
 *     "£1bn "                   32770              15605
 *
 * 10086 is the lowest a currency construct reaches, still above the 8200 floor that
 * plain digits hit on every build. The OVERALL worst case is again unchanged — but this
 * pass has moved closer to it than the unit pass ever did, so it is the one to bound
 * first when the arena job is picked up.
 *
 * The IDIOMATIC CLOCK (2026-07-27) is the third big expander — "11:19pm" (7 bytes)
 * becomes "pedair ar bymtheg munud wedi un ar ddeg y prynhawn" (50 bytes), ~6.3x — and
 * as of the colonless forms it is BOUNDED through put_n like fraction/unit: the
 * colonless "9yp " -> "naw o'r gloch y prynhawn " is 6.25x per repetition, just below
 * the colon worst ("11:19pm " -> 52 bytes, 6.5x), and either density was close enough
 * to pass_currency's low-water mark that adding forms without the bound would have
 * been careless. Bisection figures from when it was unbounded, kept for the record:
 *
 *     repeated input        with the idiomatic clock, unbounded
 *     "123456789 "               8200     <- global floor, UNCHANGED
 *     "11:19pm "                10288     <- the clock's low-water mark
 *     "1:26yp "                 10928
 *     "3:00 "                   23416
 *
 * With the clock bounded, pass_currency (10086) is the sole big unbounded expander
 * left and the one to bound first when the arena job is picked up; the 8200 floor that
 * plain digits hit through pass_integer is unchanged by any of this.
 *
 * The real fix is bounding the remaining passes, or one saturation check in
 * cyp_normalize; that is pre-existing, spans every pass, and is a separate hardening
 * job. Do not paper over it here. */
static int put_n(char *out, int o, int max, const char *s, int len) {
    if (len < 0 || o + len >= max) return -1;
    memcpy(out + o, s, (size_t)len);
    return o + len;
}

/* Value of a [0-9,] run as Python's int(s.replace(",", "")) would see it, but saturating
 * to -1 as soon as it exceeds 10 — every caller here only distinguishes 0..10 from
 * "larger", and saturating means an absurdly long run can never overflow. Leading zeros
 * fall out naturally ("0010" -> 10, matching int()). */
static int small_value(const char *s, int len) {
    long v = 0;
    for (int i = 0; i < len; i++) {
        if (s[i] == ',') continue;
        v = v * 10 + (s[i] - '0');
        if (v > 10) return -1;
    }
    return (int)v;
}

/* Pre-nominal feminine numerals ("rhan" is feminine); then the same forms after the
 * preposition "o", which causes soft mutation (ch/s/n/w do not mutate). Index = value. */
static const char *FEM_BEFORE_NOUN[11] = {NULL, "un", "dwy", "tair", "pedair", "pum",
                                          "chwe", "saith", "wyth", "naw", "deg"};
static const char *FEM_AFTER_O[11] = {NULL, "un", "ddwy", "dair", "bedair", "bump",
                                      "chwech", "saith", "wyth", "naw", "ddeg"};
static const char *MASC_BEFORE_NOUN[11] = {NULL, "un", "dau", "tri", "pedwar", "pum",
                                           "chwe", "saith", "wyth", "naw", "deg"};

/* Longest output is "pedair rhan o chwech" — both sides are bounded by 10. */
#define FRACTION_BUF 64
/* The spoken fraction for num/den, or NULL when Python's _fraction_repl leaves the match
 * untouched (division by zero, either side outside 1..10, or an improper fraction —
 * num >= den — which falls through to the digit pass instead of being guessed at). */
static const char *fraction_words(int num, int den, char *buf) {
    if (den <= 0) return NULL;                       /* den == 0, or > 10 (saturated -1) */
    if (num == 1 && den == 2) return "hanner";       /* the three irregulars displace */
    if (num == 1 && den == 3) return "traean";       /* the general pattern */
    if (num == 1 && den == 4) return "chwarter";
    if (num == 3 && den == 4) return "tri chwarter";
    if (num < 1 || num > 10 || den > 10 || num >= den) return NULL;
    snprintf(buf, FRACTION_BUF, "%s %s o %s", FEM_BEFORE_NOUN[num],
             num == 2 ? "ran" : "rhan",              /* soft mutation after "dwy" */
             FEM_AFTER_O[den]);
    return buf;
}

static void pass_fraction(const char *in, char *out, int max) {
    int i = 0, o = 0;
    while (in[i]) {
        if (!word_before(in, i) && isdigit((unsigned char)in[i])) {
            int a = i;
            while (isdigit((unsigned char)in[a])) a++;               /* (\d+) greedy */
            if (in[a] == '/' && isdigit((unsigned char)in[a + 1])) {
                int b = a + 1;
                while (isdigit((unsigned char)in[b])) b++;           /* (\d+) greedy */
                /* Trailing \b. No backtracking is needed to emulate re here: shrinking
                 * either (\d+) would leave a digit where the '/' or the \b must be, and
                 * digit-digit is never a boundary. */
                if (!word_after(in, b)) {
                    char fb[FRACTION_BUF];
                    const char *rep = fraction_words(small_value(in + i, a - i),
                                                     small_value(in + a + 1, b - a - 1), fb);
                    /* Either way re.sub CONSUMES the span, so the scan resumes after
                     * it. When _fraction_repl declines the match it returns it unchanged,
                     * and re-scanning inside would find a second, spurious fraction: in
                     * "11/7/8" Python's only match is the (untouched) "11/7", leaving
                     * "/8" behind, whereas restarting at the "7" would verbalise a "7/8"
                     * Python never saw. A declined match therefore still copies its span;
                     * only a match whose output will not fit stops the pass (see put_n). */
                    int no = rep ? put_n(out, o, max, rep, (int)strlen(rep))
                                 : put_n(out, o, max, in + i, b - i);
                    if (no < 0) break;                    /* out of room: truncate */
                    o = no;
                    i = b;
                    continue;
                }
            }
        }
        if (o + 1 >= max) break;
        out[o++] = in[i++];
    }
    out[o] = 0;
}

/* (plain, soft, aspirate). Soft follows dau/dwy; aspirate follows tri/chwe and applies
 * only to c/p/t, so units not starting with those repeat the plain form.
 *
 * This is the regex's alternation order (km|kg|cm|mm|m|g|l) and Python builds its
 * pattern from the matching table, so the two cannot drift. But the order is NOT what
 * makes "5mm" millimetres — the trailing \b is. "m" matches first and is then rejected
 * because a word char follows; Python's re backtracks into "mm" and the loop below
 * `continue`s to it, so swapping "m" ahead of "mm" changes no output in either
 * implementation (measured, both green). The order is belt-and-braces; the boundary
 * test on the next line down is the rule. mm is covered by tests/test_normalize.py and
 * by normalize_golden.tsv, which it was not before. */
static const struct { const char *sym, *plain, *soft, *asp; } UNITS_SPOKEN[] = {
    {"km", "cilomedr", "gilomedr", "chilomedr"},
    {"kg", "cilogram", "gilogram", "chilogram"},
    {"cm", "centimetr", "gentimetr", "chentimetr"},
    {"mm", "milimetr", "filimetr", "milimetr"},
    {"m", "metr", "fetr", "metr"},
    {"g", "gram", "ram", "gram"},
    {"l", "litr", "litr", "litr"},
    {NULL, NULL, NULL, NULL}};

static void pass_unit(const char *in, char *out, int max) {
    int i = 0, o = 0;
    while (in[i]) {
        if (!word_before(in, i) && isdigit((unsigned char)in[i])) {
            int a = i + 1;
            while (isdigit((unsigned char)in[a]) || in[a] == ',') a++;  /* \d[\d,]* greedy */
            /* (?:\.\d+)? -- the optional decimal part. Without it pass_unit ate the "5kg" of
             * "3.5kg" and orphaned the "3.", which then never reached pass_decimal: the result
             * was "tri.pum cilogram", and since "." is not a phone the model heard the nonword
             * "tripum cilogram". Owner 2026-07-28: "Tri pwynt pum cilogram". */
            int dot = -1;
            if (in[a] == '.' && isdigit((unsigned char)in[a + 1])) {
                dot = a; a++;
                while (isdigit((unsigned char)in[a])) a++;
            }
            /* \s? — greedy, but if the unit does not follow the space, the zero-width
             * alternative cannot match either (units are letters, never whitespace),
             * so one unconditional attempt is enough. Likewise the [\d,]* run always
             * stops at a non-[\d,] byte, so shrinking it can never expose a unit. */
            int ws = a + re_space_len(in, a);
            for (int u = 0; UNITS_SPOKEN[u].sym; u++) {
                int L = (int)strlen(UNITS_SPOKEN[u].sym);
                if (strncmp(in + ws, UNITS_SPOKEN[u].sym, (size_t)L) != 0) continue;
                if (word_after(in, ws + L)) continue;                  /* trailing \b */
                char digs[512];
                int nd = 0, trunc = 0;
                for (int t = i; t < a; t++) {
                    if (in[t] == ',') continue;
                    if (nd >= (int)sizeof(digs) - 1) { trunc = 1; break; }
                    digs[nd++] = in[t];
                }
                if (trunc) break;      /* pathological digit run: leave the match alone */
                digs[nd] = 0;
                if (dot >= 0) {
                    /* Decimal + unit. No 2/3/6 mutation branch can apply -- the value is not
                     * 2, 3 or 6 -- and the numeral's TAIL takes the connected form, the same
                     * positional rule reduce_cant implements for "cant". */
                    char wb[600] = "";
                    char ib[64]; int ni = 0;
                    for (int t = i; t < dot && ni < 60; t++) if (in[t] != ',') ib[ni++] = in[t];
                    ib[ni] = 0;
                    char cb[512]; cyp__num_words_for_run(ib, ni, cb);
                    app(wb, cb); app(wb, "pwynt");
                    for (int t = dot + 1; t < a; t++)
                        app(wb, in[t] == '0' ? "sero" : UNITS[in[t] - '0']);
                    reduce_connected(wb);
                    const char *noun_d = UNITS_SPOKEN[u].plain;
                    int wl = (int)strlen(wb), ul2 = (int)strlen(noun_d);
                    if (o + wl + 1 + ul2 + 1 >= max) break;
                    memcpy(out + o, wb, (size_t)wl); o += wl;
                    out[o++] = ' ';
                    memcpy(out + o, noun_d, (size_t)ul2); o += ul2;
                    i = ws + L;
                    goto next;
                }
                int n = small_value(digs, nd);
                /* >18 digits verbalise digit-by-digit at up to 7 bytes each ("chwech "),
                 * so this must hold the whole digs[] run, not just a cardinal. */
                char nb[sizeof(digs) * 7 + 8];
                const char *numeral;
                if (n >= 1 && n <= 10) numeral = MASC_BEFORE_NOUN[n];
                else { cyp__num_words_for_run(digs, nd, nb); reduce_cant(nb); numeral = nb; }
                const char *noun = (n == 2) ? UNITS_SPOKEN[u].soft
                                 : (n == 3 || n == 6) ? UNITS_SPOKEN[u].asp
                                 : UNITS_SPOKEN[u].plain;
                int nl = (int)strlen(numeral), ul = (int)strlen(noun);
                if (o + nl + 1 + ul >= max) goto done;   /* out of room: truncate */
                o = put_n(out, o, max, numeral, nl);     /* pre-checked: cannot fail */
                o = put_n(out, o, max, " ", 1);
                o = put_n(out, o, max, noun, ul);
                i = ws + L;
                goto next;
            }
        }
        if (o + 1 >= max) break;
        out[o++] = in[i++];
    next:;
    }
done:
    out[o] = 0;
}

/* ---------------- nasal mutation before blynedd / blwydd ---------------- */
/* Mirrors welsh_normalize._BLYNEDD / _blynedd_repl; the language decision, and which
 * rows are confirmed rather than proposed, is documented there.
 *
 * Not a new worst case for the 64 KB arena: a match grows its span by at most ~1.25x
 * ("5 blynedd" -> "pum mlynedd"), against pass_unit's ~4.5x. The unbounded path is the
 * shared one — a digit run too long for the table falls to cyp__num_words_for_run, the
 * same fallback pass_unit uses, sized by the same nb[] rule. */
static const struct { const char *radical, *nasal, *soft, *singular; } BLYNEDD_NOUNS[] = {
    {"blynedd", "mlynedd", "flynedd", "flwyddyn"},
    {"blwydd",  "mlwydd",  "flwydd",  NULL},
    {NULL, NULL, NULL, NULL}};

/* Mutation applied to the noun: 'n' nasal, 's' soft, '0' none. A value absent from the
 * table falls back to the plain cardinal and the radical noun. */
static const struct { int n; const char *numeral; char mut; } BLYNEDD_NUM[] = {
    {1, "un", 's'},   {2, "dwy", 's'},   {3, "tair", '0'},  {4, "pedair", '0'},
    {5, "pum", 'n'},  {6, "chwe", '0'},  {7, "saith", 'n'}, {8, "wyth", 'n'},
    {9, "naw", 'n'},  {10, "deng", 'n'}, {15, "pymtheng", 'n'}, {20, "ugain", 'n'},
    {50, "hanner can", 'n'}, {100, "can", 'n'}, {0, NULL, '0'}};

/* small_value saturates at 10; this table has rows up to 100, so it needs its own.
 * Same saturation trick, so an absurdly long run still cannot overflow. */
static int blynedd_value(const char *s, int len) {
    long v = 0;
    for (int i = 0; i < len; i++) {
        if (s[i] == ',') continue;
        v = v * 10 + (s[i] - '0');
        if (v > 100) return -1;
    }
    return (int)v;
}

/* ASCII-only case-insensitive compare, mirroring the re.I on Python's _BLYNEDD. Every
 * noun form in BLYNEDD_NOUNS is ASCII, so tolower on bytes is exact here -- this is NOT a
 * general Unicode casefold and must not be reused as one. */
static int ci_prefix(const char *s, const char *pat, int len) {
    for (int i = 0; i < len; i++) {
        unsigned char a = (unsigned char)s[i], b = (unsigned char)pat[i];
        if (!a) return 0;
        if (tolower(a) != tolower(b)) return 0;
    }
    return 1;
}

static void pass_blynedd(const char *in, char *out, int max) {
    int i = 0, o = 0;
    while (in[i]) {
        if (!word_before(in, i) && isdigit((unsigned char)in[i])) {
            int a = i + 1;
            while (isdigit((unsigned char)in[a]) || in[a] == ',') a++;  /* \d[\d,]* */
            /* \s+ (Python's, so Unicode-aware): at least one space codepoint. Unlike
             * pass_unit's \s? the space is REQUIRED — "10blynedd" is not a match. */
            int ws = a, sp;
            while ((sp = re_space_len(in, ws)) > 0) ws += sp;
            if (ws > a) {
                /* Hoisted above the noun loop: the digits do not depend on which noun
                 * matches, and extracting inside would make `break` on a pathological
                 * run skip only one spelling instead of abandoning the match. */
                char digs[512];
                int nd = 0, trunc = 0;
                for (int t = i; t < a; t++) {
                    if (in[t] == ',') continue;
                    if (nd >= (int)sizeof(digs) - 1) { trunc = 1; break; }
                    digs[nd++] = in[t];
                }
                digs[nd] = 0;
                if (!trunc) for (int u = 0; BLYNEDD_NOUNS[u].radical; u++) {
                    const char *forms[3] = {BLYNEDD_NOUNS[u].radical,
                                            BLYNEDD_NOUNS[u].nasal,
                                            BLYNEDD_NOUNS[u].soft};
                    for (int f = 0; f < 3; f++) {
                        int L = (int)strlen(forms[f]);
                        if (!ci_prefix(in + ws, forms[f], L)) continue;
                        if (word_after(in, ws + L)) continue;   /* trailing \b: "blwyddyn" */
                        int n = blynedd_value(digs, nd);
                        char nb[sizeof(digs) * 7 + 8];
                        const char *numeral, *noun;
                        int r = 0;
                        while (BLYNEDD_NUM[r].numeral && BLYNEDD_NUM[r].n != n) r++;
                        if (BLYNEDD_NUM[r].numeral) {
                            numeral = BLYNEDD_NUM[r].numeral;
                            if (n == 1 && BLYNEDD_NOUNS[u].singular)
                                noun = BLYNEDD_NOUNS[u].singular;
                            else
                                noun = BLYNEDD_NUM[r].mut == 'n' ? BLYNEDD_NOUNS[u].nasal
                                     : BLYNEDD_NUM[r].mut == 's' ? BLYNEDD_NOUNS[u].soft
                                     : BLYNEDD_NOUNS[u].radical;
                        } else {
                            /* Off the table. An 11+ COMPOUND numeral takes the plural
                             * ("o flynyddoedd", BTC's counted-noun rule); a non-compound
                             * one takes the NASAL, per "treiglo'n drwynol ar ol pob
                             * rhifolyn ar wahan i 2, 3, 4 a 6". 12/18/40/60/80 used to fall
                             * between the two and get neither. Mirrors _blynedd_repl. */
                            cyp__num_words_for_run(digs, nd, nb);
                            char cb[sizeof(nb) + 32];   /* room for the longest numeral */
                            long nv = n < 0 ? 999 : n;
                            if (nv != 2 && nv != 3 && nv != 4 && nv != 6
                                    && !is_compound_numeral(nb))
                                snprintf(cb, sizeof(cb), "%s %s", nb, BLYNEDD_NOUNS[u].nasal);
                            else
                                counted_noun(cb, sizeof(cb), nb, nv,
                                             BLYNEDD_NOUNS[u].radical);
                            int cl = (int)strlen(cb);
                            if (o + cl >= max) goto done;
                            o = put_n(out, o, max, cb, cl);
                            i = ws + L;
                            goto next;
                        }
                        int nl = (int)strlen(numeral), ul = (int)strlen(noun);
                        if (o + nl + 1 + ul >= max) goto done;  /* out of room: truncate */
                        o = put_n(out, o, max, numeral, nl);    /* pre-checked */
                        o = put_n(out, o, max, " ", 1);
                        o = put_n(out, o, max, noun, ul);
                        i = ws + L;
                        goto next;
                    }
                }
            }
        }
        if (o + 1 >= max) break;
        out[o++] = in[i++];
    next:;
    }
done:
    out[o] = 0;
}

/* ---------------- currency, time, symbols ---------------- */
/* At and above 1000 a pounds amount takes "o bunnoedd", not the singular "punt".
 * Owner 2026-07-28, answering with the phrase itself: "Mil o bunnoedd". Mirrors
 * welsh_normalize._pounds_plural / _POUNDS_PLURAL_FROM, where the full reasoning lives.
 * The defect it settles was not taste: the SAME amount read two ways depending only on how
 * it was typed -- "£1000000" said "un miliwn punt" while "£1m" said "un miliwn o bunnoedd".
 *
 * NO reduce_cant here, deliberately: it fires only where the numeral DIRECTLY touches the
 * noun, and "o" now sits between them. "£1500" is "mil pum cant o bunnoedd", while "£100"
 * is below the threshold with the noun still touching, so it stays "can punt". */
#define POUNDS_PLURAL_FROM 1000L

static void pounds_plural(char *b, long n) {
    char nb[512];
    cyp_num_to_welsh(n, nb, sizeof(nb));
    /* Bare "mil o bunnoedd", the owner's call and a deliberate exception to the "un mil"
     * ruling, scoped to this phrase: the cardinal 1000 is still "un mil" and the year
     * register keeps its own bare "mil".
     * Exact match or a following SPACE, never a prefix test -- "un miliwn" starts with
     * "un mil", so a prefix test would strip the "un" off every million and billion too and
     * silently change "£1m", which this ruling was not about. "un miliwn"/"un biliwn" keep
     * their "un": that is what has always shipped and nobody objected. */
    const char *p = nb;
    if (!strcmp(nb, "un mil") || !strncmp(nb, "un mil ", 7)) p = nb + 3;
    snprintf(b, 700, "%s o bunnoedd", p);
}

/* The digit-string form, for the magnitude-suffix path: that path deliberately never builds
 * an integer (see scaled_cardinal), so the "un mil" -> "mil" strip has to work on the words
 * rather than on n. */
static void pounds_plural_str(char *b, size_t cap, const char *digits, int nd) {
    char nb[4096];
    cyp__num_words_for_run(digits, nd, nb);
    const char *p = nb;
    if (!strcmp(nb, "un mil") || !strncmp(nb, "un mil ", 7)) p = nb + 3;
    /* `cap` rather than a hardcoded size: cyp__num_words_for_run's worst case is ~3.6 KB
     * (a pathological digit run read digitwise), so a 700-byte buffer would truncate
     * mid-word -- silently, which is the failure mode counted_noun was already fixed for. */
    snprintf(b, cap, "%s o bunnoedd", p);
}

static void pounds(char *b, long n) {
    switch (n) {
    case 1: strcpy(b, "un bunt"); return;
    case 2: strcpy(b, "dwy bunt"); return;
    case 3: strcpy(b, "tair punt"); return;
    case 4: strcpy(b, "pedair punt"); return;
    case 5: strcpy(b, "pum punt"); return;
    case 6: strcpy(b, "chwe phunt"); return;
    case 7: strcpy(b, "saith bunt"); return;   /* BTC: punt mutates after saith/wyth */
    case 8: strcpy(b, "wyth bunt"); return;
    case 100: strcpy(b, "can punt"); return;
    }
    if (n >= POUNDS_PLURAL_FROM) { pounds_plural(b, n); return; }
    char nb[512]; cyp_num_to_welsh(n, nb, 512);
    reduce_cant(nb);            /* "£200" -> "dau gan punt", matching _POUND's hand-cased 100 */
    counted_noun(b, 640, nb, n, "punt");
}

/* The singular form for an amount at or above the threshold that CARRIES PENCE. Owner
 * 2026-07-28: "o bunnoedd" mid-phrase is clumsy, so "£1234.56" stays "...tri deg pedwar punt
 * pum deg chwech ceiniog". Only a pounds-only amount takes the plural. */
static void pounds_with_pence(char *b, long n) {
    char nb[512]; cyp_num_to_welsh(n, nb, 512);
    reduce_cant(nb);
    counted_noun(b, 640, nb, n, "punt");
}

/* "<numeral> ceiniog" with both BTC rules that apply: the connected forms (pum/chwe/can)
 * and the soft mutation after saith/wyth. Mirrors welsh_normalize._pence_words. Both pence
 * sites go through here -- the currency path used to build its own string, so "£1.07" said
 * "saith ceiniog" while a bare "7c" said "saith geiniog". */
static void pence_words(char *b, long n) {
    char nb[512];
    if (n >= 1 && n <= 10) snprintf(nb, sizeof(nb), "%s", MASC_BEFORE_NOUN[n]);
    else { cyp_num_to_welsh(n, nb, sizeof(nb)); reduce_cant(nb); }
    counted_noun(b, 640, nb, n, "ceiniog");
}


static long atoin_commas(const char *s, int len) {
    long v = 0; for (int i = 0; i < len; i++) if (s[i] != ',') v = v * 10 + (s[i] - '0'); return v;
}

/* A magnitude suffix starting at s[j], at a word boundary: its zero count (3/6/9) and,
 * through *len_out, its byte length. 0 when there is none. The suffixes are ASCII, so
 * strncasecmp cannot fold a UTF-8 continuation byte onto one of them. */
static int magnitude_at(const char *s, int j, int *len_out) {
    for (int u = 0; MAGNITUDE[u].sym; u++) {
        int L = (int)strlen(MAGNITUDE[u].sym);
        if (strncasecmp(s + j, MAGNITUDE[u].sym, (size_t)L) != 0) continue;
        if (word_after(s, j + L)) continue;                      /* trailing \b */
        *len_out = L;
        return MAGNITUDE[u].zeros;
    }
    return 0;
}

/* pass_unit's own left edge (`\s?(km|kg|...)\b`), tested where a currency amount ends.
 * pass_currency now runs BEFORE pass_unit, so it is the one that has to yield. */
static int unit_follows(const char *s, int j) {
    int ws = j + re_space_len(s, j);
    for (int u = 0; UNITS_SPOKEN[u].sym; u++) {
        int L = (int)strlen(UNITS_SPOKEN[u].sym);
        if (strncmp(s + ws, UNITS_SPOKEN[u].sym, (size_t)L) != 0) continue;
        if (word_after(s, ws + L)) continue;
        return 1;
    }
    return 0;
}

/* Longest amount pass_currency will scale. Python has no such limit; this is the same
 * class as the `long` in atoin_commas below (which already truncates a plain amount at
 * 19 digits), only ~27x further out. Beyond it the match is copied verbatim. */
#define CUR_DIGITS 512

/* Cardinal for a scaled currency amount, from its digit string — the C mirror of
 * welsh_normalize._scaled_cardinal, and string-based for the same reason: no amount,
 * however absurd, can overflow an integer on the way through.
 *
 * ABSORBED 2026-07-28, same as its Python counterpart. This hand-rolled the billions
 * split because cyp_num_to_welsh digit-spelled everything above 999,999,999 — but it was
 * reachable ONLY from a currency amount carrying a magnitude suffix, so the same amount
 * written out in full digits still said nine "dim"s. cyp_num_to_welsh owns the biliwn tier
 * now, so every caller gets it and this is a pass-through; cyp__num_words_for_run supplies
 * the leading-zero strip and the >18-digit fallback it used to do itself.
 *
 * Fixing it there also corrected three wrong multipliers for free, because the tier goes
 * through scale() like mil and miliwn do — see biliwn_special.
 *
 * "biliwn" is the one word here NOT in the verified reference set — it cannot be, since
 * the reference stops below a billion. SIGNED OFF: native-speaker review confirmed the word and cited
 * GPC (attested 1725); see docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md §3. */
static void scaled_cardinal(const char *d, int n, char *out) {
    cyp__num_words_for_run(d, n, out);
}

static void pass_currency(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        if ((unsigned char)in[i] == 0xC2 && (unsigned char)in[i + 1] == 0xA3) {  /* £ */
            int j = i + 2;
            /* _CURRENCY's `\s?` — Unicode, like every other \s in Python, so the same
             * re_space_len unit_follows uses. A literal-' ' test made "£<NBSP>5m" read
             * "£ pum metr" (five metres, £ left dangling) where Python says "pum miliwn
             * o bunnoedd": 28 of the 29 whitespace codepoints diverged. Harmless before
             * the magnitude suffix existed -- both sides then yielded to the unit pass
             * identically -- and NBSP before an amount is ordinary web-copied text. */
            j += re_space_len(in, j);              /* optional single whitespace codepoint */
            if (isdigit((unsigned char)in[j])) {
                int ds = j;
                while (isdigit((unsigned char)in[j]) || in[j] == ',') j++;
                int de = j;                        /* end of the \d[\d,]* run */
                int ps = -1, pe = -1;              /* the optional .(\d{1,2}) */
                if (in[j] == '.' && isdigit((unsigned char)in[j + 1])) {
                    ps = j + 1; pe = ps;
                    while (isdigit((unsigned char)in[pe]) && pe - ps < 2) pe++;
                    j = pe;
                }
                int msl = 0, zeros = magnitude_at(in, j, &msl);
                if (!zeros && unit_follows(in, j)) {
                    /* Yield: whenever pass_unit would have claimed these digits, hand
                     * the whole match back untouched and let it, so putting currency
                     * first does not turn "£5kg" into "pum puntkg". A magnitude suffix
                     * wins outright — that is the point of the reorder. */
                    while (i < j) out[o++] = in[i++];
                    continue;
                }
                if (zeros) {
                    char digs[CUR_DIGITS + 16];
                    int nd = 0, trunc = 0;
                    for (int t = ds; t < de; t++) {
                        if (in[t] == ',') continue;
                        if (nd >= CUR_DIGITS) { trunc = 1; break; }
                        digs[nd++] = in[t];
                    }
                    if (!trunc) {
                        for (int t = ps; t < pe; t++) digs[nd++] = in[t];
                        for (int t = (ps >= 0 ? pe - ps : 0); t < zeros; t++) digs[nd++] = '0';
                        digs[nd] = 0;
                        char sb[(CUR_DIGITS + 16) * 7 + 16];
                        scaled_cardinal(digs, nd, sb);
                        /* "o bunnoedd" (plural after "o", soft mutation p->b), not the
                         * singular "punt" of the small-amount table: PENDING
                         * NATIVE-SPEAKER SIGN-OFF, same as the fraction/unit forms. */
                        /* Through pounds_plural so the suffix and digit spellings of the
                         * same amount agree -- "£1k" and "£1000" both say "mil o bunnoedd".
                         * Before the 2026-07-28 ruling this path was the ONLY one saying
                         * "o bunnoedd", which is what made them disagree. */
                        (void)sb;
                        char pl[4300]; pounds_plural_str(pl, sizeof(pl), digs, nd);
                        o += sprintf(out + o, "%s", pl);
                        /* Mirrors _currency_repl's _sep_if_latin_tail. Unreachable for
                         * ASCII letters (the suffix's own trailing \b would have failed)
                         * -- kept for symmetry with the Python repl, which applies the
                         * separator to both returns. */
                        if (digit_seq_sep(in, j + msl)) out[o++] = ' ';
                        i = j + msl;
                        continue;
                    }
                    while (i < j) out[o++] = in[i++];   /* absurd digit run: leave it */
                    continue;
                }
                long n = atoin_commas(in + ds, de - ds);
                char pb[700];
                /* Pence present and at/above the threshold -> singular (owner 2026-07-28);
                 * a pounds-only amount goes through pounds(), which applies the plural. */
                int has_pence = 0;
                if (ps >= 0 && atoin(in + ps, pe - ps) > 0) has_pence = 1;
                if (has_pence && n >= POUNDS_PLURAL_FROM) pounds_with_pence(pb, n);
                else pounds(pb, n);
                strcpy(out + o, pb); o += (int)strlen(pb);
                if (ps >= 0) {
                    int pv = atoin(in + ps, pe - ps);
                    if (pv > 0) { char cb[700]; pence_words(cb, pv);
                        o += sprintf(out + o, " %s", cb); }
                }
                /* "£5x" -> "pum punt x", not the glued nonword "pum puntx". The splitter
                 * cannot do it: this pass runs first and the replacement's letters erase
                 * the boundary. Mirrors _currency_repl's _sep_if_latin_tail. */
                if (digit_seq_sep(in, j)) out[o++] = ' ';
                i = j; continue;
            }
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

/* ---------------- the idiomatic clock (mirrors welsh_normalize._time_repl) ----------
 * Language decision 2026-07-26: the owner chose the idiomatic register ("o'r gloch",
 * "chwarter wedi", "hanner awr wedi", "chwarter i", "N munud wedi/i") over the previous
 * digital one ("deg tri deg"). Only that register, the "i"-triggers-soft-mutation rule
 * and the traditional-numerals-for-minutes choice are the VERIFIED reference; every
 * individual hour/minute WORD below is derived and pending native-speaker sign-off, and
 * the tables here are a transcription of the Python ones — see welsh_normalize.py and
 * docs/NORMALIZATION-FRACTIONS-UNITS-REVIEW.md §5 for the reasoning and the review
 * surface. Do NOT re-derive them here: this file must match that one word for word. */

/* Traditional cardinal hours 1-12 (11/12 are the vigesimal "un ar ddeg"/"deuddeg", not
 * the decimal register's "un deg un"/"un deg dau"), plain and soft-mutated. The mutated
 * column is used after "i" (to) — the one mutation the verified reference names
 * explicitly ("chwarter i ddau"); ch/vowels/s/n do not mutate. Index = hour. */
static const char *HOUR_TRAD[13] = {NULL, "un", "dau", "tri", "pedwar", "pump", "chwech",
                                    "saith", "wyth", "naw", "deg", "un ar ddeg", "deuddeg"};
static const char *HOUR_TRAD_MUT[13] = {NULL, "un", "ddau", "dri", "bedwar", "bump", "chwech",
                                        "saith", "wyth", "naw", "ddeg", "un ar ddeg", "ddeuddeg"};
/* Traditional cardinal minutes 1-29 (feminine agreement: "munud" is feminine, so 2/3/4
 * take dwy/tair/pedair). 15 is NULL because it can never be reached — 15/30/45 are the
 * chwarter/hanner-awr forms, and the "i" branch's complement 60-mm lands in 1..29 too, so
 * a NULL here trips a wrong caller instead of quietly reading a neighbouring word.
 * Compound forms keep the CITATION numeral (pump/chwech), not the pre-nominal reduction:
 * "munud" does not directly follow the leading digit there ("ar hugain" intervenes), so
 * 25 is "pump ar hugain munud". */
static const char *MINUTE_TRAD[30] = {
    NULL, "un", "dwy", "tair", "pedair", "pump", "chwech", "saith", "wyth", "naw", "deg",
    "un ar ddeg", "deuddeg", "tair ar ddeg", "pedair ar ddeg", NULL, "un ar bymtheg",
    "dwy ar bymtheg", "deunaw", "pedair ar bymtheg", "ugain", "un ar hugain",
    "dwy ar hugain", "tair ar hugain", "pedair ar hugain", "pump ar hugain",
    "chwech ar hugain", "saith ar hugain", "wyth ar hugain", "naw ar hugain"};
/* Standalone (non-compound) minute counts DO take the pre-nominal reduction, because
 * "munud" directly follows: pum/chwe and the archaic nasal "deng". 1/2 additionally soft-
 * mutate the noun itself (m -> f). NULL = fall through to MINUTE_TRAD + " munud". */
static const char *MINUTE_STANDALONE[11] = {NULL, "un funud", "dwy funud", NULL, NULL,
                                            "pum munud", "chwe munud", NULL, NULL, NULL,
                                            "deng munud"};
/* Am/pm-style markers, in _TIME's alternation order. Welsh "yb"/"y.b." (y bore),
 * "yp"/"y.p." (y prynhawn) and "yh"/"y.h." (yr hwyr), plus the English-influenced
 * "am"/"pm" Welsh text borrows verbatim -- in both its bare and dotted ("a.m."/"p.m.")
 * spellings. Matched case-insensitively: _TIME carries re.I.
 *
 * The DOTTED forms must come first: "yh" would otherwise match the first two characters
 * of "y.h."... it cannot (the third character differs), but "y.h." vs "yh" share a prefix
 * in the other direction, so keeping re's order removes the question entirely.
 *
 * The marker loop in pass_time does `break` (not `continue`) when the trailing (?!\w)
 * fails. That is equivalent to re's backtracking ONLY while no marker is a proper prefix
 * of another, so at most one marker can match at a given position. Re-checked with the
 * dotted English forms added: "am"/"a.m." differ at char 2, "pm"/"p.m." likewise -- the
 * property still holds. If a future marker breaks it, switch the loop to continue.
 *
 * "yh" is here because authors write it. BTC names it in order to recommend AGAINST
 * writing it ("10am hyd 4pm, nid ... '10yb hyd 4yh'") -- advice to writers, not to a
 * reader, and a TTS reads what is in front of it. Before this, "16:00yh" failed the whole
 * time match on the trailing (?!\w) and fell to the integer pass as "un deg
 * chwech:seroyh". "a.m."/"p.m." earned their place the same way, but worse: the collapsed
 * "7:00p.m." match let _PENCE read the minute digits as money ("saith sero ceiniog.m."). */
static const char *TIME_MARKERS[] = {"y.b.", "yb", "y.p.", "yp", "y.h.", "yh",
                                     "a.m.", "am", "p.m.", "pm", NULL};

/* y bore / y prynhawn / yr hwyr — ONLY from explicit information, never invented. An
 * explicit marker wins; failing that, an hour >= 13 is unambiguous on its own (24h
 * notation) and may take the qualifier its own reading of the day implies. An hour of 12
 * or less with no marker is genuinely ambiguous in the 12-hour reading the traditional
 * numerals speak, and gets nothing: a bare "3:00" is "tri o'r gloch", full stop. */
static const char *clock_qualifier(int h, const char *marker, int mlen) {
    if (mlen) {
        if ((mlen == 4 && strncasecmp(marker, "y.b.", 4) == 0) ||
            (mlen == 4 && strncasecmp(marker, "a.m.", 4) == 0) ||
            (mlen == 2 && strncasecmp(marker, "yb", 2) == 0) ||
            (mlen == 2 && strncasecmp(marker, "am", 2) == 0)) return "y bore";
        if ((mlen == 4 && strncasecmp(marker, "y.p.", 4) == 0) ||
            (mlen == 4 && strncasecmp(marker, "p.m.", 4) == 0) ||
            (mlen == 2 && strncasecmp(marker, "yp", 2) == 0) ||
            (mlen == 2 && strncasecmp(marker, "pm", 2) == 0)) return "y prynhawn";
        /* yr hwyr, NOT y prynhawn: "yh" names the evening. "pm" stays y prynhawn as it
         * always did -- English pm spans both halves, and choosing a side for it would be
         * inventing information the author did not give. */
        if ((mlen == 4 && strncasecmp(marker, "y.h.", 4) == 0) ||
            (mlen == 2 && strncasecmp(marker, "yh", 2) == 0)) return "yr hwyr";
    }
    if (h >= 13) {
        if (h <= 17) return "y prynhawn";
        if (h <= 23) return "yr hwyr";
    }
    return NULL;   /* h <= 12 with no marker, or an out-of-range 24..99 */
}

/* "pum munud" / "pump ar hugain munud" for n in 1..14, 16..29 (see the tables). */
static const char *minute_phrase(int n, char *buf, size_t cap) {
    if (n >= 1 && n <= 10 && MINUTE_STANDALONE[n]) return MINUTE_STANDALONE[n];
    snprintf(buf, cap, "%s munud", MINUTE_TRAD[n]);
    return buf;
}

static void pass_time(const char *in, char *out, int max) {
    int i = 0, o = 0;
    while (in[i]) {
        int wb = !word_before(in, i);
        if (wb && isdigit((unsigned char)in[i])) {
            int j = i;
            while (isdigit((unsigned char)in[j])) j++;
            int hl = j - i;
            /* \b(\d{1,2}):([0-5]\d) — the minute class is [0-5]\d, NOT \d\d, so ":99" is
             * simply not a time in either implementation and its digits fall through to
             * the number pass ("3:99" -> "tri:naw deg naw"). Reading it as \d\d here fed
             * 99 to the minute tables. */
            /* The HOUR is bounded 0-23 too, mirroring Python's ([01]?\d|2[0-3]). Leaving
             * it \d{1,2} while the h % 12 reduction existed made nonsense sound plausible:
             * "90:00" read as "chwech o'r gloch", "99:59" as "un funud i bedwar". */
            int hv = hl == 1 ? in[i] - '0' : (in[i] - '0') * 10 + (in[i + 1] - '0');
            if (hl >= 1 && hl <= 2 && hv <= 23) {
                int matched = 0, mm = 0, mend = 0;
                const char *mk = NULL;
                int mlen = 0;
                if (in[j] == ':' &&
                    in[j + 1] >= '0' && in[j + 1] <= '5' && isdigit((unsigned char)in[j + 2])) {
                    int end = j + 3;                    /* just past the two minute digits */
                    mend = end;
                    /* (?:\s?(y\.b\.|...|pm))?(?!\w). Greedy: try the marker after one
                     * optional whitespace CODEPOINT (Python's \s is Unicode, hence
                     * re_space_len, not ' '), then directly, then fall back to no marker
                     * at all — which is exactly how re backtracks when the alternation
                     * matches but the trailing (?!\w) then fails ("3:00pmx" is not a
                     * time, and "3:00 y.b" is a time with no marker and a literal " y.b"
                     * left behind). */
                    for (int sp = 1; sp >= 0 && !mlen; sp--) {
                        int ms = end + (sp ? re_space_len(in, end) : 0);
                        if (sp && ms == end) continue;  /* no whitespace: same as the sp=0 try */
                        for (int t = 0; TIME_MARKERS[t]; t++) {
                            int L = (int)strlen(TIME_MARKERS[t]);
                            if (strncasecmp(in + ms, TIME_MARKERS[t], (size_t)L) != 0) continue;
                            if (word_after(in, ms + L)) break;   /* (?!\w) fails -> no marker */
                            mk = in + ms; mlen = L; mend = ms + L;
                            break;
                        }
                    }
                    if (mlen || !word_after(in, end)) {
                        matched = 1;
                        mm = atoin(in + j + 1, 2);
                    }
                } else if (i == 0 || (in[i - 1] != ':' && in[i - 1] != '.' && in[i - 1] != ',')) {
                    /* The colonless clock: H(marker) and H.MM(marker), _TIME_NOCOLON's
                     * mirror. The marker is REQUIRED and GLUED (no whitespace try): "am"
                     * is a Welsh preposition, and a spaced allowance turns "5 am ddim"
                     * (five for free) into a clock reading. The byte lookbehind above is
                     * (?<![:.,]): a failed colon/decimal/comma context ("25:00pm",
                     * "99.15pm", "1,23pm") must not have its tail digits read as a
                     * plausible time -- out-of-range input falls to the number passes,
                     * audibly wrong rather than silently wrong. */
                    int ms = j;
                    if (in[j] == '.' &&
                        in[j + 1] >= '0' && in[j + 1] <= '5' && isdigit((unsigned char)in[j + 2])) {
                        ms = j + 3;                     /* dotted-hour minutes: "7.30pm" */
                        mm = atoin(in + j + 1, 2);
                    }
                    /* No marker starts with '.', so when the dotted-minute sniff consumed
                     * ".MM" there is no second, minute-less marker position to retry --
                     * this needs no backtracking arm to stay equivalent to re. */
                    for (int t = 0; TIME_MARKERS[t]; t++) {
                        int L = (int)strlen(TIME_MARKERS[t]);
                        if (strncasecmp(in + ms, TIME_MARKERS[t], (size_t)L) != 0) continue;
                        if (word_after(in, ms + L)) break;       /* (?!\w) fails */
                        mk = in + ms; mlen = L;
                        break;
                    }
                    if (mlen) {
                        matched = 1;
                        mend = ms + mlen;
                    } else {
                        mm = 0;   /* discard a dotted-minute sniff that found no marker */
                    }
                }
                if (matched) {
                    /* mm defaults to 0: a colonless "7pm" is on the hour, which is
                     * behaviourally identical to ":00" -- no sentinel needed (Python maps
                     * a None minute group to 0 the same way). h from hv, which equals the
                     * old atoin(in + i, hl) re-parse by construction. */
                    int h = hv;
                    const char *qual = clock_qualifier(h, mk, mlen);
                    int h12 = h % 12;
                    if (h12 == 0) h12 = 12;             /* h % 12 or 12 */
                    int nxt = h12 % 12 + 1;             /* the hour "i" counts down to */
                    char mb[64], core[256];
                    if (mm == 0)       snprintf(core, sizeof core, "%s o'r gloch", HOUR_TRAD[h12]);
                    else if (mm == 15) snprintf(core, sizeof core, "chwarter wedi %s", HOUR_TRAD[h12]);
                    else if (mm == 30) snprintf(core, sizeof core, "hanner awr wedi %s", HOUR_TRAD[h12]);
                    else if (mm == 45) snprintf(core, sizeof core, "chwarter i %s", HOUR_TRAD_MUT[nxt]);
                    else if (mm < 30)  snprintf(core, sizeof core, "%s wedi %s",
                                                minute_phrase(mm, mb, sizeof mb), HOUR_TRAD[h12]);
                    else               snprintf(core, sizeof core, "%s i %s",
                                                minute_phrase(60 - mm, mb, sizeof mb), HOUR_TRAD_MUT[nxt]);
                    /* One bounded write per match, pass_fraction's convention: build the
                     * whole replacement first, so a truncation can never leave half a
                     * reading ("chwarter i" with no hour) in the arena. */
                    char full[320];
                    int fl = snprintf(full, sizeof full, "%s%s%s",
                                      core, qual ? " " : "", qual ? qual : "");
                    int no = put_n(out, o, max, full, fl);
                    if (no < 0) break;
                    o = no;
                    i = mend;
                    continue;
                }
            }
        }
        if (o + 1 >= max) break;
        out[o++] = in[i++];
    }
    out[o] = 0;
}

static void pass_pence(const char *in, char *out) {
    int i = 0, o = 0;
    while (in[i]) {
        /* (?<![A-Za-z]): the pence rule must not fire inside an alphanumeric code
         * ("s4c" read its "4c" as fourpence). Python's [A-Za-z] is ASCII-only, so the
         * lookbehind must test the previous BYTE against ASCII A-Za-z explicitly:
         * isalpha() is locale-dependent on the >=0x80 UTF-8 continuation bytes of an
         * accented letter (e.g. the 0xAA of "ê"), which made "ê9p" diverge from Python. */
        unsigned char prev = i > 0 ? (unsigned char)in[i - 1] : 0;
        int prev_ascii_alpha = (prev >= 'A' && prev <= 'Z') || (prev >= 'a' && prev <= 'z');
        if (isdigit((unsigned char)in[i]) && !prev_ascii_alpha) {
            int j = i;
            while (isdigit((unsigned char)in[j]) || in[j] == ',') j++;
            if ((in[j] == 'p' || in[j] == 'c') && !(word_after(in, j + 1))) {
                char cb[700]; pence_words(cb, atoin_commas(in + i, j - i));
                o += sprintf(out + o, "%s", cb);
                i = j + 1; continue;
            }
        }
        out[o++] = in[i++];
    }
    out[o] = 0;
}

/* The digit/letter SPLITTER: one space at every ASCII-digit <-> Latin-letter/_ boundary,
 * both directions. FOLLOWUPS section G's "general digit/letter peeling job" -- it lives
 * here, late in the normaliser, not in the G2P as that section first suggested: by G2P
 * time the wrong verbalisation is already baked ("x05" -> "xpump" happens in
 * pass_integer, and phonemize skips a bare digit token). Driver placement is
 * load-bearing on both edges and mirrors Python exactly -- AFTER every pass that
 * legitimately consumes letter-adjacent digits (ordinal "3af", currency "£5M", unit
 * "5km", blynedd, time "7pm"/"12:30yb", pence "50p" -- whose ASCII lookbehind is what
 * keeps the "4c" of "s4c" from reading as fourpence, and which this pass would defeat
 * if it ran first) and after pass_email_url; BEFORE math/percent/decimal/digit-seq/
 * integer, whose guards then see the boundary as real (digit_seq_start_ok's deliberate
 * lookbehind is untouched -- "x 05" now reaches the digit register where "x05" fell
 * through to pass_integer and lost its zero).
 *
 * ASCII digits and Latin letters ONLY (cyp__cp_is_alpha + '_', the digit_seq_sep
 * class): "0800α" keeps its accepted, disclosed divergence exactly as it is, and "٣05"
 * stays untouched on both sides -- this pass can see neither. Bounded: worst case is
 * alternating "a1a1..." at just under 2x, which WOULD overflow the shared arena on a
 * 64K input without put_n. Mirrors welsh_normalize._DIGIT_LETTER_BOUNDARY. */
static void pass_digit_letter_split(const char *in, char *out, int max) {
    int i = 0, o = 0, prev = 0;      /* 0 = other, 1 = ASCII digit, 2 = Latin letter/_ */
    while (in[i]) {
        long cp = cp_at(in, i);
        int adv = utf8_len((unsigned char)in[i]);
        int cur = (cp >= '0' && cp <= '9') ? 1
                : (cyp__cp_is_alpha(cp) || cp == '_') ? 2 : 0;
        int no;
        if ((prev == 1 && cur == 2) || (prev == 2 && cur == 1)) {
            no = put_n(out, o, max, " ", 1);
            if (no < 0) break;
            o = no;
        }
        no = put_n(out, o, max, in + i, adv);
        if (no < 0) break;
        o = no;
        i += adv;
        prev = cur;
    }
    out[o] = 0;
}

static void pass_symbols(const char *in, char *out, int max) {
    int i = 0, o = 0;
    while (in[i]) {
        char c = in[i];
        int no;
        if ((c == '+' || c == '=' || c == '@') && i > 0 && in[i - 1] == ' ' && in[i + 1] == ' ') {
            const char *r = c == '+' ? "plws" : c == '=' ? "yn hafal i" : "at";
            no = put_n(out, o, max, r, (int)strlen(r));
            if (no < 0) break;
            o = no;
            i++; continue;
        }
        /* The same three, LETTER-ADJACENT ("a+b") -- the fusion class again: unspoken,
         * the symbol vanished at the phone layer and its sides fused into one nonword.
         * The words are the approved registers above, only the context widens; both
         * sides must be word chars, so "C++"/"A+"/"A+ grade" stay codes. Mirrors
         * welsh_normalize._symbols' _C_WORD_CLASS rules (same disclosed Latin-only
         * cp_is_word domain). */
        if ((c == '+' || c == '=' || c == '@') && word_before(in, i) && word_after(in, i + 1)) {
            const char *r = c == '+' ? " plws " : c == '=' ? " yn hafal i " : " at ";
            no = put_n(out, o, max, r, (int)strlen(r));
            if (no < 0) break;
            o = no;
            i++; continue;
        }
        /* A "/", ":" or "*" between two word characters becomes a space. Mirrors
         * Python's _FUSING_PUNCT_BETWEEN_WORDS; see welsh_normalize._symbols for why
         * (the two sides used to fuse into one word and reach letter-to-sound as a
         * nonword; "*" has no approved spoken word, so the space is the conservative
         * floor). word_before/word_after are the same \w this file uses everywhere
         * else, so this inherits the disclosed Latin-only cp_is_word gap rather than
         * introducing a new one. */
        if ((c == '/' || c == ':' || c == '*') && word_before(in, i) && word_after(in, i + 1)) {
            no = put_n(out, o, max, " ", 1);
            if (no < 0) break;
            o = no;
            i++; continue;
        }
        if (o + 1 >= max) break;
        out[o++] = in[i++];
    }
    out[o] = 0;
}

/* ---------------- de-shout (mirrors welsh_normalize._deshout) ---------------- */
/* (Unicode isalpha over the Latin domain we support is cyp__cp_is_alpha, above.) */
/* Lowercase codepoint cp into out at offset o the way Python str.lower() does over
 * our Latin domain (İ -> "i" + U+0307, matching pass_lower_collapse). */
static int put_lower_cp(char *out, int o, long cp) {
    if (cp == 0x0130) { o = put_cp(out, o, 'i'); return put_cp(out, o, 0x0307); }
    return put_cp(out, o, lower_accent_cp(cp));
}
/* Props of the word spanning bytes [start,end): a fully-uppercase "caps word" is
 * w.isupper() (>=1 upper, 0 lower cased letter) AND has >=2 alpha chars AND no
 * digit — a digit-bearing code (S4C, A55) is never "shouting" and must reach the
 * acronym pass in caps. has_alpha is any(c.isalpha()). */
static void deshout_word_props(const char *s, int start, int end, int *is_caps, int *has_alpha) {
    int upper = 0, lower = 0, alpha = 0, digit = 0;
    for (int j = start; j < end;) {
        long cp = cp_at(s, j);
        j += utf8_len((unsigned char)s[j]);
        if (cp >= '0' && cp <= '9') digit++;
        else if (cyp__cp_is_alpha(cp)) {
            alpha++;
            if (lower_accent_cp(cp) != cp) upper++; else lower++;
        }
    }
    *has_alpha = alpha >= 1;
    *is_caps = (upper >= 1 && lower == 0 && alpha >= 2 && digit == 0);
}
static int deshout_is_space(unsigned char b) {
    return b == ' ' || b == '\t' || b == '\n' || b == '\r' || b == '\f' || b == '\v';
}
/* A lone acronym (BBC, S4C) in normal-case text must still be letter-spelled, but a run
 * of mostly-uppercase words is emphasis ("CROESO I GYMRU"), not a string of acronyms.
 * Trigger: caps words >=2 AND at least half the alphabetic words -> lower-case the caps
 * words before the acronym pass. On trigger, rejoin single-spaced (Python
 * " ".join(text.split())); otherwise leave the text byte-for-byte unchanged. */
static void pass_deshout(const char *in, char *out) {
    int len = (int)strlen(in);
    int n_caps = 0, n_alpha = 0;
    for (int i = 0; i < len;) {
        while (i < len && deshout_is_space((unsigned char)in[i])) i++;
        if (i >= len) break;
        int start = i;
        while (i < len && !deshout_is_space((unsigned char)in[i])) i++;
        int is_caps, has_alpha;
        deshout_word_props(in, start, i, &is_caps, &has_alpha);
        if (is_caps) n_caps++;
        if (has_alpha) n_alpha++;
    }
    if (!(n_caps >= 2 && 2 * n_caps >= n_alpha)) { memcpy(out, in, (size_t)len + 1); return; }
    int o = 0, first = 1;
    for (int i = 0; i < len;) {
        while (i < len && deshout_is_space((unsigned char)in[i])) i++;
        if (i >= len) break;
        int start = i;
        while (i < len && !deshout_is_space((unsigned char)in[i])) i++;
        int end = i;
        int is_caps, has_alpha;
        deshout_word_props(in, start, end, &is_caps, &has_alpha);
        if (!first) out[o++] = ' ';
        first = 0;
        if (is_caps) {
            for (int j = start; j < end;) {
                long cp = cp_at(in, j);
                j += utf8_len((unsigned char)in[j]);
                o = put_lower_cp(out, o, cp);
            }
        } else {
            for (int j = start; j < end; j++) out[o++] = in[j];
        }
    }
    out[o] = 0;
}

/* Python word.strip().lower() over the same Latin domain: drop leading/trailing ASCII
 * whitespace, then lowercase each codepoint (İ -> "i" + U+0307, as pass_lower_collapse
 * does). Unlike pass_lower_collapse this does NOT collapse interior whitespace runs —
 * str.strip() does not either. Used by cy_phonemize.c's cyp_letter_tokens. */
void cyp__lower_strip(const char *in, char *out, int max) {
    int s = 0, e = (int)strlen(in), o = 0;
    while (s < e && deshout_is_space((unsigned char)in[s])) s++;
    while (e > s && deshout_is_space((unsigned char)in[e - 1])) e--;
    for (int j = s; j < e && o + 8 < max;) {
        long cp = cp_at(in, j);
        j += utf8_len((unsigned char)in[j]);
        o = put_lower_cp(out, o, cp);
    }
    out[o] = 0;
}

/* -------- typographic apostrophes (mirrors welsh_normalize._TYPOGRAPHIC) -------- */
/* U+2019 (E2 80 99) and U+02BC (CA BC) -> ASCII '. The Bangor dictionaries key Welsh
 * clitics on the straight apostrophe only, so a curly one misses the lexicon and falls
 * through to LTS. Runs first, so no later pass ever sees the non-ASCII form. */
static void pass_typographic(const char *in, char *out) {
    int o = 0;
    for (int i = 0; in[i];) {
        unsigned char c = (unsigned char)in[i];
        if (c == 0xE2 && (unsigned char)in[i + 1] == 0x80 && (unsigned char)in[i + 2] == 0x99) {
            out[o++] = '\'';
            i += 3;
        } else if (c == 0xCA && (unsigned char)in[i + 1] == 0xBC) {
            out[o++] = '\'';
            i += 2;
        } else {
            out[o++] = in[i++];
        }
    }
    out[o] = 0;
}

void cyp_normalize(const char *in, char *out, int max) {
    (void)max;
    static char a[65536], b[65536];
    snprintf(a, sizeof(a), "%s", in);
    pass_typographic(a, b); memcpy(a, b, strlen(b) + 1);
    /* Emoji first: their names are ordinary Welsh words and must go through every pass
     * below exactly as typed text would. */
    pass_emoji(a, b); memcpy(a, b, strlen(b) + 1);
    for (const Abbrev *ab = ABBREV; ab->pat; ab++) { pass_abbrev(a, b, ab); memcpy(a, b, strlen(b) + 1); }
    pass_deshout(a, b); memcpy(a, b, strlen(b) + 1);
    /* Emails/URLs first: their dots and @ must reach no number or symbol pass, and "@" is
     * the SCHWA in the phone inventory. Then Roman numerals BEFORE pass_acronym, which is
     * [A-Z0-9]{2,} and would claim "IV" as a code and spell it "i·v". */
    pass_email_url(a, b); memcpy(a, b, strlen(b) + 1);
    pass_roman(a, b); memcpy(a, b, strlen(b) + 1);
    pass_acronym(a, b); memcpy(a, b, strlen(b) + 1);
    pass_date_num(a, b); memcpy(a, b, strlen(b) + 1);
    pass_date_month(a, b); memcpy(a, b, strlen(b) + 1);
    pass_ordinal(a, b); memcpy(a, b, strlen(b) + 1);
    pass_fraction(a, b, (int)sizeof(b)); memcpy(a, b, strlen(b) + 1);
    /* CURRENCY BEFORE UNIT, and the order is load-bearing (Python does the same, and
     * for the same reason). With the unit pass first it ate the digits out of a
     * currency amount: "£5m" -> "£pum metr" (five metres, £ dangling), "£2.5m" ->
     * "dwy bunt.pum metr". Currency has to claim its own amount, decimal and all,
     * before anything else reads the digits; it yields back for a real unit. */
    pass_currency(a, b); memcpy(a, b, strlen(b) + 1);
    pass_unit(a, b, (int)sizeof(b)); memcpy(a, b, strlen(b) + 1);
    /* Before pass_integer, which would otherwise flatten "10 blynedd" to "deg blynedd"
     * and lose both the nasal mutation and the "deng" form. */
    pass_blynedd(a, b, (int)sizeof(b)); memcpy(a, b, strlen(b) + 1);
    pass_time(a, b, (int)sizeof(b)); memcpy(a, b, strlen(b) + 1);
    pass_pence(a, b); memcpy(a, b, strlen(b) + 1);
    /* The digit/letter splitter -- placement is load-bearing on both edges; the full
     * reasoning lives at the function. Python mirror: _DIGIT_LETTER_BOUNDARY, at the
     * same point in normalize(). */
    pass_digit_letter_split(a, b, (int)sizeof(b)); memcpy(a, b, strlen(b) + 1);
    /* Operators and the degree sign BEFORE every number pass, so their operands are still
     * DIGITS when the lookarounds run. */
    pass_math_deg(a, b); memcpy(a, b, strlen(b) + 1);
    pass_percent(a, b); memcpy(a, b, strlen(b) + 1);
    pass_decimal(a, b); memcpy(a, b, strlen(b) + 1);
    /* digit SEQUENCES before the cardinal pass, and after time/date/currency so a
     * "07:00" or "01/01/1980" is claimed by the pass that understands it. */
    pass_digit_seq(a, b, (int)sizeof(b)); memcpy(a, b, strlen(b) + 1);
    pass_integer(a, b); memcpy(a, b, strlen(b) + 1);
    pass_amp(a, b); memcpy(a, b, strlen(b) + 1);
    pass_symbols(a, b, (int)sizeof(b)); memcpy(a, b, strlen(b) + 1);
    pass_lower_collapse(a, out);
}
