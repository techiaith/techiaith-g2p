"""Gate G4: the training phonemization path reproduces the frozen goldens.

The preprocess 'bangor' worker (../piper-cy .../preprocess.py) computes, per
utterance:  normalize -> phonemize(on_oov='lts') -> phonemes_to_ids  — which must
equal BangorG2P.text_to_ids AND the frozen golden ids (train == inference ==
contract). This runs with plain Python (no training deps). The full preprocess.py
module is additionally verified in the training venv (see docs / commit notes).
"""
import json
import sys
from pathlib import Path

from techiaith.g2p.bangor_g2p import BangorG2P

REPO = Path(__file__).resolve().parent.parent

SEEDS = [json.loads(l) for l in (REPO / "tests" / "golden" / "seed.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]


def _worker_ids(g: BangorG2P, text: str):
    """Exactly what phonemize_batch_bangor computes for each utterance."""
    return g.phonemes_to_ids(g.phonemize(g.normalize(text), on_oov="lts"))


def test_g4_train_inference_parity():
    g = BangorG2P()
    bad = [s["text"] for s in SEEDS
           if not (_worker_ids(g, s["text"]) == g.text_to_ids(s["text"]) == s["ids"])]
    assert not bad, f"G4 parity failures: {bad}"


if __name__ == "__main__":
    g = BangorG2P()
    bad = [s["text"] for s in SEEDS if _worker_ids(g, s["text"]) != s["ids"]]
    print(f"{len(SEEDS) - len(bad)}/{len(SEEDS)} G4 parity")
    sys.exit(1 if bad else 0)
