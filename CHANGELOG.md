# Changelog

All notable changes to `techiaith-g2p` are documented in this file.

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
