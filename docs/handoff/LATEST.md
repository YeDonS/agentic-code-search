# Implementation and evaluation handoff

## Current work

[PR #4](https://github.com/YeDonS/agentic-code-search/pull/4) repairs patch generation,
adds controlled evaluation, and corrects the historical architecture/metric descriptions.
Changes are scoped to this repository. Original frozen predictions/results are unchanged.

Implemented: synthesis source reads; source-priority handoff context; at most two patch
corrections using applicability errors; preserved candidates/attempts and safe provider
error records; global model/tool call ceilings; a continuous-conversation control; regular
text-file creation/deletion with citation/path checks; CLI tests; reproducible experiment,
curation and context-replay commands. Correction failures preserve the existing diagnosis.

## Frozen evidence

| Study | Inference source | Outcome |
|---|---|---|
| Original 100 | `3dc26ac14fe7573bb84ef851262645353842ef58` | 48/100 official resolutions; all routes search → synthesis |
| Paired 20, three arms | `6b61f9a4ac9ac5b5420caf1eba7d3d503f33c9fb` | Single 11/20; routed recent/source both 10/20 |
| Repair development v1 | `6b61f9a4ac9ac5b5420caf1eba7d3d503f33c9fb` | 14/17 applicable, 9/17 resolved; 3 provider errors |
| Repair follow-up v2 | `0c39f8a24d04ac8b690ed6db83b1714a7edb7b65` | 17/17 applicable, 11/17 resolved; 6 functional failures |

Every study has its own manifest, source fingerprint/proof, predictions, events and official
outcomes. No best-of-runs pooling, task replacement or denominator exclusions occurred.
The paired plan predates inference, selects tasks without reading outcomes, disables repair
and tests in all arms, and shares ten model/eighteen tool call ceilings. Actual token use
differs; the single arm used fewer observed calls/reported tokens. No routed advantage is
established by this small exploratory study. Paired sources remained frozen while default
code received later error-handling/new-file boundary fixes.

The repair study is selected and uses extra inference after the original run. Its 11 successes
are not added to 48/100 as a new pass@1 result. No gold fix or official-test feedback was
provided to repair actors. Original diagnoses retain their historical limitations in the
frozen artifacts; the accompanying README identifies that scope. Current code clears stale
generated checker notices when rechecking a diagnosis.

All 94 new official outcomes (60 paired + two independent sets of 17 repairs) are complete,
hash-bound, and include durable reports/excerpts/image digests/raw-log hashes. Workflows:
`37848455841`, `37849298422`, `37850192309`, `37848457575`, `37849300774`.

## Context and judge findings

The original 100-ledger replay finds 39 windows exceeding 24 records, 13 partial source-loss
cases (nine abstentions), and no case losing all source. Source priority preserves distinct
source reads. In the live paired pilot, it eliminates source loss but does not increase
resolution: both routed arms solve exactly the same ten cases.

Automatic causal judgments remain archived audit data and are removed from headline claims.
Forty explanations labeled correct did not resolve, while requests-2674's original patch
resolved despite an incorrect explanation label. This is a cross-metric disagreement;
functional success does not prove every causal sentence. Human causal accuracy is unmeasured.

## Validation and reproduction

107 offline tests pass; source coverage is 84.9%, CLI coverage 72.2% (previously zero).
Ruff lint/format and wheel build pass. CI covers Python 3.11/3.12/3.13 and both Docker images.
Real traces exercise five synthesis source reads and 36 repair source reads. Applicability
checks never execute repository code; official functional testing follows freezing.

Use [experiment commands](../EXPERIMENTS.md), [published evidence](../../reports/README.md),
and [validation](../../reports/experiments/validation.json). New machines create a fresh
plan with the same selection seed/count; resumption rejects source/environment changes.
Do not overwrite original runs. GitHub artifacts retain raw logs for 30 days; curated
evidence is durable. Ignored `runs/` and `.cache/` hold local source/full run artifacts.

Provider APIs are the independent service/inference path; no live native-provider key was
available, so actual provider-API inference remains unverified. The optional CLI adapter
depends on account access/version and online model behavior. No credentials were copied
into CI or images. Frozen patch replay is independent of CLI/model access.

Remaining limits: no inference-time official-container test specialist; no complete
100-task/token-cost-matched architecture comparison; no human causal adjudication; public
training contamination and repository-subset distribution bias; unexplained provider errors
and the original two 600-second test timeouts. Local pytest is explicitly trusted execution
without an OS sandbox; disabled execution and the Docker runner remain available.

Review is a source/trace/hash self-review, not an independent human review. Publication uses
the Git Data API with exact local tree/commit verification; no force push or history rewrite.
