"""Rule-based Welsh grapheme->phone LTS for out-of-vocabulary words (P3).

The dictionary (P1) covers ~29k Welsh words + names; this handles the tail —
words not listed. Welsh orthography is highly regular, so ordered longest-match
rules + a vowel-length heuristic + penultimate stress get most of it. Output is
Bangor phone tokens (with stress ˈ and syllable |), the same inventory as the
dictionary, so it feeds the id-map identically. Accuracy is measured against the
full dictionary by tests/audit_lts.py (the oracle).

Known-hard (measured, not claimed perfect): vowel length in ambiguous contexts,
the ng=/ŋ/ vs /ŋɡ/ split, wy/w disambiguation, and non-native letters.
"""
from __future__ import annotations

from typing import Dict, List, Tuple

_ACCENT_LONG = {"â": "a", "ê": "e", "î": "i", "ô": "o", "û": "u", "ŵ": "w", "ŷ": "y"}
_ACCENT_BASE = {
    "à": "a", "á": "a", "ä": "a", "è": "e", "é": "e", "ë": "e", "ì": "i", "í": "i",
    "ï": "i", "ò": "o", "ó": "o", "ö": "o", "ù": "u", "ú": "u", "ü": "u", "ẁ": "w",
    "ẃ": "w", "ẅ": "w", "ỳ": "y", "ý": "y", "ÿ": "y",
}

_CONS3 = {"ngh": "ngh"}
_CONS2 = {"ng": "ng", "ch": "x", "dd": "dh", "ff": "f", "ll": "lh", "ph": "f",
          "rh": "rh", "th": "th", "mh": "mh", "nh": "nh"}
_CONS1 = {"b": "b", "c": "k", "d": "d", "f": "v", "g": "g", "h": "hh", "j": "jh",
          "l": "l", "m": "m", "n": "n", "p": "p", "r": "r", "s": "s", "t": "t", "k": "k"}
_DIPH = {"ae": "aay", "ai": "ai", "au": "ay", "aw": "au", "ei": "ei", "eu": "ey",
         "ew": "eu", "ey": "ey", "iw": "iu", "oe": "oy", "oi": "oi", "ou": "ou",
         "ow": "ou", "uw": "iu", "wy": "uy", "yw": "yu"}
_VOW = {"a": ("a", "aa"), "e": ("e", "ee"), "i": ("i", "ii"),
        "o": ("o", "oo"), "u": ("y", "yy"), "w": ("u", "uu")}
_VOWEL_LETTERS = set("aeiouwy")
# A single one of these lengthens a preceding *stressed* vowel; else short.
_LONG_CODA = {"b", "d", "g", "v", "dh", "f", "th", "x", "s"}

STRESS = "ˈ"
SYLLABLE = "|"


def _prep(word: str) -> Tuple[str, List[bool]]:
    base_chars, forced = [], []
    for ch in word.lower():
        if ch in _ACCENT_LONG:
            base_chars.append(_ACCENT_LONG[ch]); forced.append(True)
        elif ch in _ACCENT_BASE:
            base_chars.append(_ACCENT_BASE[ch]); forced.append(False)
        else:
            base_chars.append(ch); forced.append(False)
    return "".join(base_chars), forced


def _segment(base: str, forced: List[bool]) -> List[Tuple[str, object]]:
    """-> list of ('C', token) | ('V', {...})."""
    segs: List[Tuple[str, object]] = []
    i, n = 0, len(base)

    def isv(c: str) -> bool:
        return c in _VOWEL_LETTERS

    while i < n:
        c = base[i]
        # s + i + vowel -> /ʃ/
        if c == "s" and base[i + 1:i + 2] == "i" and i + 2 < n and isv(base[i + 2]):
            segs.append(("C", "sh")); i += 2; continue
        g3, g2 = base[i:i + 3], base[i:i + 2]
        if g3 in _CONS3:
            segs.append(("C", _CONS3[g3])); i += 3; continue
        if g2 in _CONS2:
            segs.append(("C", _CONS2[g2])); i += 2; continue
        if c in _CONS1:
            segs.append(("C", _CONS1[c])); i += 1; continue
        # consonantal i (/j/) at an onset before a vowel (iaith; -ion, -iad, -io endings)
        if c == "i" and i + 1 < n and isv(base[i + 1]) and (not segs or segs[-1][0] == "C"):
            segs.append(("C", "j")); i += 1; continue
        # w: part of "wy" diphthong / consonant / vowel
        if c == "w":
            nxt = base[i + 1:i + 2]
            if nxt == "y":
                segs.append(("V", {"diph": "uy"})); i += 2; continue
            if nxt and isv(nxt):
                segs.append(("C", "w")); i += 1; continue
            segs.append(("V", {"letter": "w", "forced": forced[i]})); i += 1; continue
        # vowel diphthong
        if g2 in _DIPH:
            segs.append(("V", {"diph": _DIPH[g2]})); i += 2; continue
        # single vowel
        if c in _VOW or c == "y":
            segs.append(("V", {"letter": c, "forced": forced[i]})); i += 1; continue
        i += 1  # skip apostrophes, hyphens, unknown chars
    return _postprocess(segs)


def _postprocess(segs):
    # collapse geminate consonants (nn, rr, ...) to one sound
    collapsed = []
    for s in segs:
        if collapsed and s[0] == "C" and collapsed[-1] == s:
            continue
        collapsed.append(s)
    segs = collapsed
    # s-cluster devoicing: s + b/d/g -> s + p/t/k (ysgol /əskɔl/, sbectol /sp-/)
    devoice = {"b": "p", "d": "t", "g": "k"}
    for i in range(len(segs) - 1):
        if segs[i] == ("C", "s") and segs[i + 1][0] == "C" and segs[i + 1][1] in devoice:
            segs[i + 1] = ("C", devoice[segs[i + 1][1]])
    # nasal assimilation: n before k/g -> ŋ (dianc /-ŋk/)
    for i in range(len(segs) - 1):
        if segs[i] == ("C", "n") and segs[i + 1][0] == "C" and segs[i + 1][1] in ("k", "g"):
            segs[i] = ("C", "ng")
    return segs


def lts(word: str) -> List[str]:
    base, forced = _prep(word)
    segs = _segment(base, forced)
    vidx = [k for k, s in enumerate(segs) if s[0] == "V"]
    nsyll = len(vidx)
    if nsyll == 0:
        return [STRESS] + [s[1] for s in segs] if segs else []
    stress_syll = 0 if nsyll == 1 else nsyll - 2
    syll_of = {k: sy for sy, k in enumerate(vidx)}

    def following_cons(k: int) -> List[str]:
        toks, j = [], k + 1
        while j < len(segs) and segs[j][0] == "C":
            toks.append(segs[j][1]); j += 1
        return toks

    def resolve(k: int, v: dict, sy: int) -> str:
        if "diph" in v:
            return v["diph"]
        letter, is_final = v["letter"], (sy == nsyll - 1)
        stressed = sy == stress_syll
        if letter == "y":
            if not is_final and nsyll > 1:
                return "@"                       # obscure y (schwa)
            short, long_ = "y", "yy"             # clear y
        else:
            short, long_ = _VOW[letter]
        fol = following_cons(k)
        long_v = v["forced"] or (stressed and (len(fol) == 0 or (len(fol) == 1 and fol[0] in _LONG_CODA)))
        return long_ if long_v else short

    # syllable start segment indices (maximal-onset-ish)
    starts: Dict[int, int] = {0: 0}
    for sy in range(1, nsyll):
        k, kp = vidx[sy], vidx[sy - 1]
        c = k - kp - 1
        starts[sy] = k if c == 0 else (kp + 1 if c == 1 else kp + 2)
    start_seg = {seg_idx: sy for sy, seg_idx in starts.items()}

    out: List[str] = []
    for idx, seg in enumerate(segs):
        if idx in start_seg:
            sy = start_seg[idx]
            if sy > 0:
                out.append(SYLLABLE)
            if sy == stress_syll:
                out.append(STRESS)
        out.append(seg[1] if seg[0] == "C" else resolve(idx, seg[1], syll_of[idx]))
    return out


if __name__ == "__main__":
    for w in ["cath", "afal", "mynydd", "ceffyl", "ysgrifennu", "gwyn", "siop", "chwaraeon"]:
        print(f"  {w!r} -> {lts(w)}")
