"""Native English G2P for the bilingual Welsh voice (Workstream P — bilingual).

Pronounces English words in our phone set, keeping English distinctions (æ ʌ ɹ @r):
  * lexicon lookup over the native CMUdict (~126k words), then
  * a compact rule-based English LTS for out-of-vocabulary words.

Two output modes:
  * native=True  -> English phones (for a native-English-trained model)
  * native=False -> folded to nearest Welsh phones via id-map `english_fold`
                    (for the current Welsh-only model)

The CMUdict lexicon is the accurate bulk; the LTS is a rough fallback for the rare
tail (English orthography is irregular) — audited by tests/audit_english_lts.py.
See docs/BILINGUAL.md.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional

_HERE = Path(__file__).resolve().parent
_LEX = _HERE / "data" / "english" / "cmudict_native.dict"
_IDMAP = _HERE / "bangor_phoneme_id_map.json"

STRESS = "ˈ"

# ---- compact English letter-to-sound (native phones) ----
_DIGRAPH = [
    ("tch", ["ch"]), ("igh", ["ai"]), ("ough", ["oo"]), ("augh", ["oo"]),
    ("sh", ["sh"]), ("ch", ["ch"]), ("th", ["th"]), ("ph", ["f"]), ("ck", ["k"]),
    ("ng", ["ng"]), ("qu", ["k", "w"]), ("wh", ["w"]), ("gh", []), ("kn", ["n"]),
    ("wr", ["ɹ"]), ("gn", ["n"]),
    ("ar", ["aa", "ɹ"]), ("or", ["oo", "ɹ"]), ("er", ["@r"]), ("ir", ["@r"]),
    ("ur", ["@r"]), ("ee", ["ii"]), ("ea", ["ii"]), ("oo", ["uu"]), ("oa", ["ou"]),
    ("ai", ["ei"]), ("ay", ["ei"]), ("oi", ["oi"]), ("oy", ["oi"]), ("ou", ["au"]),
    ("ow", ["au"]), ("au", ["oo"]), ("aw", ["oo"]), ("ew", ["j", "uu"]), ("ie", ["ii"]),
]
_VOWEL = {"a": "æ", "e": "e", "i": "i", "o": "ɒ", "u": "ʌ", "y": "i"}
_LONG = {"a": "ei", "e": "ii", "i": "ai", "o": "ou", "u": "uu", "y": "ai"}
_CONS = {"b": "b", "c": "k", "d": "d", "f": "f", "g": "g", "h": "hh", "j": "jh",
         "k": "k", "l": "l", "m": "m", "n": "n", "p": "p", "r": "ɹ", "s": "s",
         "t": "t", "v": "v", "w": "w", "x": "ks", "z": "z"}
_VOWELS = set("aeiouy")


def english_lts(word: str) -> List[str]:
    """Rough rule-based English G2P -> native phones (OOV fallback only)."""
    w = "".join(c for c in word.lower() if c.isalpha())
    if not w:
        return []
    # silent final 'e' after V C (make the vowel long): tape, bike, note
    if len(w) >= 3 and w.endswith("e") and w[-2] not in _VOWELS and w[-3] in _VOWELS:
        w = w[:-1]
        long_last_vowel = True
    else:
        long_last_vowel = False
    toks: List[str] = []
    i, n = 0, len(w)
    first_vowel_idx = None
    while i < n:
        c = w[i]
        matched = False
        for g, out in _DIGRAPH:
            if w.startswith(g, i):
                if any(o in ("aa", "oo", "ei", "ii", "ai", "ou", "oi", "au", "uu", "@r") for o in out) and first_vowel_idx is None:
                    first_vowel_idx = len(toks)
                toks.extend(out)
                i += len(g)
                matched = True
                break
        if matched:
            continue
        if c in _VOWELS:
            if first_vowel_idx is None:
                first_vowel_idx = len(toks)
            # long if this is the last vowel and silent-e applied
            is_last_vowel = not any(x in _VOWELS for x in w[i + 1:])
            if long_last_vowel and is_last_vowel:
                toks.append(_LONG[c])
            else:
                toks.append(_VOWEL[c])
            i += 1
        elif c in _CONS:
            # soft c/g before e,i,y
            nxt = w[i + 1] if i + 1 < n else ""
            if c == "c" and nxt in "eiy":
                toks.append("s")
            elif c == "g" and nxt in "eiy":
                toks.append("jh")
            elif c == "x":
                toks.extend(["k", "s"])
            else:
                toks.append(_CONS[c])
            i += 1
        else:
            i += 1
    # crude stress: before the first vowel
    if first_vowel_idx is not None:
        toks.insert(first_vowel_idx, STRESS)
    return toks


class EnglishG2P:
    def __init__(self, lexicon_path: Path = _LEX, id_map_path: Path = _IDMAP):
        self.lex: Dict[str, List[str]] = {}
        for line in Path(lexicon_path).read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            word, toks = line.split("\t")
            self.lex[word] = toks.split(" ")
        self.fold_map: Dict[str, List[str]] = json.loads(
            Path(id_map_path).read_text(encoding="utf-8")
        )["english_fold"]

    def lookup(self, word: str) -> Optional[List[str]]:
        return self.lex.get(word.lower())

    def fold(self, tokens: List[str]) -> List[str]:
        out: List[str] = []
        for t in tokens:
            out.extend(self.fold_map.get(t, [t]))
        return out

    def phonemize(self, word: str, native: bool = True) -> List[str]:
        toks = self.lookup(word)
        if toks is None:
            toks = english_lts(word)
        return list(toks) if native else self.fold(toks)


if __name__ == "__main__":
    g = EnglishG2P()
    print("lexicon:", len(g.lex))
    for w in ["cardiff", "computer", "the", "zworbtastic", "brightness"]:
        print(f"  {w}: native={g.phonemize(w, True)}  folded={g.phonemize(w, False)}")
