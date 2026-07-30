"""Audit the rule-based LTS against the full Welsh dictionary (the oracle).

Not a pass/fail test — a measurement. Reports exact-match (incl. stress/syllable
markers) and phones-only accuracy over every native Welsh headword, plus the most
common phone-substitution errors to guide rule refinement.

Run: python3 tests/audit_lts.py [limit]
"""
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

from techiaith.g2p.bangor_g2p import _parse_line, _tokenize_phone_column
from techiaith.g2p.bangor_lts import lts

DICT = REPO / "techiaith" / "g2p" / "data" / "geiriadur-ynganu-bangor" / "bangordict.dict"
MARKERS = {"ˈ", "|"}


def strip_markers(toks):
    return [t for t in toks if t not in MARKERS]


def main():
    limit = int(sys.argv[1]) if len(sys.argv) > 1 else None
    exact = phones_ok = total = 0
    sub_errors = Counter()
    samples = []
    for raw in DICT.read_text(encoding="utf-8").splitlines():
        p = _parse_line(raw)
        if not p:
            continue
        word, phones = p
        if not word.isalpha() or "'" in word:   # skip clitics/odd headwords for a clean baseline
            continue
        gold = _tokenize_phone_column(phones)
        got = lts(word)
        total += 1
        if got == gold:
            exact += 1
        gp, pp = strip_markers(gold), strip_markers(got)
        if gp == pp:
            phones_ok += 1
        else:
            if len(gp) == len(pp):
                for a, b in zip(pp, gp):
                    if a != b:
                        sub_errors[f"{a}->{b}"] += 1
            if len(samples) < 12:
                samples.append((word, gold, got))
        if limit and total >= limit:
            break

    print(f"words audited: {total}")
    print(f"exact match  (incl. ˈ/|): {exact:>6}  {100*exact/total:5.1f}%")
    print(f"phones-only match        : {phones_ok:>6}  {100*phones_ok/total:5.1f}%")
    print("\ntop phone substitutions (got->gold):")
    for k, v in sub_errors.most_common(15):
        print(f"  {k:14} {v}")
    print("\nsample mismatches:")
    for w, gold, got in samples:
        print(f"  {w}\n    gold {gold}\n    lts  {got}")


if __name__ == "__main__":
    main()
