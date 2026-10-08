# Handoff

## Objective and status

Completed real LLM diagnosis and official patch evaluation for the existing 100 historical
tasks, improved the implementation, and published English/Chinese evidence.

## Scope

- Only the separate `agentic-code-search` repository was changed. Core implementation
  merged in PR #1; final results/documentation use `feat/model-benchmark-results`.
- Added a local-login Codex LangChain adapter, tool isolation, safe model diagnostics,
  patch applicability checks, parallel/resumable inference, automated causal review,
  official harness scripts, frozen-batch export, and Linux evaluation workflow.
- Preserved the original task selection, gold isolation, retrieval baseline, and synthetic
  demo. The adjacent `xhs-vault-main` project and private data were outside scope.
- Credentials remain with the CLI. Authentication files, API keys, prompts, hidden
  reasoning, full source snapshots, and private repositories are excluded from publication.

## Frozen inference and measured results

- Inference source commit: `3dc26ac14fe7573bb84ef851262645353842ef58`.
- Source SHA-256: `d4e5b6d72a4d66ac37e10f45ae0c900d24a439de2ee2ff1d5c6ca68fd5f1ddf1`.
- Model: `codex-cli:gpt-6.1-sol`, reasoning medium, HTTPS, 6 workers,
  CLI `0.162.0-alpha.2`, five model turns per role, 18 tools per issue.
- 100 complete: 90 cited diagnoses, 10 abstentions. Hit@1 87%, Hit@5 88%, MRR@5 0.875.
- 541 model responses, 844 paired tools; 5,379,967 reported input tokens,
  124,958 output tokens, 939,008 cached input tokens. Zero built-in CLI tool calls,
  transport reconnects, run crashes, unpaired tools, or unfinished traces.
- 26 role step-limit events, 7 recoverable tool errors, 17 withheld patches; 73 submitted
  nonempty patches. Full inference wall time: 1,358.683187 seconds on the recorded host.
- Automated causal review: 87 correct, 1 partial, 2 incorrect, 10 unscorable.
  Human root-cause accuracy remains null; same-model judgment is explicitly labeled.
- Official `swebench==5.0.2`: **48/100 resolved**, 23 unresolved, 27 empty patches,
  2 test timeouts at 600 seconds, no missing outcomes or image-pull failures.
- Four frozen 25-task batches, workflow runs `37823468905`, `37823608201`,
  `37824041242`, `37824921353`. Exact patch hashes match the full predictions;
  actual image digests, official reports, excerpts and raw-log hashes are published.
- Separate pilot: 3/3 official resolutions, workflow `37822223997`. Excluded from full score.
- Two post-hoc maintainer-patch sanity controls resolved with the same recorded image
  digests, workflow `37827800765`. Incidental fixture/import errors still occurred but
  did not block required regressions. Original model failures and 48/100 remain unchanged.

## Validation and review

- 75 local tests passed on Python 3.12; Ruff lint/format passed for src/tests/scripts.
- Real model CLI integration performed search/test/search/synthesis; baseline 1 failed,
  2 passed, then independent application to a temporary copy produced 3 passed.
- Real FastAPI/model integration: health 200, missing bearer token 401, authenticated
  diagnosis 200, all three roles executed. Loopback HTTP clients bypass inherited proxies.
- CI validates Python 3.11/3.12/3.13 and both Docker images; see published CI evidence.
- Reviewed tool protocol, built-in activity rejection, actor-root isolation, safe provider
  errors, process timeouts, patch-path confinement, unchanged source snapshots, strict
  resumption, full-denominator aggregation, and absence of credentials in CI.
- Review was self-review with a fresh validation pass; no independent human review or
  orchestration ablation is claimed.

## Evidence and remaining limits

`reports/model-100/` holds predictions, causes/citation provenance, source proof, usage,
events, failure analysis, automated review, and official evaluation. Local complete logs
and source caches remain ignored under `runs/` and `.cache/`. GitHub raw evaluation
artifacts have 30-day retention; durable reports/excerpts/hashes are committed.

Residual limits: public-benchmark training contamination, model alias drift, same-model
review bias, 17 invalid candidates, 10 abstentions, and 2 unexplained test timeouts.
Any larger-budget, patch-correction, timeout, or single-agent comparison must use a new
manifest/output directory; do not rewrite the original predictions or score.

GitHub Git HTTPS transport was unavailable during publication. Git Data API publication
preserved and verified exact local commit/tree identities without force-pushing.
