"""Packaging tests for techiaith.g2p: install shape, namespace package, and the exact import
the model card will show.
"""
import subprocess
import sys

import pytest


def test_g2p_importable_by_dotted_path():
    # A fast local smoke check, not an airtight isolation proof. Subprocess with -E (ignore
    # PYTHONPATH) and cwd outside the repo, so a bare `python -c "from techiaith.g2p import
    # ..."` at least can't be rescued by PYTHONPATH or the cwd script directory.
    #
    # What this can't catch: under `pip install -e .` -- an editable install, how most
    # contributors will actually run this -- the site-packages .pth shim that pip/hatchling
    # writes puts the repo root on sys.path regardless of -E, PYTHONPATH, or cwd (confirmed
    # with `env -u PYTHONPATH python3.10 -E -c "import sys; print(sys.path)"`: the repo root
    # is there anyway). So in the editable-install case this test cannot fail on "only
    # reachable via a sys.path hack" -- the exact failure the model card hits today -- it can
    # only catch a completely broken import (missing file, syntax error, wrong package
    # layout). That's still worth having cheaply and locally, but the real, airtight version
    # of this check -- a clean venv with nothing installed but the built wheel -- is Task 4's
    # CI build job, not this test.
    #
    # Also deliberately not -I: isolated mode disables the user-site directory
    # (~/.local/.../site-packages), a legitimate, common install location (e.g. `pip install
    # --user`). Under -I this assertion is unsatisfiable for such an install for reasons that
    # have nothing to do with whether the package is genuinely importable -- don't restore it.
    r = subprocess.run(
        [sys.executable, "-E", "-c",
         "from techiaith.g2p import BangorG2P;"
         "print(BangorG2P(english_mode='native').data_version())"],
        capture_output=True, text=True, cwd="/tmp")
    assert r.returncode == 0, r.stderr
    assert len(r.stdout.strip()) == 16


def test_techiaith_is_a_namespace_package():
    """techiaith/ must have no __init__.py so a future techiaith-* can share the name.

    The 0.1.6 release made it a regular package (techiaith/version.py, techiaith/py.typed),
    which would collide with any second distribution under the same namespace.
    """
    import techiaith
    assert getattr(techiaith, "__file__", None) is None, (
        "techiaith/ has an __init__.py — that makes it a regular package")


def test_the_card_snippet_import_works():
    """The exact line the HF model card will show, asserted so it cannot silently rot."""
    from techiaith.g2p import BangorG2P
    g2p = BangorG2P(english_mode="native")
    ids = g2p.text_to_ids("Bore da. Sut wyt ti'n teimlo heddiw?")
    assert ids[0] == 1 and ids[-1] == 2      # [BOS] ... [EOS], per docs/PARITY.md
    assert len(ids) > 20


def test_no_third_party_imports_in_the_g2p():
    """A dependency here would defeat the point: the API and NVDA paths need this bare."""
    import ast
    import pathlib

    import techiaith.g2p as pkg
    allowed = {"__future__", "hashlib", "json", "re", "pathlib", "typing", "unicodedata"}
    for path in pathlib.Path(pkg.__file__).parent.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for a in node.names:
                    assert a.name.split(".")[0] in allowed, f"{path.name}: {a.name}"
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                assert node.module.split(".")[0] in allowed, f"{path.name}: {node.module}"


def test_no_data_version_literal():
    """A pinned hash breaks against the next retrain; it must always be computed."""
    import pathlib

    import techiaith.g2p
    root = pathlib.Path(techiaith.g2p.__file__).parent
    for p in root.rglob("*.py"):
        assert "b1edc63e35bb7a6f" not in p.read_text(encoding="utf-8"), f"literal in {p}"


def test_missing_emoji_file_raises_loudly(tmp_path):
    """Missing emoji_cy.tsv must raise RuntimeError, not degrade silently.

    When data/emoji_cy.tsv is missing from a packaged wheel, the phonemizer must fail
    loudly rather than ship with a silently broken emoji reader. This defect is unreachable
    from a git checkout (the file is tracked) but a real failure mode once distributed.
    """
    from techiaith.g2p import welsh_normalize as wn
    missing_file = tmp_path / "does-not-exist.tsv"
    with pytest.raises(RuntimeError, match=str(missing_file)):
        wn._load_emoji(missing_file)


def test_empty_emoji_file_raises_loudly(tmp_path):
    """Empty emoji_cy.tsv must raise RuntimeError, degradation identical to missing file.

    An empty file degrades just as silently as a missing one: the phonemizer loads but
    reads no emoji names. Treating both failures identically prevents a zero-byte file
    from shipping a broken installation undetected.
    """
    from techiaith.g2p import welsh_normalize as wn
    empty_file = tmp_path / "empty.tsv"
    empty_file.write_text("")
    with pytest.raises(RuntimeError, match=str(empty_file)):
        wn._load_emoji(empty_file)


def test_whitespace_only_emoji_file_raises_loudly(tmp_path):
    """Whitespace-only emoji_cy.tsv must raise RuntimeError, same as empty file.

    Like an empty file, a file containing only whitespace yields a zero-entry emoji
    table and silently breaks the phonemizer. Both should raise to prevent accidental
    distribution of a broken install.
    """
    from techiaith.g2p import welsh_normalize as wn
    whitespace_file = tmp_path / "whitespace.tsv"
    whitespace_file.write_text("   \n\n\t  \n")
    with pytest.raises(RuntimeError, match=str(whitespace_file)):
        wn._load_emoji(whitespace_file)
