# Vendored upstream sources for the Welsh emoji table

These files are **build-time inputs only** — nothing here is shipped in a binary. They exist
so that `scripts/gen_emoji_cy.py` is reproducible offline and so the provenance of
`../emoji_cy.tsv` is auditable.

## Why they are vendored at all

The previous `emoji_cy.tsv` was extracted from **espeak-ng's `cy` voice**, which is
**GPLv3**. That was stated outright in `welsh_normalize.py` ("the ONLY hand-written entries
in an otherwise extracted table"), and the derived table compiled into every shipped
artifact — Android, iOS, Linux, Windows — against this project's own rule of shipping no GPL
components. The table was regenerated from scratch from the two permissively-licensed
upstreams below, with no espeak-ng input of any kind.

| File | Upstream | Version | Licence |
|---|---|---|---|
| `emoji-test.txt` | <https://unicode.org/Public/emoji/latest/emoji-test.txt> | 17.0 | Unicode terms of use — <https://www.unicode.org/terms_of_use.html> |
| `cldr-annotations-cy.xml` | `unicode-org/cldr` `common/annotations/cy.xml` | `release-48-2` | `Unicode-3.0` (declared in the file) |
| `cldr-annotationsDerived-cy.xml` | `unicode-org/cldr` `common/annotationsDerived/cy.xml` | `release-48-2` | `Unicode-3.0` (declared in the file) |

Both licences permit redistribution and modification with attribution. The attribution
lives in `../../../../NOTICE`.

## Refreshing

Re-download the three files at a newer version, then:

    /Library/Frameworks/Python.framework/Versions/3.10/bin/python3.10 scripts/gen_emoji_cy.py
    <canonical python3.10> scripts/emit_c_data.py

`gen_emoji_cy.py --report` prints what changed without writing. Note that `emoji_cy.tsv` is
**not** hashed into `data_version` (see `BangorG2P._compute_data_version`, which covers only
the emission policy, the id map and the dictionary files), so refreshing the emoji table does
**not** invalidate a trained model or require a model-config bump.
