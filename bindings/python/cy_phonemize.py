"""Python (ctypes) binding for libcy_phonemize (Workstream P / P7 bindings).

The on-device phonemizer, callable from Python — the NVDA-add-on path and a
reference for the other platform bindings (JNI / Swift / Dart FFI / P/Invoke).

    from cy_phonemize import CyPhonemizer
    g = CyPhonemizer(english_mode="native")   # match the model's config.json
    ids = g.text_to_ids("Bore da, mae'r BBC yn dweud £5.99")

Build the shared library first:  make -C techiaith/g2p/c libcy_phonemize.so
"""
from __future__ import annotations

import ctypes
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_DEFAULT_LIB = _REPO / "techiaith" / "g2p" / "c" / "libcy_phonemize.so"
_DEFAULT_CORE = _REPO / "techiaith" / "g2p"
_MAX_IDS = 8192
_MAX_SEGS = 2049                 # 2048 boundaries plus the tail
_MAX_MARKS = 8192
_LANG = {None: 0, "cy": 1, "en": 2}


class _WordMark(ctypes.Structure):
    _fields_ = [("seg", ctypes.c_int), ("word", ctypes.c_int),
                ("src_start", ctypes.c_int), ("src_end", ctypes.c_int)]


class CyPhonemizer:
    def __init__(self, english_mode: str = "accented", core_dir=None, lib_path=None):
        self._lib = ctypes.CDLL(str(lib_path or _DEFAULT_LIB))
        self._lib.cyp_create.restype = ctypes.c_void_p
        self._lib.cyp_create.argtypes = [ctypes.c_char_p, ctypes.c_char_p]
        self._lib.cyp_text_to_ids.restype = ctypes.c_int
        self._lib.cyp_text_to_ids.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.POINTER(ctypes.c_int32), ctypes.c_int]
        self._lib.cyp_data_version.restype = ctypes.c_char_p
        self._lib.cyp_data_version.argtypes = [ctypes.c_void_p]
        self._lib.cyp_num_symbols.restype = ctypes.c_int
        self._lib.cyp_num_symbols.argtypes = [ctypes.c_void_p]
        self._lib.cyp_destroy.argtypes = [ctypes.c_void_p]
        self._lib.cyp_segment_spans.restype = ctypes.c_int
        self._lib.cyp_segment_spans.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(ctypes.c_int),
            ctypes.POINTER(ctypes.c_int), ctypes.c_int]
        self._lib.cyp_word_marks.restype = ctypes.c_int
        self._lib.cyp_word_marks.argtypes = [
            ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int, ctypes.POINTER(_WordMark), ctypes.c_int]
        self._lib.cyp_word_starts.restype = ctypes.c_int
        self._lib.cyp_word_starts.argtypes = [
            ctypes.POINTER(ctypes.c_int32), ctypes.c_int, ctypes.POINTER(ctypes.c_int), ctypes.c_int]
        self._p = self._lib.cyp_create(
            str(core_dir or _DEFAULT_CORE).encode("utf-8"), english_mode.encode("utf-8"))
        if not self._p:
            raise RuntimeError("cyp_create failed (check core_dir + data files)")

    def text_to_ids(self, text: str) -> list[int]:
        buf = (ctypes.c_int32 * _MAX_IDS)()
        n = self._lib.cyp_text_to_ids(self._p, text.encode("utf-8"), buf, _MAX_IDS)
        if n < 0:
            raise RuntimeError("cyp_text_to_ids overflow")
        return list(buf[:n])

    # Word highlighting. Offsets are UTF-8 BYTE offsets into text.encode("utf-8"), as the C ABI
    # returns them (BangorG2P's are code points).
    def segment_spans(self, text: str, lang: str | None = None) -> list[tuple[int, int]]:
        a = (ctypes.c_int * _MAX_SEGS)()
        e = (ctypes.c_int * _MAX_SEGS)()
        n = self._lib.cyp_segment_spans(self._p, text.encode("utf-8"), _LANG[lang], a, e, _MAX_SEGS)
        if n < 0:
            raise RuntimeError("cyp_segment_spans overflow")
        return list(zip(a[:n], e[:n]))

    def word_marks(self, text: str, lang: str | None = None) -> list[tuple[int, int, int, int]]:
        """[(seg, word, src_start, src_end)]."""
        buf = (_WordMark * _MAX_MARKS)()
        n = self._lib.cyp_word_marks(self._p, text.encode("utf-8"), _LANG[lang], buf, _MAX_MARKS)
        if n < 0:
            raise RuntimeError("cyp_word_marks overflow")
        return [(m.seg, m.word, m.src_start, m.src_end) for m in buf[:n]]

    def word_starts(self, ids: list[int]) -> list[int]:
        arr = (ctypes.c_int32 * max(1, len(ids)))(*ids)
        out = (ctypes.c_int * max(1, len(ids)))()
        n = self._lib.cyp_word_starts(arr, len(ids), out, len(out))
        if n < 0:
            raise RuntimeError("cyp_word_starts overflow")
        return list(out[:n])

    def data_version(self) -> str:
        return self._lib.cyp_data_version(self._p).decode("utf-8")

    def num_symbols(self) -> int:
        return self._lib.cyp_num_symbols(self._p)

    def __del__(self):
        p = getattr(self, "_p", None)
        if p:
            self._lib.cyp_destroy(p)


if __name__ == "__main__":
    g = CyPhonemizer(english_mode="native")
    print("data_version:", g.data_version(), "num_symbols:", g.num_symbols())
    print(g.text_to_ids("Bore da, mae'r BBC yn dweud £5.99 am 3:00"))
