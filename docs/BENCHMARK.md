# Historical benchmark / 历史评测

## Decision and scope

The real-model experiment asks whether the assistant identifies the causal mechanism in
real bug reports, as confirmed by merged maintainer fixes. The 100-task run is complete:
90 cited diagnoses, 10 abstentions, Hit@1 87%, Hit@5 88%. An explicitly automated causal
comparison scores 87 correct, 1 partial, 2 incorrect, and 10 unscorable. **Human-adjudicated
root-cause accuracy remains unmeasured.** Functional resolution is measured separately by
the pinned official harness: **48/100 resolved**, 23 unresolved, 27 empty patches,
2 test timeouts (600 seconds). See [published results](../reports/README.md).

The earlier completed experiment is a **deterministic file-localization baseline**. It checks data
preparation, snapshot isolation, search/read tools, scoring, and per-issue telemetry. It does
not test LLM reasoning or establish that multi-agent orchestration improves outcomes.

## Data and selection

- Source: [SWE-bench/SWE-bench_Lite](https://huggingface.co/datasets/SWE-bench/SWE-bench_Lite).
- Revision: `b0dde1093fe417d83b7184254edf8199c1f0dff5`; split: `test`; upstream rows: 300.
- Eligible: nonempty issue text, a base commit, and at least one non-test file in the maintainer patch.
  All 300 source rows meet these rules.
- Seed: 2026. Within each repository, rank by `SHA256(seed:instance_id)`; take sorted-repository
  round-robin entries until 100. This improves repository coverage rather than reproducing
  the upstream repository distribution. No selection depends on predictions or outcomes.
- The selected 100 span 12 repositories. Counts, hashes, and creation time are in
  [`provenance.json`](../benchmarks/provenance.json).
- `instance_id` ends in a **solution PR number**, not necessarily the original issue number.
  `maintainer_fix_url` correctly links to `/pull/<number>`.

[`tasks.jsonl`](../benchmarks/tasks.jsonl) contains actor inputs. Separate
[`gold/reference.jsonl`](../benchmarks/gold/reference.jsonl) contains changed-file labels,
test IDs, and patch hashes. Full patches remain in the upstream cached parquet and can be
exported for reviewers after predictions are frozen:

```bash
uv run code-assistant benchmark reference astropy__astropy-12907 runs/review/astropy-reference.json
```

No manual verification of every upstream PR or semantic diagnosis is claimed. The maintainer
reference relationship comes from SWE-bench's issue/merged-PR pairing. Human evaluation must
inspect the actual fix and test context; file overlap alone is an inadequate root-cause label.

## Actor isolation and reproducibility

Every issue uses the GitHub archive at its exact `base_commit`. Extraction rejects parent
paths, absolute paths, and links, and caps expanded size and member count. There is no `.git`
directory. Only that snapshot is passed to repository tools. Gold labels, full reference patches,
and hidden tests are outside the actor's root. The actor has no network-search or history tool.

Issue text can naturally contain suggested solutions, and public historical bugs may appear
in a model's training data. Snapshot isolation reduces tool-based leakage; it cannot eliminate
training contamination or guidance already present in the original report. This subset is
not an official SWE-bench leaderboard submission.

The manifest records ordered task IDs, task hash, seed, mode, model identifier, budgets,
Python/platform/package versions, and a SHA-256 of implementation files. Each trace records
the source archive hash. Original archives are cached locally and never committed. New runs
must use a new output directory so previous evidence is preserved.

## Completed retrieval baseline

One query uses the 35 most frequent tokenized issue terms. BM25 ranks source documents with
filename terms weighted three times. Of the top ten hits, test files are removed and the first
five distinct remaining files become predictions. Up to three are read for evidence. No gold
paths influence queries, filtering, ranking, or file reads. Historical tests are not executed
by this diagnostic runner.

| Metric | Definition | Result |
|---|---|---:|
| Hit@1 | First candidate is a maintainer-changed non-test file | 40 / 100 |
| Hit@5 | Any of up to five candidates matches such a file | 71 / 100 |
| MRR@5 | Mean reciprocal rank of first matching file, else zero | 0.5201667 |
| Changed-file recall@5 | Mean fraction of reference files retrieved | 0.71 |
| Failed/missing runs | Kept in the denominator | 0 / 100 |
| Root-cause accuracy | Requires complete causal review | Unmeasured |
| Patch resolution | Requires official regression execution | Unmeasured |

The cached reproduction produced the same ranked file predictions. Per-issue results,
raw durations, trace conservation checks, and manifests are published in [reports](../reports/README.md).

## Model evaluation and causal rubric

First run three pilot issues for environment/protocol debugging, then freeze the model,
prompts, tools, budgets, and code before the 100-issue run. A full run requires a provider
key or supported local CLI login and consumes that account's allowance. Record token usage when supplied;
unknown usage stays null. Do not alter the task set after viewing results.

```bash
uv run code-assistant benchmark run runs/model-pilot --mode model --limit 3
uv run code-assistant benchmark run runs/model-100 --mode model
uv run code-assistant benchmark export runs/model-100/predictions.jsonl runs/model-100/swebench.jsonl
```

The export also creates `swebench.review.csv`. Review against the merged fix and relevant
tests, with a named reviewer and rationale for every decision:

| Verdict | Criteria | Binary accuracy credit |
|---|---|---:|
| `correct` | Identifies causal condition, mechanism, and responsible source behavior consistent with the maintainer fix | 1 |
| `partial` | Related symptom/file identified but a necessary causal step is missing | 0 |
| `incorrect` | Wrong mechanism, contradicted by source/fix, or an unsupported confident claim | 0 |
| `unscorable` | Reference ambiguity, missing diagnosis, or failed environment prevents assessment | 0 |

A second reviewer should independently review ambiguous cases and adjudicate disagreements.
Record reviewer IDs, rationale, and disagreements. Do not use the agent's own confidence as
ground truth. The scorer leaves aggregate root-cause accuracy null until all expected issues
have explicit judgments; once complete, the denominator remains 100, including failures.

```bash
uv run code-assistant benchmark score runs/model-100/predictions.jsonl runs/model-100/reviewed-scores.json \
  --reviews runs/model-100/swebench.review.csv
```

For a future single-agent comparison, hold task IDs, snapshots, model version, evidence limits,
and total model/tool budget constant. Vary only orchestration. No such ablation has been run.
Raw outcomes and latency distributions must accompany any comparison; do not infer causal
benefits from the retrieval baseline versus an LLM treatment.

## Official patch evaluation

The runnable evaluation path is [MODEL_EVALUATION.md](MODEL_EVALUATION.md), pinned to
`swebench==5.0.2`. The 100 inference outputs are also frozen in four consecutive 25-task
batches so Docker tests can overlap later inference. Batch selection follows the original
task order and includes abstentions and invalid patches; no outcome-based filtering is used.
Every nonempty evaluated patch has a SHA-256 checked against the final predictions. The
four batch denominators sum to 100. The original dataset checksum and actual image digests
are retained. The full run resolved 48/100; 23 nonempty patches failed tests, 27 predictions
had empty patches, and 2 tests timed out. There are no missing outcomes or image-pull failures.
The three-task pilot separately resolved all three cases; it does not enlarge the denominator.

Two post-hoc maintainer-patch controls also passed official required regressions with the
same image digests, despite incidental fixture/import errors in the larger test output.
Those errors alone therefore do not justify excluding the original model failures.
[Control evidence](../reports/evaluation-controls/README.md). The agent score remains 48/100.

Use a separate environment with a recorded, pinned SWE-bench harness version and working Docker.
Export the **same pinned source records** for official evaluation, instead of silently loading
whatever the upstream `main` revision becomes:

```bash
uv run python - <<'PY'
from pathlib import Path
import json
import pyarrow.parquet as pq
from code_assistant.benchmark import REVISION, read_jsonl
ids = {t['instance_id'] for t in read_jsonl(Path('benchmarks/tasks.jsonl'))}
rows = pq.read_table(Path('.cache') / f'swebench-lite-{REVISION}.parquet').to_pylist()
Path('runs/eval-tasks.jsonl').write_text(''.join(json.dumps(r) + '\n' for r in rows if r['instance_id'] in ids))
PY
# With the official swebench package installed in your evaluation environment:
python -m swebench.harness.run_evaluation \
  --dataset_name runs/eval-tasks.jsonl \
  --predictions_path runs/model-100/swebench.jsonl \
  --max_workers 2 --run_id model-100
```

The upstream [loader supports local JSONL](https://github.com/SWE-bench/SWE-bench/blob/main/swebench/harness/utils.py).
Follow the [official evaluation guide](https://www.swebench.com/SWE-bench/guides/evaluation/)
for platform/image compatibility, environment setup, and report locations. This repository's
test-runner image is not a substitute for upstream per-instance environments.

Import the official JSON report, which contains `resolved_ids`:

```bash
uv run code-assistant benchmark score runs/model-100/predictions.jsonl runs/model-100/final-scores.json \
  --reviews runs/model-100/swebench.review.csv --harness-report /path/to/official-report.json
```

The scorer rejects unknown resolved IDs and resolution claims for empty submitted patches.
Patch resolution is `resolved / 100`; missing patches and infrastructure failures count as
unresolved and must also be reported separately. Exact textual equality with the gold diff
is not used: multiple fixes can be valid. Preserve official logs, harness version, report hash,
and selected dataset hash before making a patch-correctness claim.

## 中文说明

已完成 100 条历史问题的检索基线和真实模型运行。真实模型给出 90 条带证据诊断，
10 条主动判断证据不足；文件 Hit@1 为 87%，Hit@5 为 88%。固定数据版本、2026 种子和
按仓库轮转的选样规则均可核验，12 个仓库全部有覆盖。

agent 只能访问修复前快照，参考补丁和隐藏测试放在外部；但公开历史问题可能存在训练
污染，因此不能宣称完全不存在泄漏。文件命中率与因果正确性严格区分。

人工根因评分要求说明触发条件、错误机制及责任代码，并与维护者补丁一致；相关文件命中
但解释不全只能算部分正确。每条需要复核人和理由，全部复核后才生成根因正确率。
自动评审已对照维护者补丁产生 87 条正确、1 条部分正确、2 条错误及 10 条不可评分；
这不是人工准确率。官方 SWE-bench 环境确认 **48/100** 修复；23 条未通过、27 条空补丁、
2 条超时均保留在分母中，逐条报告、日志摘录与哈希已发布。100 条推理阶段关闭历史
仓库测试执行，专职测试 agent 已在真实模型的可信
示例中实际运行；官方隐藏测试仅在预测冻结后执行。
