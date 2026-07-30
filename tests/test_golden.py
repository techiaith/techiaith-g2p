"""Golden-parity test: the reference G2P must reproduce every seed vector exactly.

This is the P8 contract in miniature for the Python reference (P1). It is RED
until techiaith/g2p/bangor_g2p.py exists and is correct.
"""
import json
import sys
from pathlib import Path

from techiaith.g2p.bangor_g2p import BangorG2P

REPO = Path(__file__).resolve().parent.parent

SEEDS = [json.loads(l) for l in (REPO / "tests" / "golden" / "seed.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]

_g2p = None


def g2p() -> BangorG2P:
    global _g2p
    if _g2p is None:
        _g2p = BangorG2P()
    return _g2p


def test_seeds_present():
    assert len(SEEDS) >= 30, f"expected >=30 seed cases, got {len(SEEDS)}"


def _run():
    """Standalone runner (no pytest needed): returns (passed, failures)."""
    g = g2p()
    failures = []
    for case in SEEDS:
        text = case["text"]
        try:
            got_tokens = g.phonemize(text)
            got_ids = g.text_to_ids(text)
        except Exception as e:  # noqa: BLE001
            failures.append((text, f"raised {e!r}", None))
            continue
        if got_tokens != case["phone_tokens"]:
            failures.append((text, case["phone_tokens"], got_tokens))
        elif got_ids != case["ids"]:
            failures.append((text, case["ids"], got_ids))
    return len(SEEDS) - len(failures), failures


def test_all_seed_ids_match():
    passed, failures = _run()
    msg = "\n".join(f"  {t!r}: expected {exp} got {got}" for t, exp, got in failures)
    assert not failures, f"{len(failures)}/{len(SEEDS)} golden mismatches:\n{msg}"


if __name__ == "__main__":
    passed, failures = _run()
    print(f"{passed}/{passed + len(failures)} golden cases pass")
    for t, exp, got in failures:
        print(f"  FAIL {t!r}: expected {exp} got {got}")
    sys.exit(1 if failures else 0)
