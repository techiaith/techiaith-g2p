# Changelog

All notable changes to `techiaith-g2p` are documented in this file.

## [1.4.0] — unreleased (2026-09-07 → 2026-09-08; one release for the whole text-structure programme)

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
