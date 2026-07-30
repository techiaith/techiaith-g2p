# libcy_phonemize — C ABI phonemizer (Workstream P / P7)

On-device port of the permissive Welsh phonemizer, so the **identical** phoneme-id
sequence the model trains on (Python) is produced at inference on every platform (C).
Gated by the golden-parity test.

## Status — increments 1–2 (done)
- **1 — dict lookup + interleaving:** id-map + the 4 Bangor dictionaries, word-split +
  ordered lookup (cy→xx→en→cmudict) + `[BOS]+[PAD,id]*+[PAD,EOS]`. `42/42` golden parity.
- **2 — Welsh LTS (OOV):** full port of `bangor_lts.py` (UTF-8 accents, grapheme
  segmentation, s-devoicing/nasal-assimilation/geminate-collapse, clear/obscure y,
  vowel length, penultimate stress). `cyp_lts` + OOV routing in `cyp_text_to_ids`.
  **`3565/3565` C LTS parity** (byte-identical to Python across a broad dictionary
  sample). So the C phonemizer now handles **any Welsh word** on-device.
- **3 — text normalization:** full port of `welsh_normalize.py` (`cy_normalize.c`):
  cardinals 0–999,999,999, integers/thousands-commas, decimals (pwynt), percent
  (y cant), `&`→a/ac, abbreviations, acronym spell-out. `cyp_num_to_welsh` +
  `cyp_normalize`, wired into `cyp_text_to_ids`. **`1903/1903` C normalize parity**;
  end-to-end C==Python on number/acronym sentences.

- **4 — bilingual English:** native English lexicon (CMUdict, `cyp_create` loads it),
  `english_fold` (native→Welsh), English LTS (`cy_english.c`), word-level language-ID,
  and mode routing. `cyp_create(core_dir, english_mode)` where `english_mode` is
  `"native"` / `"accented"` — **match the model's `config.json` → phonemizer.english_mode**
  (the model's `data_version` does not yet encode the mode; the runtime must read it).
  **`82/82` native + `82/82` accented C bilingual parity**; end-to-end C==Python.

**The C phonemizer is feature-complete** — full permissive Welsh+English on-device,
byte-identical to Python. Same `data_version`; C99/gnu11, no dependencies.
Next: per-platform bindings (JNI / Swift C-interop / Dart FFI / P/Invoke).

## Build & test
```
# THE CANONICAL INTERPRETER, not a bare `python3` -- see below. The script now also
# rewrites canonical.py's ND_BLOCK table, and refuses to run on the wrong Unicode version.
/usr/bin/python3.10 ../../../scripts/emit_c_data.py   # (re)generate the corpora + ND_BLOCK
make check CORE=..                         # build + run the golden-parity test
make libcy_phonemize.a                     # static library
make fuzz PYTHON=/usr/bin/python3.10       # the two differential fuzzers (not in `check`)
```
`CORE` is the `techiaith/g2p` directory (holds `c/tokens.tsv`, the dictionaries, and
`c/data_version.txt`).

### Generate and test under the canonical interpreter

**Generated data and the Python test suite must run on the same Python.** Some of what
this port reproduces is Unicode-version-dependent — `letter_tokens` decides what is a
letter or a digit with `str.isdecimal()` / `str.isalpha()`, and `ND_BLOCK` in
`cy_normalize.c` is the C mirror of exactly that table. "The C port reproduces the Python
reference byte for byte" therefore said nothing until *which* Python was named.

Four interpreters are measured on the current development host (there is no Python
3.12 anywhere on this machine — an earlier version of this table assumed a 3.12 dev
venv that does not exist; do not trust that description):

| interpreter | Python | `unicodedata` | role |
|---|---|---|---|
| `/usr/bin/python3.10` | 3.10.12 | 13.0.0 | **canonical** — has `pytest` |
| `/home/linuxbrew/.linuxbrew/bin/python3.10` | 3.10.20 | 13.0.0 | no `pytest` |
| `/home/linuxbrew/.linuxbrew/bin/python3.14` | 3.14.6 | **16.0.0** | has `pytest` — useful for checking the matrix |
| the dev venv (`piper-cy/.venv/bin/python`) | 3.10.12 | 13.0.0 | has `pytest`, same tables as canonical |

They agreed on every committed corpus (verified byte-for-byte), so the drift was latent,
not live — but it was still an open question which one governs. **It is now decided:
Python 3.10 / Unicode 13.0.0 is canonical**, declared once in
[`techiaith/g2p/canonical.py`](../canonical.py) (`CANONICAL_PYTHON`, `CANONICAL_UNICODE`,
and the `ND_BLOCK` digit table itself — 65 entries under Unicode 13, not the 68 that a
Unicode-15 interpreter would derive). 3.10 was picked because it is what the deployed API
container serves, and because it has the *oldest* character tables of the three — anything
it accepts, a newer interpreter also accepts.

The **digit class is vendored** (Task 2): `decimal_value()` in `canonical.py` and
`ND_BLOCK` in `cy_normalize.c` are generated together from one source
(`scripts/emit_c_data.py`), and `bangor_g2p.py` calls `decimal_value(ch) >= 0` rather than
the host interpreter's `str.isdecimal()` — so a user running Python 3.14 still classifies
digits exactly as Unicode 13 does, not as 3.14 does.

The **letter class is deliberately NOT vendored**: `str.isalpha()` (Python, Unicode-aware
over every script) and `cyp__cp_is_alpha`/`cp_is_word` (C, four Latin ranges only) are left
as they were. This is a live, intentional Python/C divergence outside Latin letters — see
`docs/FOLLOWUPS.md` §G — carried forward rather than closed here, and it is why the
differential fuzzers deliberately exclude non-Latin-letter inputs: they would fail the gate
on a known, accepted divergence rather than guard against a new one.

This is still guarded, not just declared:

- `emit_c_data.py` **refuses to run** unless `unicodedata.unidata_version` equals
  `canonical.py`'s `CANONICAL_UNICODE`, naming both versions and the interpreter to use. It
  writes source (`canonical.py`'s `ND_BLOCK`), so under a bare `python3` it used to swap 65
  Unicode-13 block starts for 76 Unicode-16 ones with every "65 blocks" comment left in
  place — the silent drift this whole section exists to prevent. It also records its own
  interpreter in `generator_env.txt`.
- `cy_normalize.c` declares `ND_TABLE_UNICODE_VERSION` in the comment block above
  `ND_BLOCK`. The test finds it by searching the whole file, so the exact position is not
  load-bearing — but the spelling `ND_TABLE_UNICODE_VERSION = <x.y.z>` is.
- `tests/test_ssml_primitives.py` fails loudly if either the generated corpora or the
  interpreter running the tests disagrees with `canonical.py`, and separately walks all
  0x110000 codepoints against `unicodedata` to confirm the vendored table is exact.

So if you regenerate with one Python and test with another, pytest tells you immediately
and names both versions. Regenerate the corpora *and* `ND_BLOCK` under
`/usr/bin/python3.10` (or whichever interpreter `canonical.py` names, if that is ever
deliberately changed — see its own docstring for what changing it requires).

**`make check` does not exercise any of this.** It builds and runs the C suites against
the checked-in corpus only — it never invokes Python — so it is structurally blind to a
Python-side regression; only `make fuzz` (which needs `PYTHON=/usr/bin/python3.10` and the
built `.so`) diffs live Python against C. See the comment above the `fuzz` target in the
`Makefile`.

## API (`cy_phonemize.h`)
`cyp_create(core_dir)` · `cyp_text_to_ids(p, utf8, out, max)` · `cyp_data_version(p)`
· `cyp_num_symbols(p)` · `cyp_destroy(p)`. Shells must assert
`model.data_version == cyp_data_version()` at load.

## Next C increments (mirror the Python, each golden-gated)
- Welsh LTS (OOV) · text normalization (numbers/dates/…) · native English G2P.
- Per-platform bindings: JNI (Android), Swift/C-interop (Apple), Dart FFI (Flutter),
  P/Invoke (Windows), plain C (Linux/NVDA).

Generated data files (`tokens.tsv`, `golden.tsv`, `ipa_map.tsv`, `data_version.txt`,
`generator_env.txt`, and the parity corpora) are committed so the C build is
self-contained; regenerate them with `/usr/bin/python3.10 scripts/emit_c_data.py` after any
id-map or golden change — the canonical interpreter, which is also the one that runs your
tests (see above). The script now enforces that itself.
