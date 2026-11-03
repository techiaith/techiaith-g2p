# Changelog

All notable changes to `techiaith-g2p` are documented in this file.

## [1.5.0] — 2026-11-03

Code only: `data_version` stays `718542836d1dcbdd` (no data file and no emission policy changes).
Golden corpora at the end of this section: `normalize_golden.tsv` / `normalize_golden_en.tsv`
2,152 / 2,324 rows, `segments_golden.tsv` 192, `word_marks_golden.tsv` 245.

### Added
- **Word highlighting: where each segment and each spoken word came from in the source text.**
  The segments say what to render, but not where it came from, and the WORD_SEP-delimited
  phone-words do not line up one-to-one with source words ("£9.50" is five spoken words, a bullet
  none). Three calls, Python and C, held together by `word_marks_golden.tsv` (245 rows, AUTO and
  forced `cy`/`en`, `test_word_marks.c` in `make check`), the C-vs-Python cross-check in
  `tests/test_word_marks.py`, and a word-mark pass in both differential fuzzers:
  - `BangorG2P.segment_spans(text, lang=None)` / C `cyp_segment_spans`: each segment's source
    span, parallel to `segments()` — the sentence or line with the whitespace around it trimmed,
    before a heading's full stop is added. Consumers raise a sentence event over it.
  - `BangorG2P.word_marks(text, lang=None)` → `[WordMark(seg, word, start, end)]` / C
    `cyp_word_marks` → `CypWordMark {seg, word, src_start, src_end}`: one mark per source word
    that starts a new spoken word, by **prefix counting** per segment — the phone-words of the
    segment's text up to the end of each source word, in the segment's `phone_lang`, clamped so
    marks rise strictly and stay below the segment's count. Phonemising the prefix rather than the
    word keeps every context effect (numbers, acronym runs, brand splits, heteronyms). From a
    segment's 32nd word the prefix is a window of the 16 to 31 words before it (`_WM_WINDOW`), so
    the cost is linear: whole prefixes cost O(words × length), and prose whose sentences start in
    lower case is one segment however long (4 KB of it took 465 ms in C at -O2 on an M-series Mac;
    with the window 25 ms, 0.02–0.035 ms per source word). The window gave the whole-prefix marks
    on every long text measured. Measured consistent (the count at a segment's last word equals
    its own) on 3,001 of 3,002 Welsh segments (brawddegau-tagiedig) and 2,180 of 2,184 English
    ones (MASC written), with and without the window; the clamp keeps the rest in order, at worst
    leaving a word unmarked. Compute marks per utterance, off the path to the first audio.
  - `BangorG2P.word_starts(ids)` / C `cyp_word_starts`: the id index where each phone-word of one
    segment's ids begins, so a model's per-id durations give each word's first frame and no
    platform re-derives the WORD_SEP layout. A WORD_SEP directly before EOS starts nothing, so a
    piece cut just after one (a segment over the model's id cap: `[…, PAD, 3, EOS]`) counts only its
    own words and the ordinals carry across the pieces; after a hard split inside one over-long
    phone-word, the next piece's first phone-word continues the last.
  Offsets are code points in Python and UTF-8 bytes in C. `Segment` is unchanged. The C calls use
  the library's static buffers like every other: callers keep their existing lock around them.
  Size `max_segs` at 2,049 (2,048 boundaries plus the tail) for `cyp_segments` and
  `cyp_segment_spans` alike: with fewer, `cyp_segments` truncates silently while the span and mark
  calls fail, so the tail would be spoken with no events.
  The ctypes binding (`bindings/python/cy_phonemize.py`) gains `segment_spans`, `word_marks` and
  `word_starts`.

### Fixed
- **C on Windows: every number of 2³¹ and up was read wrong** (present in 1.4.0; the Windows app
  has shipped it). The C normaliser built numbers in a `long`, which is 64 bits on macOS, Linux,
  Android and iOS (LP64) but 32 bits on Windows (LLP64), so there they wrapped: "£3bn" read "minws
  un biliwn dau gant naw deg pedwar miliwn … o bunnoedd" ("minus one billion two hundred and
  ninety four million … pounds") where the API says "tri biliwn o bunnoedd", and 2³¹ itself
  wrapped to −2³¹, whose negation overflows. A native Windows run of `test_norm` failed 10 of
  2,104 Welsh and 11 of 2,276 English rows. Every number is now an `int64_t`, and
  `cyp_num_to_welsh` takes one (the same register on LP64 hosts, where no output changes:
  byte-identical normalise, AUTO normalise and ids on 14,900 big-number probe inputs). The longs
  left hold code points and a headword count. Built for Windows x64, x86 and arm64 with the shim
  flags, with no warnings (the old code drew `-Wtype-limits` on exactly these comparisons). 34
  rows join each normalise golden and three sentences the segment and word-mark goldens.
- **C: a pound or pence amount of 2⁶³ crashed the normaliser** (present in 1.4.0, on every host).
  `atoin_commas` reads a plain amount modulo 2⁶⁴, so "£9223372036854775808",
  "9223372036854775808p" and any amount ≡ 2⁶³ (mod 2⁶⁴) reached `cyp_num_to_welsh` as INT64_MIN,
  whose negation is INT64_MIN again: it recursed until the stack overflowed (SIGSEGV on macOS;
  Android, iOS and Linux run the same code). `cyp_num_to_welsh(INT64_MIN)` now reads 2⁶³ digit by
  digit, as Python's `num_to_welsh(-2**63)` does, and `en_cardinal` is guarded the same way; no
  other output changes (14,900 probe inputs: only the 25 that crashed differ).
- **C: a plain pound or pence amount of 2⁶³ and up read a wrapped number** (present in 1.4.0, on
  every host; Welsh only, English reads the digit string). `atoin_commas` read "£<digits>" and
  "<digits>p" modulo 2⁶⁴, so "£10000000000000000000" said "minws wyth pedwar pedwar chwech … punt"
  and "£18446744073709551617" "un bunt", where the API reads the digits one by one ("un dim dim …
  o bunnoedd"). An amount of more than 18 significant digits now takes that reading, with the
  plural, the singular before pence and the soft mutation after saith/wyth as Python builds them;
  shorter amounts are unchanged. On the 14,900 big-number probe inputs C now equals Python in
  every column (normalise `cy`/`en`, AUTO, ids, `cyp_num_to_welsh`); 1,152 Welsh rows differed. 14
  rows join the normalise goldens.
- **C: emails and web addresses read as the API reads them.** `pass_email_url` was an
  approximation of `_EMAIL_OR_URL` that ran first in the C normaliser, where Python runs it after
  the colon clock: on a targeted corpus of 20,026 address-shaped inputs, C and Python disagreed on
  about half. Device and API said "Ewch i www.bbc.co.uk/cymrufyw" differently — C stopped the
  address at the "/" and read "uk" as "wc", while the API keeps the path in the match ("uk/cymrufyw"
  is not a label it maps) and says "U K". C also took "a@b.c", "www.x" and
  "1.2.JavaMail.evans@thyme" for addresses, which Python does not (the host must end in a dot and
  two letters). C now mirrors the pattern (host as `re` backtracks it, the `/\S*` path, `\b`) and
  its place in the pipeline — `pass_time` is split into its colon and colonless halves with the
  address pass between them, as in Python. 20,026/20,026 then agree (normalise `cy` and `en`, and
  ids), and 18 rows join `normalize_golden.tsv` / `normalize_golden_en.tsv`, with the URL
  sentence in `segments_golden.tsv` and `word_marks_golden.tsv`. This moves C
  to the API's behaviour, quirks included: the owner's ".uk" → "wc" applies only when nothing
  follows the host ("www.bbc.co.uk/" says "uk/"), and a clock time inside a path is read after the
  address ("www.x.com/7.30pm" → "… dot com saith dot tri deg pm").
- **C: a title after a curly quote, a guillemet, a dash or a no-break space ended the sentence.**
  `nl_title_before` treated any non-ASCII byte before "Mr"/"Mrs"/"Ms"/"Dr" as a letter, so in
  'Dywedodd Jeff Flake, “Mr. Llywydd, …' C split after "Mr." where Python (the API) does not: two
  segments, a 250 ms gap and a sentence-final fall in the middle of a name. It now decodes the
  code point and tests it as Python does (`str.isalnum()`). The six such rows join
  `segments_golden.tsv` and so `word_marks_golden.tsv`. A non-Latin letter
  directly before the title stays inside the known Latin-only letter-class gap
  (docs/FOLLOWUPS.md §G).
  `str.isalnum()` is also true for numeric forms (`²`, `½`, `①`, `Ⅳ`), which the first version of
  this fix read as non-alphanumeric — a regression against 1.4.0, which agreed with Python on them
  by accident. The splitter now asks Python's questions with the numeric No/Nl code points
  included (`cyp__cp_numeric`, Unicode 13, checked over the whole code-point space): `isalnum()`
  before a title and for the single-letter rule, `isdigit()` for what may follow a full stop
  ("Diwedd. ² …" splits, "… ½ …" does not). The last two were 1.4.0 divergences too. Five rows
  join `segments_golden.tsv`; `²Mr` itself still differs in ids, in the normaliser
  (docs/FOLLOWUPS.md §G).
- **C: two out-of-bounds writes in the sentence and clause splitters** (memory safety; no output
  change below the caps). `nl_sentences` stops after 2,048 boundaries and `nl_clauses` after 64,
  then — as Python's `_split_sentences` / `_split_clauses` do — still closes the rest of the text
  as one more span, but every caller had sized its array for the cap alone, so that last span
  was written one element past the end. AddressSanitizer found a global-buffer-overflow on 2,100
  short lines (4.2 KB) and a stack-buffer-overflow on a bilingual sentence with 64 or more
  comma clauses (about 270 bytes). The arrays now hold the extra span, so C also agrees with
  Python at the caps (`tests/test_segments.py::test_c_span_caps_match_python`).
- **C: an ordinal suffix after a digit run past 2³¹ read as a small ordinal** (present in 1.4.0).
  `atoin` overflowed (undefined behaviour, flagged by UBSan on the committed goldens) and wrapped,
  and `pass_ordinal` tests the whole run against 1..31, so "4294967297af" read "cyntaf" where the
  API reads the number. It now saturates. Four rows join the normalise goldens.
- **C: a date found inside a slash run that has none** (present in 1.4.0). When `_DATE_NUM`
  matches a d/m/y whose day or month is out of range, Python leaves it as it is and `re.sub`
  resumes after it; C stepped one byte and found a date inside, so "80/12/10/2026" read "wyth deg
  y deuddegfed o hydref …" where the API reads the numbers. C now resumes after the match too: 0
  of 19,604 date-shaped inputs differ (723 did). Five rows join the normalise goldens.
- **C: an all-capital word of 128 letters or more was spelled out** (present in 1.4.0). The
  acronym gate reads a capitalised token of four or more letters with a vowel as a word, at any
  length in Python; C skipped the gate from 128 letters (the size of its lower-case buffer) and
  spelled the token, so "A" × 128 gave 769 ids where the API gives 515. C now applies that rule at
  any length (no vocabulary entry is that long). From 512 letters the LTS's documented word cap
  still differs. Five rows join `normalize_golden.tsv` / `normalize_golden_en.tsv`.
- **C: a run of emoji overflowed the normaliser's 64 KB arena** (memory safety; present in 1.4.0;
  no output change below the caps). `pass_emoji` copied each name unbounded, and it is the
  steepest expander in the file: "↪" is one UTF-16 unit and a 38-byte name, so 1,725 of them in one
  sentence (5,175 bytes) overflowed (AddressSanitizer), inside Android's 4,000-character request
  limit; 4,000 killed the process. It now stops when the arena is full, as the bounded passes do
  (text that long is far past the 8,192-phone cap, so no speech changes), and two lookaheads
  (`pp_bullet`, `emoji_skip_len`) no longer read past the end of a full arena. Re-measured in both
  languages, no construct overflows below 6,370 bytes (a digit run through `pass_integer`, as
  before) or 5,244 UTF-16 units (🆎, whose name later passes expand again). The passes still
  unbounded are listed in docs/FOLLOWUPS.md ("Arena hardening"); the regression inputs are in
  `test_c_span_caps_match_python`.

## [1.4.0] — 2026-09-08 (one release for the whole text-structure programme)

`data_version` **moves**: `e015a51f4373ef2b` → `718542836d1dcbdd`. The per-word language prior
`data/lang/lang_prior.tsv` joins the hash and the emission policy goes to v5 (`route=prior+excl`),
because the prior decides which lexicon a shared word reads from. Every consumer — the API's
`techiaith-g2p` pin, the HF model config's `phonemizer.data_version`, and each app distro's
bundled config — must move together; they hard-fail on mismatch by design. The C sources AND the
new data file must be vendored together.

### Added
- **Text structure: segments, boundary kinds and the pauses the model can realise.** Measured on
  the release model, only `, ; :` are pauses; a mid-utterance full stop is 80 ms of silence
  against 124 for a plain space, brackets, dashes, ellipses and quotes nothing, and a newline was
  collapsed before anything saw it — so headings ran into the next line and multi-sentence text
  "smashed together" on device and API alike. `BangorG2P.segments(text)` (C `cyp_segments`) now
  returns the utterance as rendering units — sentence, heading, list line — each with the boundary
  that follows it (`sentence` at `. ! ? …` before whitespace when an upper-case letter, digit,
  quote or the end follows; `line` at a newline; `paragraph` at a blank line) and its own number
  and phone language, carried forward into a segment with no evidence. A line without terminal
  punctuation takes a full stop, so a heading gets the sentence-final fall. Consumers render one
  model pass per segment and insert `BOUNDARY_GAP_MS` / `cyp_boundary_gap_ms(kind)` of silence
  (250 / 350 / 600 ms, tuned by ear) between passes, the same constants everywhere. `text_to_ids`
  is DEFINED as the concatenation of the segments' phones, so a whole-text caller and a
  per-segment caller agree by construction; single-sentence text is byte-identical to before.
- **Structure punctuation becomes the pause the model honours** (normaliser, both languages,
  mirrored in C): brackets, spaced dashes, em/en dashes and a bullet between words → a comma pause;
  an ellipsis (`…` or `...`) → a full stop at the end, a comma inside; `?!?` → `?`; a list marker
  (`- * • ‣ ◦ ▪`) at the start of a line is dropped — the owner heard the bullet read as "bwled"
  (CLDR) and the ellipsis voiced. Two pauses in a row collapse to the second; nothing pauses before
  the first word or after the last. The phone-number pass keeps its brackets ("(01248) 382000").
- `segments_golden.tsv` (168 rows) holds `cyp_segments` to Python; the fuzz corpus gained headings,
  lists, brackets, dashes, ellipses and quotes.

### Changed
- **A word's routing weight is its corpus weight PLUS lexicon exclusivity** (was: corpus weight,
  or exclusivity only for a word neither corpus contains). The owner's phone read a Messages banner
  "2 unread messages" as *dau unread messages*: "unread" carried +7 from a single Welsh tweet and
  "messages" only −12, so the banner was Welsh. The English lexicon knows "unread"; adding ±16 for a
  word only one lexicon holds outvotes that noise. Held-out (`scripts/gen_lang_prior.py` split):
  English sentences 98.6% → 99.2%, Welsh 99.7% unchanged. Side effect, accepted: lone English UI
  words the corpus barely saw ("Cancel", "Skip", "keyboard") are now decided English instead of
  falling to the Welsh default, and "a BBC" alone reads the "a" as English.
- **A soft wrap must continue with a word.** A line of ≥40 characters without terminal punctuation
  followed by one newline was always joined to the next line; a message followed by its timestamp
  ("…this afternoon or not⏎15:44") therefore ran straight into the time with no pause, unlike the
  system voice. The join now also requires the next line to start with a letter, so a time, a
  number or an emoji on the next line is a line boundary (350 ms) and takes the message's language.
- **Abbreviated dates read as dates.** TalkBack sends a widget's date literally, "Tue 8 Sept", which
  read as *tue eight sept* (VoiceOver expands its own labels, so the iPhone said "Tuesday the 8th of
  September" and the Pixel did not). A title-case weekday abbreviation before the date (Mon, Tue,
  Tues, Wed, Thu, Thur, Thurs, Fri, Sat, Sun; Llun, Maw, Mer, Iau, Gwe, Sad, Sul) is read as the
  full day name, a title-case month abbreviation (Jan…Dec, Sep and Sept; Ion, Chwe, Chwef, Maw, Ebr,
  Meh, Gor, Gorff, Hyd, Tach, Rhag) as the month, and English also comes month-first ("Sep 8",
  "Tuesday, September 8, 2026" → "tuesday, the eighth of september twenty twenty six"). The day
  may carry an ordinal suffix in either order ("8th Sept", "Jan 1st", "1af Ionawr"). Abbreviations
  and the month-first month are case-sensitive because "mar", "sat", "sun", "dec", "hyd", "iau" and
  "llun" are words: "5 hyd 7" and "may 5 people" are untouched. Full month names stay
  case-insensitive. A year may now follow after a comma ("8 Sept, 2026").
- **The ratio colon (U+2236) and the fullwidth colon (U+FF1A) fold to ":"** in the typographic pass,
  so a clock time written with either is still a clock time rather than two bare numbers.
- **Sentence language is decided by a corpus-derived word prior, not an exclusive-word count.**
  The owner heard "Learn more" as *learn mor-eh* on both phones and the API: "more" is a loan in
  the Welsh dictionary, so it was a *shared* word, and the old rule wanted two English-only words
  making up a third of the utterance before it would route English. Measured on 26 everyday English
  labels, 18 routed Welsh. `data/lang/lang_prior.tsv` (`scripts/gen_lang_prior.py`) now scores
  every word the router can see by 16 × the log-odds of its frequency in Welsh text
  (corpws-brawddegau-tagiedig, CC0, sentence records) versus English text (MASC 3.0.0, CC BY 3.0
  US, as NLTK's `masc_tagged`), tokenised exactly as the router tokenises, damped for rare words,
  quantised to an int8 (33,777 words, 359 KB). A sentence's language is the sign of the sum, with
  half a nat of evidence required either way; a word in neither corpus falls back to dictionary
  exclusivity; letter names weigh nothing except Welsh "o" and "y". Held-out sentences: Welsh 99.6%
  / English 99.1% (old rule 99.6% / 94.6%); every one of the 18 labels now routes English; "Un
  taxi", "Y BBC", "c, a, th." stay Welsh. Numbers and phones share the one score, so the 1.3.x
  function-word lists are gone. The rows of the frozen pre-lang oracle that move ("the", "action",
  "AB", "ab·cd") each carry their dictionary readings as literals. C mirrors the table (binary
  search) and the scoring in `phonemize_flat_ex` and `number_score`.

- **`techiaith`** gets a pinned Welsh pronunciation (`ˈt e x | j ai th`) — see below under 1.3.1's
  items, folded into this release.

### Fixed
- **Capitalised words no longer spell out unless they are initialisms.** The owner read a GitLab
  project page and heard "r·e·a·d·m·e" and "c·h·a·n·g·e·l·o·g"; typical labels showed the same:
  6 of 20 common Welsh labels (CAU, AGOR, IAWN, CADW, WEDI), 7 of 10 app names in caps, and
  pronounceable words CMUdict lacks (LOGIN, WIFI, OFCOM). Cause: the vocabulary gate read an
  all-caps token as a word only if the English tables knew it, or the Welsh table knew it AND it
  had five letters (the 1.2.0 fix for DWP/NHS), and it never consulted the native English
  lexicon. The gate now has four rules, in `welsh_normalize._acronym_reads_as_word` and its C
  mirror: (1) an explicit always-spell list of 36 initialisms — the Welsh-headword collisions
  (DWP, NHS, RAC, PHD…) and the vowel-bearing ones still said letter by letter (GCSE, HDMI, RSPCA,
  WJEC, FTSE, JPEG…), measured over ~250 UK/tech initialisms as the complete exception set;
  (2) English/foreign tables **including `cmudict_native.dict`** read as their entry; (3) a Welsh
  headword of three or more letters reads as the word — two-letter caps tokens (OS, AR, CI, EU)
  are initialisms; (4) an unknown token with four or more letters and a vowel reads through
  letter-to-sound, without a vowel (HMRC, GDPR, HTML, GPS, USB) it spells. On the probe: Welsh
  labels spelled 6 → 0, app names 7 → 0, initialisms unchanged.
- **readme, changelog, devops, gitlab, kubernetes** get explicit English pronunciations (the
  first four as two words, like the brand entries), since no dictionary has them and
  letter-to-sound gave "reed-meh" and "chan-ge-lodge".
- **The number language is decided per sentence, not per utterance.** "1 o 1. 1 of 1" read
  every digit in English because one "of" anywhere decided the whole text. Sentences end at a
  run of `. ! ?` before whitespace, or a newline — not after a single-letter word ("e.e.",
  "y.b.", "a.m.") or a title (Dr., Mr.). A sentence with evidence for BOTH languages is split
  again at `, ; :` before whitespace or a dash between spaces ("Tudalen 1 o 3, Page 1 of 3"
  — bilingual-signage style), and a span with no evidence takes the language of the span
  before it, the first defaulting to Welsh. When every span agrees the text is normalised in
  one pass exactly as before, so single-language utterances are byte-identical. Welsh "o"
  and "y" now count as Welsh evidence (their only English homograph is a letter name) unless
  an apostrophe follows ("o'clock"). `BangorG2P._number_spans` and C `number_spans`.
- **Sentence routing counts words, not punctuation tokens.** Python's `_sentence_lang` counted a
  dash between spaces as a word of the utterance (C never made a token for it), so
  "Croeso - Welcome, 1 o 3 – 1 of 3" routed Welsh in Python and English in C, and C in turn
  counted an en dash (which survives its ASCII punctuation peel as a core) while dropping a
  hyphen — the only Python-vs-C divergence found in this round, and a pre-existing one. Both
  sides now count only cores with a letter or digit, the rule's wording. Texts without
  standalone punctuation are unaffected.
- **A comma after a number is kept.** `_INTEGER` and `_CURRENCY` accepted `[0-9,]*`, so
  "1, 1" was "un un" and "£5, diolch" lost its pause; a comma is now part of the number only
  when a digit follows (`(?:,?[0-9])*`, and the two C loops), which also stops "1,,2" reading
  as twelve.

## [1.3.0] — 2026-09-07

`data_version` does **not** move (`e015a51f4373ef2b`): the phone inventory, emission policy,
dictionaries and tagger data are unchanged, and text normalisation has never been part of the
hash. The API can take this pin with no HF config change; the apps re-vendor the C sources only.

### Added
- **Digits inside an English utterance read as English words.** A screen reader hands the
  engine one utterance at a time ("Home screen 1 of 3", "Battery at 45%", "Alarm set for
  6:45 am"), and every one of them came out with Welsh numerals in the middle of English —
  "home screen un o tri". The normaliser now takes the language the numbers are read in
  (`normalize(text, lang="cy"|"en")`; C: `cyp_normalize_lang`). The triggers — what counts as
  a time, a date, a price, a percentage, a unit, a fraction, a Roman numeral — are shared;
  only the words written back differ, so the two languages cannot drift on *what* they
  verbalise. British English conventions, agreed with the owner 2026-09-07
  (`techiaith/g2p/english_numbers.py` is the contract; `docs/number-language.md` the summary):
  "one hundred and twenty three", "twenty twenty six" for a bare 1100–2099, "the twelfth of
  march", "three thirty p·m" (letters through the acronym join), "five pounds ninety nine",
  "fifty pence", "fifteen percent", phone numbers digit by digit with "zero", "henry the
  eighth" but "chapter four". Anything the Welsh path did is byte-identical to 1.2.0: the
  Welsh golden corpus (1,986 rows) is unchanged.
- **The number language is detected per utterance** (`BangorG2P._number_lang`; C:
  `number_lang`) from the alphabetic words of the raw text, by the same dictionary-exclusivity
  evidence as the phone routing but with a lower bar — one English-only word and no Welsh-only
  word is enough, because a Welsh "tri" inside an English interface is unintelligible where an
  English "three" inside Welsh is not. No evidence (a bare "3") means Welsh, the voice's own
  language; an explicit `lang` to `text_to_ids` / `cyp_text_to_ids_lang` wins outright.
  The phone routing (`_sentence_lang`) is untouched, so how words *sound* has not changed.
- **English function words count as English evidence** even though `bangordict.dict` lists
  "of", "the", "for", "it", "not" as loans with Welsh phonology (which made "Tab 1 of 4" look
  language-neutral). The list is the high-frequency closed class minus every genuine Welsh
  homograph ("at", "is", "to", "was", "her", "be", "can", "had", "call"); the tagger's Welsh
  training features settled the borderline cases. Same list in Python and C, asserted equal.
- `normalize_golden_en.tsv` (2,137 rows: the Welsh corpus's inputs plus the English
  constructs) holds the C mirror to the Python verbaliser; the parity fuzz corpus gained a
  section of English screen-reader strings and Welsh sentences with the same constructs.

### Changed
- **Phone routing is decided per sentence, not per utterance.** "1 of 1. 1 o 1" said the right
  words after the number-language fix but spoke "un o un" with English phones, and "Techiaith TTS"
  came out *tetch-ee-ayth* whenever an English sentence preceded it in the same utterance — one
  `_sentence_lang` decision covered everything. Each sentence (the same spans as the number
  language) is now scored on its own words by today's rule: meets the English bar → English; has
  Welsh-only evidence → Welsh; no exclusive word either way ("un o un" — both are in both
  dictionaries) → the number language's evidence for that sentence ("o", "y", "mae" / "of",
  "the"…); none of that → the utterance's decision, so "I agree." inside an English text does
  not flip. Single-sentence utterances keep the utterance rule unchanged. When every sentence agrees the text is phonemized in one pass with
  that language, byte-identical to before; only a mixed utterance is phonemized sentence by
  sentence. C: `phonemize_sentences`, with a count-only mode of the phonemizer so a sentence is
  scored by the same tokeniser that emits it. Clause-level (comma) routing is deliberately not
  done: a clause boundary is a pause, not a language boundary, and the number language already
  handles digits at that level.
- **`techiaith`** gets a pinned Welsh pronunciation (`ˈt e x | j ai th`), the organisation's own
  name being in no dictionary.
- `english_numbers.cardinal` reads more than twelve significant digits digit by digit, the
  floor the Welsh path already had, so no digit run can raise.

## [1.2.0] — 2026-09-07

`data_version` **moves**: `b1edc63e35bb7a6f` → `e015a51f4373ef2b`. Every consumer — the API's
`techiaith-g2p` pin, the HF model config's `phonemizer.data_version`, and each app distro's
bundled config — must move together; `models/piper/bangor.py` and the apps hard-fail on
mismatch by design.

### Added
- **Heteronyms are resolved by part of speech.** `read`, `use`, `close`, `live`, `record`,
  `object`, `present`, `separate`, `wind`, `estimate`, `desert`, `refuse` each carried one
  fixed reading; scored against MASC gold POS over 933 real instances, 9 of 15 shipped the
  minority reading (`live` was right 3.6% of the time). An averaged-perceptron tagger
  (integer weights, byte-identical Python/C) now picks the reading: 38.7% → 88.1% correct,
  with the majority reading as fallback when no model is installed. English tagger data is
  MASC 3.0.0 (CC BY 3.0 US, attributed in NOTICE); Welsh is `brawddegau-tagiedig` (CC0).
  Models ship as `data/pos/pos_{cy,en}.bin` (5.4 MB); the tagger runs only when an utterance
  contains a heteronym, so every other utterance is provably unchanged.
- **Brand and product names read as English** where `bangordict.dict` had Welsh-phonology
  readings: YouTube, Google, Twitter, Adobe, Photoshop, PowerPoint, eBay, iPhone, iPad,
  Android, plus OneDrive, Chromebook, Firestick, Fitbit, TikTok, Deliveroo as two-word forms.
  Phones are the existing `cmudict_native` entries verbatim.
- **Hyphenated compounds unknown to the dictionaries split into their parts** ("double-tap",
  "read-only"), instead of falling to letter-to-sound as one nonword.
- **Emoji names come from Unicode CLDR `cy` annotations**, not espeak-ng (GPL). 1,427 → 2,375
  entries, zero readings lost; corrections and additions in `scripts/gen_emoji_cy.py`.

### Changed
- **Acronym vocabulary gate no longer captures short English acronyms that collide with
  Welsh words.** 1.1.0's gate read `DWP` as the Welsh adjective *dwp* and `NHS` as a Welsh
  headword. Headwords from the English/foreign tables still read as words at any length
  (`BBC`, `USA`, `OK`, `NATO`); native-Welsh-only headwords read as words only from five
  letters (`ADRODDIAD`, `CROESO`), and spell below that, as 1.0.1 did.
- `cmudict_native.dict` and `pos_{cy,en}.bin` are hashed into `data_version`.
- `diff_fuzz_c_parity.py` samples across whole dictionary files (it read only the
  alphabetical head — 21% of `bangordict.dict`, 0% of `cmudict.dict`) and pins heteronyms.

### Not changed, deliberately
- The English lexicon. A rule-based "Welsh English" re-derivation was measured against
  Bangor's own 119,305 English transcriptions (agreement 82% → 63%) and against the deployed
  API by ear, and withdrawn. The model was trained with these labels; accent is a retrain.

## [1.1.0] — 2026-08-27

Normaliser and tokeniser fixes for the confidently-wrong readings surfaced by the
Orpheus-3B text-in consumer (`docs/FOLLOWUPS.md` §H) plus the open §G classes.
`data_version` is unchanged (`b1edc63e35bb7a6f`): every change re-verbalises into
words, phones and pause ids the deployed model already renders.

### Fixed
- **The clock reads what Welsh authors actually write.** Dotted meridiems on the colon
  form (`7:00p.m.` was read as *money* — "saith sero ceiniog.m."), and the colonless /
  dotted-hour forms BTC itself recommends (`7pm` was the LTS nonword "saithpm",
  `10am hyd 4pm` two nonwords, `7.30pm` a decimal misread). The marker must be glued —
  `am` is a Welsh preposition, so `5 am ddim` / `2 am 1` stay untouched and the spaced
  `7 pm` stays unclaimed by design. Uppercase glued forms (`7PM`, `3:00PM`) reach the
  clock through an acronym stand-aside; uppercase dotted (`7P.M.`) stays a spelled code.
- **Digit runs no longer glue to letters, either direction.** `x05` → "x dim pump" (the
  zero survives), `800x` → "wyth gant x", `£5x` → "pum punt x", `50%x` → "pum deg y cant
  x"; `s4c` now reads like `S4C` ("s pedwar c", not fourpence), and `covid19` / `h2o`
  verbalise cleanly. A letter after a date's year now means it is not a year — closing a
  silent Python↔C divergence.
- **Interior punctuation is spoken, not swallowed.** `ie!na` tokenises exactly as
  "ie! na" (the pause id is emitted), `ty(bach)` as "ty (bach)"; clitics (`i'r`) and
  compounds (`gogledd-ddwyrain`) untouched.
- **Letter-adjacent symbols.** `a+b` → "a plws b", `a=b` → "a yn hafal i b", `a@b` →
  "a at b" (the approved space-bounded words, context widened); `a*b` takes the space
  floor. `C++` / `A+` stay codes.
- **Python↔C parity.** All consuming digit positions are now the ASCII class in Python
  (`£٣`/`٣%`/`٣.٣`/`٣ Ionawr 2020` converge) and the C whitespace loops in
  percent/math/ampersand/date are Unicode-aware (`8 x 9` with NBSP converges) — the
  differential fuzzers' last known findable divergence is gone.

### Changed
- **Acronym letter-spelling is now an OOV fallback (2026-08-25).** An all-caps token
  whose lowercase form the pronunciation dictionaries know reads as that word —
  `ADRODDIAD` → "adroddiad" (a shouted single word is not an acronym), `BBC`/`NATO`/
  `OK` read as the lexicon's own entries ("bi bi si", "nato", "ou kei") — and only a
  token the dictionaries do not know is spelled letter-by-letter (`HMS`, `WJEC`,
  `USB`). Digit-bearing codes (`S4C`, `A55`) always spell. Accepted collisions: `US`,
  `IT`, `AM` and similar read as the words they collide with. The headword set (140k
  entries, ASCII `[a-z]{2,}` first fields of the four dictionary files) is loaded
  lazily in Python (`_acronym_vocab`) and at `cyp_create` in C; a harness calling the
  bare `cyp_normalize` must call `cyp_normalize_load_vocab(core_dir)` first — the
  golden corpus fails loudly if it forgets.

### Hardened
- `pass_time`, `pass_symbols` and the new splitter pass are bounds-checked against the
  shared 64 KB arena (`pass_currency` remains the largest unbounded expander, recorded).

## [1.0.1] — 2026-07-30

### Changed
- Source and test comments cite issue numbers (or "native-speaker review") instead of
  naming the reviewer — the package is public on PyPI and mirrored to GitHub, so shipped
  artifacts no longer name an individual. The pronunciation dictionaries are untouched:
  their entries are data, not attribution, and `data_version` is unchanged.
- `pyproject.toml`'s Homepage points at the public mirror
  (`github.com/techiaith/techiaith-g2p`) instead of a dead link.

## [1.0.0] — 2026-07-30

First release. This is a **new distribution**, not a successor to anything — there is no
0.x history to summarize.

`techiaith-g2p` is the Bangor Welsh grapheme-to-phoneme (G2P) engine, extracted from
`piper-lleol`, producing the Piper phoneme-id sequences consumed by Bangor University's
retrained `techiaith/cy_en_GB-bu_tts` voices. Dictionary-based, permissively licensed data
only (CC0-1.0 code, BSD-2-Clause pronunciation data — see `NOTICE`), and dependency-free: it
imports nothing beyond the Python standard library.

Starting at 1.0.0 rather than 0.1.0 is deliberate. The id-map and interleaving this package
emits are a frozen contract — a trained model depends on their exact output, and the
emission policy cannot change without a `data_version` bump. A 0.x version would imply an
instability this format does not have.

**Not this package:** `techiaith-tts` 0.1.6 on PyPI is an unrelated, dormant distribution
(a 2023 Welsh text normaliser, `techiaith.tts.testun`). If you found that name first, this
is the package you want for phonemization; `techiaith-tts` is not maintained and is not a
predecessor of this one.
