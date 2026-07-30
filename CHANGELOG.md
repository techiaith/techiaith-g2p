# Changelog

All notable changes to `techiaith-g2p` are documented in this file.

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
