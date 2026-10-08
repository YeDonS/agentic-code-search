# Handoff

## Objective

Complete real LLM root-cause diagnosis and patch evaluation for the existing 100 historical
issues, improve the implementation, and publish evidence with English/Chinese documentation.

## Scope

- Changed: only this separate `agentic-code-search` repository on `feat/real-model-evaluation`.
- Added: local-login Codex LangChain adapter, tool isolation, model-access diagnostics,
  safe patch applicability checks, parallel/resumable inference, automated review,
  pinned official-harness scripts and GitHub Actions workflow.
- Preserved: original historical task selection, gold isolation, retrieval baseline,
  original synthetic demo, adjacent `xhs-vault-main` project and all private data.
- Credentials remain with the CLI. No auth files, API keys, private source, model reasoning,
  or full source snapshots are published.

## Evidence

- 73 tests passed locally on Python 3.12; Ruff lint and formatting passed.
- Real CLI readiness and historical three-issue pilot succeeded.
- Pilot: 3 diagnosed, 3 localization hits, 3 applicable patches, 14 model calls,
  127,195 input tokens, 3,107 output tokens, zero observed built-in tool calls.
- Exploratory pilot used automatic WebSocket fallback (56 reconnect events). A separate
  HTTPS probe succeeded without reconnects; the fixed 100-task run uses HTTPS.
- Full run: ignored `runs/model-100-20261008`; manifest freezes model, settings, source
  digest, dataset/task hash, environment, CLI version, and worker count. Results pending.
- Published pilot evidence: `reports/model-pilot-3/`; source excerpts are excluded.
- Original retrieval results remain at `reports/retrieval-100/`.

## Review Notes

- Reviewed native tool protocol, absence of built-in CLI tools, no actor checkout in model
  working directory, no raw credential access, usage accounting, and process-group timeout.
- Rejected built-in activity, unavailable application tools, malformed arguments, and
  incomplete model turns. Provider errors are safe to log and do not reveal raw stderr.
- Patch checks use isolated copies to avoid Git subdirectory filtering, enforce read-file
  path membership, and leave the checkout untouched. Applicability is not test resolution.
- Parallel results are persisted after each issue, sorted at completion, and duplicate or
  configuration-mismatched resumption is rejected.
- Official harness is pinned to 5.0.2 and verifies the upstream parquet checksum.
  Image digests are captured; empty patches, infrastructure errors, and missing outcomes
  stay in the full denominator. No model credentials enter GitHub Actions.
- Residual risks: model alias drift, public-benchmark training contamination, same-model
  automated-review bias, and dependency/image/network failures during official tests.
- Human root-cause accuracy remains null without complete human adjudication.

## Next Step

Finish the frozen 100-task inference, export its predictions, run official Docker evaluation,
compare frozen causes with maintainer fixes using labeled automated review, and publish
all measured scores, failed cases, logs and validation evidence. Update both READMEs and
resume/interview guidance from actual final results. Do not alter source during the frozen run.
