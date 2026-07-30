"""The one interpreter this repo's generated artifacts are produced under.

Why this file exists: str.isdecimal() and str.isalpha() are Unicode-version-dependent, so
"the C port reproduces the Python reference byte for byte" says nothing until you name WHICH
Python. Several are in play on a development host and they agreed only by luck. Publishing to
PyPI widens that to whatever users have installed.

MEASURED on the development host, 2026-07-29 -- and note that an earlier version of this
docstring named "a 3.12 dev venv", which does not exist. There is no Python 3.12 on this
machine at all; do not trust that description if you meet it elsewhere. The same table, with
roles, is in c/README.md.

    /usr/bin/python3.10                        3.10.12   Unicode 13.0.0   CANONICAL, has pytest
    /home/linuxbrew/.../bin/python3.10         3.10.20   Unicode 13.0.0
    /home/linuxbrew/.../bin/python3.14         3.14.6    Unicode 16.0.0   has pytest
    the dev venv (piper-cy/.venv/bin/python)   3.10.12   Unicode 13.0.0   has pytest

3.10 is canonical because it is what the deployed API container serves, and because it has the
OLDEST character tables of the four -- anything it accepts, a newer interpreter also accepts.
Unicode 13 has 65 Nd blocks; Unicode 16 has 76.

Changing either value here is a deliberate act: it requires regenerating every artifact from
scripts/emit_c_data.py AND the ND_BLOCK table in c/cy_normalize.c under the new interpreter.
tests/test_ssml_primitives.py fails loudly if the committed artifacts and this file disagree.
"""
from __future__ import annotations

CANONICAL_PYTHON = "3.10"
CANONICAL_UNICODE = "13.0.0"

# Unicode 13.0.0 Nd block starts -- the codepoint of the '0' of every decimal-digit block.
# This is the SAME table as ND_BLOCK in c/cy_normalize.c, and
# tests/test_ssml_primitives.py walks all 0x110000 codepoints to prove it.
#
# It is vendored rather than derived from str.isdecimal() because isdecimal() follows the host
# interpreter's Unicode version: 65 blocks on 3.10, 76 on 3.14. Deriving it would mean the
# reference G2P classified digits differently on a user's machine than the shipped C port does,
# for any block added after 13.0 -- a divergence no test on the developer's machine could see.
#
# REGENERATE with scripts/emit_c_data.py under the canonical interpreter; it writes both this
# table and C's from one source, so they cannot drift apart.
ND_BLOCK = (
    0x0030, 0x0660, 0x06F0, 0x07C0, 0x0966, 0x09E6, 0x0A66, 0x0AE6, 0x0B66, 0x0BE6, 0x0C66,
    0x0CE6, 0x0D66, 0x0DE6, 0x0E50, 0x0ED0, 0x0F20, 0x1040, 0x1090, 0x17E0, 0x1810, 0x1946,
    0x19D0, 0x1A80, 0x1A90, 0x1B50, 0x1BB0, 0x1C40, 0x1C50, 0xA620, 0xA8D0, 0xA900, 0xA9D0,
    0xA9F0, 0xAA50, 0xABF0, 0xFF10, 0x104A0, 0x10D30, 0x11066, 0x110F0, 0x11136, 0x111D0, 0x112F0,
    0x11450, 0x114D0, 0x11650, 0x116C0, 0x11730, 0x118E0, 0x11950, 0x11C50, 0x11D50, 0x11DA0, 0x16A60,
    0x16B50, 0x1D7CE, 0x1D7D8, 0x1D7E2, 0x1D7EC, 0x1D7F6, 0x1E140, 0x1E2F0, 0x1E950, 0x1FBF0,
)


def decimal_value(ch: str) -> int:
    """Python str.isdecimal()'s digit VALUE for one character, or -1 -- from the fixed table.

    isdecimal, not isdigit: '²' and '①' are isdigit but int() rejects them. '٣'
    (Arabic-Indic three) IS decimal and must read "tri" in both implementations.
    """
    cp = ord(ch)
    for start in ND_BLOCK:
        if start <= cp < start + 10:
            return cp - start
    return -1
