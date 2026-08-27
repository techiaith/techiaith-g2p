# techiaith-g2p

The permissive Bangor Welsh grapheme-to-phoneme (G2P) engine: turns Welsh (and
code-switched English) text into the phoneme-id sequence consumed by Bangor
University's retrained Piper/VITS voices. Dictionary-based, permissively licensed
data only, and dependency-free -- it imports nothing beyond the Python
standard library, so it drops into an inference server, a screen-reader
add-on, or a CLI without pulling in a model runtime.

## Install

```bash
pip install techiaith-g2p
```

## Use

```python
from techiaith.g2p import BangorG2P

g2p = BangorG2P(english_mode="native")
ids = g2p.text_to_ids("Bore da. Sut wyt ti'n teimlo heddiw?")
print(ids)
```

`english_mode` and the package's `data_version()` must match the target
voice's `.onnx.json`. For the full text-to-audio example, see the model card:
https://huggingface.co/techiaith/cy_en_GB-bu_tts

**Do not feed this voice to stock `piper`.** Its `phoneme_type: "text"` path
treats phonemes as individual codepoints, one at a time -- it does not
understand the multi-codepoint phoneme ids this G2P produces, and the output
will be mispronounced. Use the ids from `text_to_ids` directly against the
model's input layer, as the model card describes.

## Links

- Voice model: https://huggingface.co/techiaith/cy_en_GB-bu_tts
- Pronunciation dictionary: https://github.com/techiaith/geiriadur-ynganu-bangor
- Source: https://github.com/techiaith/techiaith-g2p
- License: CC0-1.0 — public domain dedication (see `LICENSE`; the bundled
  pronunciation data keeps its own BSD-2-Clause terms, see `NOTICE`)
