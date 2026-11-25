# P0 — tasks

- [x] T1 `findmnt -T /srv/workdata` → ext4, UUID matches (R1)
- [x] T2 Read `PACKAGE.md` once; copy package without `KIRO_START_PROMPT.md` and `PACKAGE.md` (R2)
- [x] T3 `diff -r` source vs repo: only the two excluded files differ (R2)
- [x] T4 `sha256sum -c MANIFEST.sha256` (R3)
- [x] T5 Read HANDOFF, GAME_RULES, interface spec, steering (schema is checked through the validator)
- [x] T6 Create venv outside the repo, install pytest, jsonschema, playwright 1.64.1 (R9)
- [x] T7 `.gitignore`, `.gitattributes`, `pyproject.toml`, scripts (R8, R9)
- [x] T8 Manifest + validator + hygiene tests (R4, R5, R10)
- [x] T9 Static `#demo` test; run it once to completion (R6)
- [x] T10 `tech.md`, README with ports and disclosure (R11, R12, R13)
- [ ] T11 `git init`, first commit, private GitHub repo, push (R7)
- [ ] T12 Clean-clone check: clone the remote to a temp dir, run `sha256sum -c` and the fast tests
- [ ] T13 Report to the owner and wait
