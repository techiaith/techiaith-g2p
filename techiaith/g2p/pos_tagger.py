"""Averaged-perceptron POS tagger over a sorted-blob model.

Reference implementation. `techiaith/g2p/c/cy_pos.c` mirrors it and
`tests/diff_fuzz_c_parity.py` proves the two agree byte for byte, so every detail here
is load-bearing: the feature strings, the integer arithmetic, and the tie-break.

Integer-only by construction. A float score would differ in the last bit between
Python's doubles and C's, on some platform, on some input, and the parity harness would
catch it as a phoneme divergence long after the cause was forgotten. Weights are
pre-averaged and quantised by scripts/gen_pos_data.py; nothing here divides.

The tagger is fed words that welsh_normalize.normalize() has already lowercased, so it
does NO case folding of its own -- which is also why it needs no Unicode case tables in
C, and why the model carries no capitalisation feature (see gen_pos_data.read_corpus).
"""
from __future__ import annotations

import struct
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_MAGIC = b"TPOS"
_FORMAT_VERSION = 1

# A feature longer than this is dropped, on BOTH sides. C builds features into a fixed
# buffer, and silently truncating there while Python kept the full string would be a
# divergence that only a pathological input reveals. Real words are far shorter; the
# cap exists so the failure mode is "both ignore it" rather than "they disagree".
_MAX_FEATURE = 1000


class PosTagger:
    __slots__ = ("tags", "scale", "lang", "_keys", "_weights")

    def __init__(self, path: Path):
        raw = path.read_bytes()
        if raw[:4] != _MAGIC:
            raise ValueError(f"{path}: not a TPOS model (bad magic)")
        off = 4
        version, self.scale = struct.unpack_from("<HH", raw, off); off += 4
        if version != _FORMAT_VERSION:
            raise ValueError(f"{path}: TPOS version {version}, expected {_FORMAT_VERSION}")
        (n,) = struct.unpack_from("<B", raw, off); off += 1
        self.lang = raw[off:off + n].decode("ascii"); off += n
        (ntags,) = struct.unpack_from("<H", raw, off); off += 2
        tags: List[str] = []
        for _ in range(ntags):
            (n,) = struct.unpack_from("<B", raw, off); off += 1
            tags.append(raw[off:off + n].decode("ascii")); off += n
        self.tags = tuple(tags)
        nfeat, blob_len = struct.unpack_from("<II", raw, off); off += 8
        offsets = struct.unpack_from(f"<{nfeat + 1}I", raw, off)
        off += 4 * (nfeat + 1)
        blob = raw[off:off + blob_len]

        # The C side binary-searches the blob in place. Python builds a dict instead --
        # same answers, and the parity that matters is the OUTPUT, not the lookup
        # strategy. Decoding a 2 MB blob once at construction costs less than
        # re-searching it per token.
        self._weights: Dict[bytes, Tuple[Tuple[int, int], ...]] = {}
        for k in range(nfeat):
            p = offsets[k]
            (klen,) = struct.unpack_from("<H", blob, p); p += 2
            key = bytes(blob[p:p + klen]); p += klen
            (nw,) = struct.unpack_from("<B", blob, p); p += 1
            self._weights[key] = tuple(
                struct.unpack_from("<Bh", blob, p + 3 * j) for j in range(nw))
        self._keys = nfeat

    def __len__(self) -> int:
        return self._keys

    @staticmethod
    def features(i: int, words: List[bytes], prev1: bytes, prev2: bytes) -> List[bytes]:
        """Byte-level feature construction -- see gen_pos_data.features, which must
        produce exactly these strings, and cy_pos.c, which must too.

        Everything is bytes, and suffixes/prefixes are BYTE slices. Slicing mid-UTF-8
        is deliberate and harmless: the feature is an opaque key, and both sides slice
        identically, which is the only property that matters."""
        w = words[i]
        pw = words[i - 1] if i > 0 else b"<s>"
        ppw = words[i - 2] if i > 1 else b"<s2>"
        nw = words[i + 1] if i + 1 < len(words) else b"</s>"
        nnw = words[i + 2] if i + 2 < len(words) else b"</s2>"
        return [
            b"b",
            b"w=" + w,
            b"suf1=" + w[-1:], b"suf2=" + w[-2:], b"suf3=" + w[-3:], b"suf4=" + w[-4:],
            b"pre1=" + w[:1], b"pre3=" + w[:3],
            b"p1=" + prev1, b"p2=" + prev2, b"p1p2=" + prev1 + b"|" + prev2,
            b"pw=" + pw, b"ppw=" + ppw, b"nw=" + nw, b"nnw=" + nnw,
            b"p1|w=" + prev1 + b"|" + w,
            b"pw|w=" + pw + b"|" + w,
            b"w|nw=" + w + b"|" + nw,
            b"shape=" + (b"D" if any(48 <= c <= 57 for c in w) else b"-")
                      + (b"H" if 45 in w else b"-"),
        ]

    def tag(self, words: List[str]) -> List[str]:
        """Greedy left-to-right decode. Ties go to the LOWEST tag index -- which is not
        a detail: a word whose features all miss scores zero for every tag, and without
        a fixed rule Python's max() and C's loop would pick different ones."""
        wb = [w.encode("utf-8") for w in words]
        nt = len(self.tags)
        p1, p2 = b"<s>", b"<s2>"
        out: List[str] = []
        for i in range(len(wb)):
            scores = [0] * nt
            for f in self.features(i, wb, p1, p2):
                if len(f) > _MAX_FEATURE:
                    continue
                hit = self._weights.get(f)
                if hit:
                    for k, v in hit:
                        scores[k] += v
            best = 0
            for k in range(1, nt):
                if scores[k] > scores[best]:
                    best = k
            tag = self.tags[best]
            out.append(tag)
            p2, p1 = p1, tag.encode("ascii")
        return out


_CACHE: Dict[str, Optional[PosTagger]] = {}


def load(lang: str, data_dir: Path) -> Optional[PosTagger]:
    """Return the tagger for `lang`, or None if its model is not installed.

    None is a supported state, not an error: a distro that ships without the POS models
    must still phonemize, falling back to each heteronym's majority reading. That is the
    74.1%-correct behaviour the fallbacks already give."""
    if lang not in _CACHE:
        path = data_dir / f"pos_{lang}.bin"
        _CACHE[lang] = PosTagger(path) if path.exists() else None
    return _CACHE[lang]
