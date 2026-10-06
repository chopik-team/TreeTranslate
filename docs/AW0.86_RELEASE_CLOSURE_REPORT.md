# AW0.86 — release closure

Consolidation preserves existing best known production. No new algorithm, optimization, quality patch, PDF failure repair, model change, benchmark run or Windows installer was added. Only version markers and release/documentation/evidence metadata changed after the initial production snapshot.

| Item | Status |
|---|---|
| Production frozen | PASS — 466-file snapshot; only two version marker changes |
| Version AW0.86 | PASS — constant + language-support presentation version |
| Changelog complete | PASS — historical milestones 0.81–0.85; no invented Git tags |
| Benchmark history complete | PASS — same100 official reference; samples not conflated |
| Known issues complete | PASS — 17 validation + 6 structure + 1 model failure retained |
| Research archived | PASS — inactive NMT prototype, 994 captured inputs, exact-output rejection |
| README updated | PASS — current technical alpha; original README preserved as history |
| Tests | PASS — **1278 passed, 0 failed/errors/skipped**, 614,25 s; first attempt preserved |
| Compile | PASS — compileall including final metadata/release tools |
| Diff check | PASS — working and staged git diff --check |
| Repo hygiene | PASS — candidate content ~79 MB rather than ~3.12 GB; useful tracked font retained |
| Freeze receipt | PASS — production SHA, 49 DB hashes, model/sample references and fresh full-suite result |
| Git commit | PASS — `10bbc50`; one closing commit |
| Git tag | PASS — annotated AW0.86; no retroactive 0.81–0.85 tags |
| GitHub push | PASS — closing branch + tag pushed atomically |
| GitHub Release | PASS — [technical prerelease](https://github.com/chopik-team/TreeTranslate/releases/tag/AW0.86), 655459-byte evidence ZIP |
| AW0.9 branch | PASS — codex/aw0.9; AW0.9-dev markers and transition metadata only |
| AW0.9 scope | PASS — preliminary MUST/SHOULD/MAY/NOT NOW; no tasks executed |

The closing source commit necessarily precedes its tag/publication and cannot contain its own SHA. Post-publication identities are bound in the external finalization receipt and this development-cycle transition metadata. The immutable AW0.86 tag was not amended. Its source report records the pre-publication preparation state; the release finalization assets record actual completion.

Historical restored NMT suite: **1269 PASS**. Closing suite includes nine previously added ETA cases (1278 collected). First attempt: 1276 passed / 2 failed; one was the missed presentation version field, corrected as permitted metadata. GPU UI smoke exceeded its existing 30-second limit; standalone rerun passed without changing runtime or timeout. Both failed checks separately passed. The complete retry passed **1278/1278**, with unchanged production hashes.

Benchmark: **same100 79,73 → 23,81 min, 3,35×, −70,14% wall**, 76 translated / 24 preserved / 0 fatal. [Performance](PERFORMANCE_AW0.86.md). NMT experiment savings are not claimed as production performance.

Decision: existing `codex/*` branch convention is retained, so the next branch is `codex/aw0.9`. No production architecture/UI redesign was made. The previously accepted UI and ETA work remains part of this freeze. Large QA trees are ignored but kept locally; compact evidence and exact regression fixture paths are retained. No tracked evidence deletion or history rewrite. Seventeen exact duplicate render copies are local-only. Narrow gitattributes preserve upstream notices/forensic output bytes; six QA/helper/note whitespace cleanups preserve Python AST and do not touch production.

[Freeze receipt](AW0.86_FREEZE_RECEIPT.md), [release notes](releases/AW0.86.md), [known issues](KNOWN_ISSUES.md), [AW0.9 preliminary scope](AW0.9_SCOPE.md).

Final stop: consolidation, publication and development-cycle opening complete; no AW0.9 feature work started.
