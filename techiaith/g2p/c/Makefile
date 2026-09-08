# libcy_phonemize (Workstream P / P7). Run `make check` (or `make check CORE=..`).
CC ?= cc
CFLAGS ?= -O2 -std=gnu11 -Wall -Wextra
CORE ?= ..

OBJ = cy_phonemize.o cy_normalize.o cy_english.o cy_pos.o

libcy_phonemize.a: $(OBJ)
	ar rcs $@ $^

# shared library for FFI bindings (ctypes / JNI / Dart FFI / P-Invoke)
# cy_emoji_data.h is GENERATED (scripts/gen_emoji_cy.py -> scripts/emit_c_data.py) and is
# included by cy_normalize.c. It was missing from these prerequisites, so regenerating the
# emoji table left a stale .so behind and `make` reported "up to date" -- the exact stale-.so
# trap the comment below already warns about. Found 2026-09-02 regenerating the table off
# espeak-ng; do not drop it again.
libcy_phonemize.so: cy_phonemize.c cy_normalize.c cy_english.c cy_pos.c cy_phonemize.h cy_english.h cy_pos.h cy_emoji_data.h
	$(CC) $(CFLAGS) -fPIC -shared cy_phonemize.c cy_normalize.c cy_english.c cy_pos.c -o $@

cy_phonemize.o: cy_phonemize.c cy_phonemize.h cy_english.h
	$(CC) $(CFLAGS) -c $< -o $@

cy_normalize.o: cy_normalize.c cy_phonemize.h cy_emoji_data.h
	$(CC) $(CFLAGS) -c $< -o $@

cy_english.o: cy_english.c cy_english.h
	$(CC) $(CFLAGS) -c $< -o $@

# $< $(OBJ), not $^: test_common.h is a prerequisite so editing it rebuilds the suites,
# but passing a header to the compiler as an input is a GCC extension. NDK clang, Apple
# clang and MSVC -- the toolchains this port targets -- can reject or mis-handle it.
test_golden: test_golden.c test_common.h $(OBJ)
	$(CC) $(CFLAGS) $< $(OBJ) -o $@

test_lts: test_lts.c test_common.h $(OBJ)
	$(CC) $(CFLAGS) $< $(OBJ) -o $@

test_norm: test_norm.c test_common.h $(OBJ)
	$(CC) $(CFLAGS) $< $(OBJ) -o $@

test_bilingual: test_bilingual.c test_common.h $(OBJ)
	$(CC) $(CFLAGS) $< $(OBJ) -o $@

test_ssml: test_ssml.c test_common.h $(OBJ)
	$(CC) $(CFLAGS) $< $(OBJ) -o $@
test_segments: test_segments.c test_common.h $(OBJ)
	$(CC) $(CFLAGS) $< $(OBJ) -o $@

# libcy_phonemize.so is a prerequisite even though no ./test_* binary links it: the
# Python C-vs-Python cross-checks in tests/test_ssml_primitives.py load it via ctypes.
# Without it here, `make check` can pass green against freshly built test binaries
# while pytest silently certifies a stale .so -- which is exactly what happened when
# the isolated-K change landed (make check 82/82, pytest reporting C/Python divergence).
check: test_golden test_lts test_norm test_bilingual test_ssml test_segments libcy_phonemize.so
	./test_golden $(CORE)
	./test_lts $(CORE)
	./test_norm $(CORE)
	./test_bilingual $(CORE)
	./test_ssml $(CORE)
	./test_segments $(CORE)

clean:
	rm -f *.o *.a *.so test_golden test_lts test_norm test_bilingual test_ssml test_segments

# The differential fuzzers are not part of `check`: they need Python and the built .so, and
# they are slower. They ARE the only gate that catches a Python/C divergence the frozen corpus
# does not cover -- which is exactly how d27543e's leading-zero divergence survived five
# commits with `check` green. CI calls this target; both scripts exit non-zero on mismatch.
#
# PYTHON ?= python3 is a TRAP on this project, not a safe default: the canonical interpreter
# is /usr/bin/python3.10 (Unicode 13), while a bare `python3` here can resolve to 3.14
# (Unicode 16). welsh_normalize._sep_after_spelled_digits and friends call str.isalpha(),
# which reads the HOST interpreter's live Unicode tables -- so `make fuzz` under the wrong
# python can report mismatches that are Unicode-version artefacts, not real Python/C logic
# divergences. Always run this target with PYTHON=/usr/bin/python3.10 explicitly; the ?=
# default below is left as a generic fallback for environments without that exact path, not
# an endorsement of whatever `python3` happens to mean locally.
PYTHON ?= python3
fuzz: libcy_phonemize.so
	cd ../../.. && $(PYTHON) tests/diff_fuzz_c_parity.py
	cd ../../.. && $(PYTHON) tests/diff_fuzz_edge.py

.PHONY: check clean fuzz
