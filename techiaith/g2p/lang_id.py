"""Word-level Welsh/English language identification (bilingual routing, P-bilingual).

A lightweight orthographic heuristic used to route out-of-vocabulary words to the
Welsh vs English G2P. In-vocabulary words are resolved by dictionary lookup (a
stronger signal); this only decides the OOV tail and code-switch routing. Default
is Welsh (the majority language of the voice). See docs/BILINGUAL.md.
"""
from __future__ import annotations

_WELSH_ACCENTS = set("âêîôûŵŷ")
_WELSH_CUES = ("ll", "dd", "ff", "rh", "ngh", "mh", "nh", "wy")
_ENGLISH_LETTERS = set("kvxzq")
_ENGLISH_CUES = ("ck", "tion", "sh", "wh", "ght", "qu")

# Very common function words that carry no orthographic cue.
_EN_STOP = {
    "the", "a", "an", "and", "of", "to", "in", "is", "it", "for", "on", "with",
    "as", "at", "by", "this", "that", "he", "she", "they", "we", "you", "was",
    "are", "be", "have", "has", "not", "but", "or", "from", "which", "what",
    "when", "where", "how", "all", "can", "will", "my", "your", "his", "her",
}
_CY_STOP = {"y", "yr", "yn", "ac", "ar", "at", "am", "er", "os", "na", "ni",
            "fe", "mi", "dy", "ei", "eu", "ein", "wrth", "gan", "hyn", "hon"}


def classify_word(word: str) -> str:
    """Return 'cy' or 'en' for a single word. Defaults to 'cy'."""
    w = word.lower().strip("'-.,;:!?()\"…—")
    if not w:
        return "cy"
    if w in _EN_STOP:
        return "en"
    if w in _CY_STOP:
        return "cy"
    en = sum(1 for c in w if c in _ENGLISH_LETTERS) + sum(w.count(c) for c in _ENGLISH_CUES)
    cy = sum(w.count(c) for c in _WELSH_CUES) + sum(1 for c in w if c in _WELSH_ACCENTS)
    # 'w'/'y' as a vowel (word has no a/e/i/o/u) is a Welsh signal.
    if any(c in "wy" for c in w) and not any(v in w for v in "aeiou"):
        cy += 1
    return "en" if en > cy else "cy"


if __name__ == "__main__":
    for w in ["mynydd", "keyboard", "rhaglen", "action", "dŵr", "zebra", "cymraeg", "the"]:
        print(f"  {w!r} -> {classify_word(w)}")
