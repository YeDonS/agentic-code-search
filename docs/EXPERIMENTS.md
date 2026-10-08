# Controlled experiments / 对照实验

The frozen historical result remains **48/100**, from search → synthesis with tests disabled
during inference. Its BM25 reference, synthetic routing fixture and automated judge do not
establish a benefit from multiple agents. The following studies keep independent outputs.

## Paired architecture and evidence-window pilot

Before inference, `code-assistant experiment plan` freezes 20 tasks from the original 100,
ranked by SHA256(`controls:20261008:instance_id`). Selection does not read original success,
abstention, judge or patch labels. This is an exploratory subset, not a leaderboard result.
The plan, task IDs, source fingerprint, provider parameters and raw events are retained in
[`reports/experiments/paired-20`](../reports/experiments/paired-20/).

| Arm | Conversation | Handoff window | Patch repair |
|---|---|---|---|
| `routed_recent` | Search role → synthesis role | Last 24 records | Disabled |
| `routed_source` | Search role → synthesis role | Source reads, then test/log, then search | Disabled |
| `single` | One conversation with search/read tools and final JSON | Continuous tool history | Disabled |

All arms use the same model, reasoning effort, HTTPS transport, workers, snapshots and issue
text. Every task has ceilings of **10 model calls and 18 application tool calls**. The search
role reserves three model calls for synthesis; a single conversation may use all ten. Source
reads and output limits are shared. Synthesis may verify source in both routed arms. No arm
sees reference patches, hidden tests or automated judge labels during inference.

These are equal **call/tool budget ceilings**, not equal consumed tokens or monetary cost.
Tokens, cache counts, durations and actual calls are reported. Different conversation
lengths are a remaining cost confounder; results must not be described as token-cost matched.
The three arms run in declared order with one stochastic attempt each, without choosing the
best rerun. Provider drift and sampling variation remain possible.

The primary measure is official FAIL_TO_PASS/PASS_TO_PASS resolution divided by all 20 tasks.
Abstentions, invalid patches, errors and timeouts stay in the denominator. Secondary measures
are applicability, abstentions, actual costs and source evidence retained at synthesis.
`routed_source` vs `single` tests the conversation architecture; `routed_source` vs
`routed_recent` tests the window policy. A configuration comparison gate rejects unintended
differences. A tiny pilot can find regressions; it cannot establish population superiority.
The test specialist is disabled in every arm, so this study cannot support a three-agent claim.

```bash
uv run code-assistant experiment plan runs/paired-plan --model provider:model-id --count 20
uv run code-assistant experiment run runs/paired-plan routed_recent runs/paired/routed_recent
uv run code-assistant experiment run runs/paired-plan routed_source runs/paired/routed_source
uv run code-assistant experiment run runs/paired-plan single runs/paired/single
# Freeze/export each arm, evaluate via scripts/evaluate_patches.py, then place the
# hash-bound aggregate at <arm>/official-evaluation/results.json.
uv run code-assistant experiment summarize runs/paired runs/paired/comparison.json
```

The initial historical correlation was 10 abstentions among 39 tasks with more than 24
evidence records, versus 0 among 61 other tasks. Difficulty, search frequency and tool choices
are confounders. The mechanism check counts actually retained source reads; a favorable
correlation or a unit test alone is not evidence of better functional resolution.

## Post-hoc format repair of 17 withheld candidates

This study selects **all** original candidates marked invalid by the applicability checker,
without selecting by the automated judge or later test outcome. Its actor receives the
original issue, frozen diagnosis/candidate, reconstructed observations from the exact pre-fix
snapshot, and the `git apply --check` error. It may read source and request at most two repairs
within six model / eight tool calls. It receives no gold fix or official test feedback.

The original root cause and declared file scope remain fixed. The patch is checked on a copy;
all original/repaired candidates, errors and hashes are retained. Frozen repairs are then
graded in the official containers. The denominator is 17, including unrecovered candidates.
This is a selected, extra-budget **post-hoc repair study**, not pass@1, an independent full
100-task rerun, or an improvement attributable solely to formatting: a model may alter the
implementation despite the repair prompt. The original 48/100 is never overwritten.

The first development run (`repair-17-v1`, source commit `6b61f9a`) recovered 14 applicable
patches; three provider errors aborted correction. It is retained, rather than erased.
The follow-up (`repair-17-v2`, source commit `0c39f8a`) reruns **all 17** after preserving
diagnoses/attempts on provider errors and adding request/error counters. It uses the same
per-issue caps, but is a new stochastic run with additional total budget. Differences
between these runs cannot be attributed solely to exception handling, and their best
patches are never pooled into one score. The paired three-arm study continues to use its
original frozen `6b61f9a` implementation for every arm.

```bash
uv run python scripts/repair_withheld.py reports/model-100 runs/repair-17 \
  --model provider:model-id --workers 4
```

Reconstruction uses published source-read provenance and pinned source archives. The gold
directory and full reference parquet are never passed to repair actors. Official evaluation
uses the same pinned harness and 600-second test budget as the original evaluation.

## 中文说明

20 题在推理前按固定哈希选定，不按原成绩筛题。三组共享模型及每题 10 次模型、18 次
工具调用上限；比较“两步流程 / 单对话”与“最近 24 条 / 源码优先”两个因素。补丁重试
在这些对照中关闭，避免混入第三个变量。实际 token 消耗可以不同，必须同时报告，不能
宣传为同 token 成本对照。小样本只作探索，测试 agent 仍未参与，因此不能声称证明了
三 agent 优于单 agent。

17 题补救实验使用全部原无效补丁，给模型应用错误和修复前源码，最多重试两次，不反馈
标准答案或官方测试结果。它是额外预算的事后补救，单独报告可应用率和官方解决率，不能
加回原始 48/100 冒充原本的一次成功率。人工根因抽检仍未完成；自动评审只作审计。
