# Golden-vector schema (Workstream P / P0.4, P8)

Golden files are JSON Lines (`.jsonl`), one test case per line. They are the
immutable **target** that the G2P engine (P1), its C port (P7), and the training
`preprocess.py` path (P4) must all reproduce byte-for-byte (asserted by P8 CI).

## Fields (per line)
| field | type | meaning |
|---|---|---|
| `text` | string | raw input text (as a caller would pass it) |
| `normalized` | string | text after L1 normalization (P2); equals `text` for already-clean seed words |
| `phone_tokens` | string[] | the phoneme/marker tokens, in order, before interleaving (each must be a key in the id-map) |
| `ids` | int[] | the final id sequence **after** interleaving `[BOS] + [PAD,id]* + [PAD,EOS]` — the exact tensor fed to the model |

## Files
- `seed.jsonl` — ~37 hand-verified cases from dictionary-covered words + phrases
  (authored by [`scripts/build_seed_golden.py`](../../scripts/build_seed_golden.py)).
  Locks the id-map, the ASCII-column tokenisation, and the interleaving.
- *(later)* `corpus.jsonl` — the ~500-case P8 corpus: every phone ≥ once, numbers/
  dates/currency/URLs, code-switch, OOV cy/en, stress/length edge cases.

## Rules
- A case is **PASS** iff the engine's `ids` equal the recorded `ids` exactly.
- `phone_tokens` is the human-readable intermediate for debugging a mismatch.
- Regenerating the model (new `data_version`) regenerates goldens **in the same
  commit** — never edit a golden to make a failing engine pass.
