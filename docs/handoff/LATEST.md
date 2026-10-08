# Handoff

## Objective

Create a real GitHub project implementing the supplied developer-assistant description,
with English/Chinese READMEs and evidence-backed answers to four interview questions.

## Scope

- Changed: only this new `agentic-code-search` project: implementation, examples, tests,
  pinned historical task set, Docker/CI configuration, documentation and curated reports.
- Intentionally not changed: the adjacent `xhs-vault-main` project and its private data/output.
- Out of scope: fabricated model results, automatic patch application, public service hosting,
  model credentials, and claiming official SWE-bench leaderboard performance.
- Work was developed on `feat/initial-build`; the lead publishes the completed snapshot to main.

## Evidence

- Python 3.12: 55 behavioral/integration tests passed; Ruff checks and formatting passed.
- Offline demo: real baseline pytest output `1 failed, 2 passed`; separate temporary-copy
  regression test confirms the proposed example patch yields `3 passed`.
- Two complete 100-task retrieval runs: identical ranked predictions; Hit@1 0.40,
  Hit@5 0.71, MRR@5 0.5201667. No failed/missing runs.
- Each full run has 100 per-issue traces and 399 paired tool calls, with no incomplete
  runs, tool errors, empty searches, or truncated indexes.
- Dataset revision and hashes: `benchmarks/provenance.json`.
- Curated outputs: `reports/`; full local outputs: ignored `runs/` and `.cache/`.
- Package build succeeds; API and wheel smoke checks are recorded in `reports/validation.json`.
- Container and multi-version evidence is available from the repository's GitHub Actions CI.

## Review Notes

- Review covered path traversal, symlink access, shell argument injection, subprocess
  credentials, timeout termination, tool budgets, invented citations, abstention,
  score denominators, reviewer completeness, wheel data inclusion, and container boundaries.
- Corrected a zero-context demo diff to a context-bearing patch and verified it applies.
- Corrected upstream list/string test-ID compatibility and `.env` provider-key loading.
- Returned a tool response for every model-requested call, including calls over a batch limit.
- The historical actor root contains no `.git`, gold labels, or hidden test patch.
- Residual risk: real provider invocation is untested without credentials; citation validation
  does not prove causality; local pytest executes trusted code with host privileges;
  generic Docker runner requires project dependencies to be baked into a suitable image.

## Next Step

Configure a tool-capable model and provider key locally, run the three-issue pilot, freeze
model/settings/prompts, then run all 100. Complete causal review and run the official
SWE-bench regression harness before changing the unmeasured correctness fields or resume claims.
