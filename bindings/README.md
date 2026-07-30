# Bindings — calling `libcy_phonemize` from each platform

The phonemizer is one C library (`techiaith/g2p/c/libcy_phonemize`, feature-complete,
byte-identical to the Python reference). Every app links it and calls the same C ABI
(`cyp_create(core_dir, english_mode)` → `cyp_text_to_ids` → `cyp_destroy`), then feeds
the returned phoneme ids to the ONNX model (via sherpa-onnx or ORT). **Match the
model:** pass `english_mode` = the model's `config.json` → `phonemizer.english_mode`.

## Pattern (per platform)
| Platform | Binding | Notes |
|---|---|---|
| **Python / NVDA** | **ctypes** — `bindings/python/cy_phonemize.py` ✅ done, parity-tested | NVDA add-ons are Python; also the reference binding |
| Android | JNI (thin C shim → Kotlin/Java) | build the `.so` per ABI (arm64-v8a, armeabi-v7a, x86_64) with the NDK |
| Apple (iOS/macOS) | Swift C-interop (module map over `cy_phonemize.h`) → `.xcframework` | |
| Flutter (desktop app) | Dart FFI (`dart:ffi`) over the `.so`/`.dylib`/`.dll` | |
| Windows | P/Invoke (`DllImport`) over `cy_phonemize.dll` | |
| Linux (speech-dispatcher / CLI) | link the `.a`/`.so` directly | |

## Build
```
make -C techiaith/g2p/c libcy_phonemize.so       # shared lib (ctypes/Dart/JNI/P-Invoke)
make -C techiaith/g2p/c libcy_phonemize.a        # static lib (Linux/Apple)
python3 tests/test_binding.py                    # ctypes parity vs BangorG2P (both modes)
```
The library reads its data (`c/tokens.tsv`, the dictionaries, `data/english/…`,
`c/*.tsv`, `c/data_version.txt`) from the `core_dir` passed to `cyp_create` — ship
that directory (or a packaged copy) with the app.

## Contract
Every consumer must assert `model.config.data_version == cyp_data_version()` at load
(hard-fail on mismatch) — silent drift corrupts audio. See `docs/PARITY.md`.
