"""Parity test for the ctypes binding: the shared library (via Python) must match
the Python reference BangorG2P, in both english modes. Proves the .so + binding
plumbing end-to-end. Requires: make -C techiaith/g2p/c libcy_phonemize.so
"""
import sys
from pathlib import Path

from techiaith.g2p.bangor_g2p import BangorG2P

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "bindings" / "python"))

from cy_phonemize import CyPhonemizer  # noqa: E402

INPUTS = [
    "bore da", "cymru", "mynydd", "ci bach", "sgrwtlaniog",   # Welsh (dict + LTS)
    "mae 25 o gathod", "yn 2026", "17 Gorffennaf 2026", "£5.99", "3:00", "50%",  # normalization
    "computer", "the quick brown fox", "Mae'r BBC yn dda", "cardiff",  # English / code-switch
]


def _check(mode):
    ref = BangorG2P(english_mode=mode)
    lib = CyPhonemizer(english_mode=mode)
    assert lib.data_version() == ref.data_version(), (mode, lib.data_version(), ref.data_version())
    bad = [t for t in INPUTS if lib.text_to_ids(t) != ref.text_to_ids(t)]
    return bad


def test_binding_native():
    assert not _check("native")


def test_binding_accented():
    assert not _check("accented")


if __name__ == "__main__":
    fails = 0
    for mode in ("native", "accented"):
        bad = _check(mode)
        print(f"{len(INPUTS) - len(bad)}/{len(INPUTS)} binding parity ({mode})" + (f"  FAIL: {bad}" if bad else ""))
        fails += len(bad)
    sys.exit(1 if fails else 0)
