"""Shared fixtures/guards for the parity tests.

The C-vs-Python cross-checks load techiaith/g2p/c/libcy_phonemize.so through ctypes, but
`make check` builds the five ./test_* binaries and (until recently) not the shared library,
so the two were free to drift. A stale .so silently disarms every cross-check: it happened
during the isolated-K change, where `make check` reported 82/82 green while pytest was
exercising a library five hours older than its source. `check` now depends on the .so, but
nothing stopped pytest being run directly against a stale one -- which is exactly the
situation the cross-checks exist to cover.
"""
import os
from pathlib import Path

import pytest

C_DIR = Path(__file__).resolve().parent.parent / "techiaith" / "g2p" / "c"
SO = C_DIR / "libcy_phonemize.so"
SOURCES = ("cy_phonemize.c", "cy_normalize.c", "cy_english.c",
           "cy_phonemize.h", "cy_english.h")


@pytest.fixture(scope="session", autouse=True)
def _reject_a_stale_shared_library():
    """Fail loudly if libcy_phonemize.so predates any of its sources."""
    if not SO.exists():
        return                      # individual tests skip on a missing .so
    so_mtime = SO.stat().st_mtime
    stale = [name for name in SOURCES
             if (C_DIR / name).exists() and (C_DIR / name).stat().st_mtime > so_mtime]
    if stale:
        pytest.fail(
            f"libcy_phonemize.so is older than {', '.join(stale)} — the C/Python "
            f"cross-checks would certify a stale library. Run "
            f"`make -C techiaith/g2p/c libcy_phonemize.so` (or `make check`, which now "
            f"depends on it) and re-run.",
            pytrace=False,
        )
