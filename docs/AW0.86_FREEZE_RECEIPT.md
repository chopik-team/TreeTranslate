# TreeTranslate AW0.86 — source freeze receipt

Date: 2026-10-06. Closing Git commit: **`10bbc50f023c106bf259330395110daacaceee57`**. [Published release](https://github.com/chopik-team/TreeTranslate/releases/tag/AW0.86). Version: **AW0.86**, technical alpha/source freeze. Immutable Git reference: annotated tag **`AW0.86`**; exact closing commit is resolved with `git rev-parse AW0.86^{commit}` and recorded in the release finalization asset. A commit cannot contain its own final SHA; the post-publication receipt binds that tag, commit and release URL without rewriting history.

## Production identity

Pre-closure base Git commit: `9aa36fc327463b5ef11d6d02e40a810207bd5e8f`, branch `codex/next-cycle`. This base commit alone does not include the previously developed uncommitted AW0.8x work.

Snapshot made before documentation edits: raw working production tree SHA256 **`0ddf2d9813453df0569a488272cce2e54386d77cd90f8f87a3bb5363accf7270`**, 466 files. [Per-file receipt](../qa/aw086/closure/production_before.json).

Frozen AW0.86 working production tree SHA256: **`ffba121652fdf05a0b51bf97742596559b177ae141cd0e6799e3b4cf3f4e88a5`**. Hash = SHA256 of sorted `relative-path + NUL + raw-file-SHA256 + newline` records. Scope: app/assets, root Python/package/build metadata and requirements, root vendor model/runtime JSON manifests; bytecode, SQLite sidecars and model weights excluded. Git text normalization may change line endings on another checkout; Git-normalized production tree SHA256: **`ad470299f36701d7f7acf5a52229e248cd63f1fa0bc7cc203477867f372c0fd0`**, independently computed from staged Git blobs and saved in [`git_production_blobs.json`](../qa/aw086/closure/git_production_blobs.json). Use this identity for a normalized checkout comparison.

Allowed changes during closure: only `APP_VERSION` in `app/config/constants.py` and the version field in `assets/language-support.json`. Language counts/history, data and all algorithms are unchanged. [Audit](../qa/aw086/closure/production_after.json).

Four NMT rollback files still match exact historical safe hashes: `job.py`, `run_metrics.py`, `runtime_manager.py`, `m2m100_backend.py`. The rejected scheduler is inactive and archived outside app. Later approved file-bar/ETA changes were present before this closure snapshot; the old global NMT hash is a historical proof, not the current whole-tree SHA.

## Test and static receipt

Historical safe restored baseline: **1269 passed, 0 failed/errors/skipped**, 338,38 s. Fresh closing full suite: **1278 passed, 0 failed, 0 errors, 0 skipped**, 614,25 s; command `python -X utf8 -m pytest -q --junitxml=qa/aw086/closure/full_pytest_final/junit.xml`. Production hashes before/after the suite are identical. [Result](../qa/aw086/closure/test_result.json). First attempt (1276 passed / 2 failed) is preserved separately; its metadata mismatch was corrected, GPU smoke retry passed without runtime/timeout changes. No failed counts were overwritten.

`compileall app tools tests main.py` PASS; `git diff --check` PASS before final staging. Existing `tools/verify_models.py`: **15 local model artifacts verified**, no model changes. Final staged diff/static checks are in the release audit.

## Data and model references

49 packaged Knowledge DB hashes match `assets/knowledge/manifest.json`; exact hashes are copied into `production_after.json`. Knowledge, glossary content and translation-memory semantics were not edited by consolidation.

Model references: `vendor/models/models_manifest.json`, `vendor/model-metadata/**`, OCR manifest. Weights are local and not distributed by this release. The large lexicon SQLite database also stays local; its SHA256/size and data/model manifest hashes are in [`external_data_refs.json`](../qa/aw086/closure/external_data_refs.json). Dependencies: existing pinned requirements and third-party notices; no package installation or model conversion was done for closure.

Full CN7C source SHA256: **`ecc0fd54bbc421af33febcb4f971e9a4735b15102aae9c451334a449c3a85330`**. 17 211 PDF. Source corpus and large translated ZIPs are excluded from Git/release. Source reference and sample CRC/size/indices/hashes: [same100 manifest](../qa/aw086/benchmarks/final100/run_manifest.json).

Official benchmark: already measured same100 `25825c3f75a7` → `736fc7a72805`, 4783,64 → 1428,60 s, 3,35×; 76 translated / 24 preserved / 0 fatal. No repeat benchmark/full-corpus run. [Performance](PERFORMANCE_AW0.86.md), [history](BENCHMARK_HISTORY.md), [reproducibility](BENCHMARK_REPRODUCIBILITY.md).

[Known issues](KNOWN_ISSUES.md), [rejected experiments](research/REJECTED_EXPERIMENTS.md), [closure status](AW0.86_RELEASE_CLOSURE_REPORT.md), [next scope](AW0.9_SCOPE.md). AW0.9 begins only after this freeze/release gate; no next-cycle feature work is performed here.

Transition metadata: `codex/aw0.9` opened after verified publication; `AW0.9-dev` changes only current development version markers. AW0.86 tag/source/evidence remain immutable.
