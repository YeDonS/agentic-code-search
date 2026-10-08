# Real-model evaluation / 真实模型评测

The completed 100-task run produced 90 cited diagnoses and 10 abstentions, file Hit@1 87%,
Hit@5 88%, and MRR@5 0.875. Automated judgments are retained as audit data rather than
headline correctness. There are 73 applicable patches and 17 withheld
candidates. Official tests resolved **48/100**: 23 unresolved, 27 empty patches, and
2 test timeouts at the fixed 600-second limit. All failures remain in the denominator.
[Per-issue official results](../reports/model-100/official-evaluation/results.json) ·
[Failure analysis](FAILURE_ANALYSIS.md) · [Evidence index](../reports/README.md).

The fixed 100-task actor run uses `codex-cli:gpt-6.1-sol`, reasoning `medium`, HTTPS
transport, six workers, and the budgets recorded in its manifest. Codex CLI
`0.162.0-alpha.2` reuses its own local ChatGPT login. It does not require exporting
an API key, and its authentication files are never copied into this repository or CI.

Every original route was **code_search → synthesis**. The test specialist was disabled
throughout inference, with official testing afterward. This result does not measure a
three-agent architecture or establish an advantage over a single agent. The current code
has new context/repair behavior and therefore produces a **new experiment**, not an exact
re-execution of the old configuration. [Paired and repair studies](EXPERIMENTS.md).

固定 100 条任务使用上述模型及配置。模型仅收到问题描述、修复前代码工具返回值；
临时仓库没有 Git 历史、维护者补丁或隐藏测试。模型运行时使用空目录，内置工具关闭。
每次调用检查 CLI 事件，遇到内置命令、文件操作、联网搜索或连接器调用立即判为失败。

## Independent inference with provider APIs

The portable path uses `ASSISTANT_MODEL=openai:<model-id>` with `OPENAI_API_KEY`, or
`anthropic:<model-id>` with `ANTHROPIC_API_KEY`. These use native LangChain adapters and do
not depend on Codex flags, subscription login or an account-specific alias. Select a
tool-capable model and freeze its identifier, provider/library versions and budgets.
`doctor` checks configuration only. This environment had no provider API credentials, so
native-provider setup is covered offline but live API inference remains unverified.

```bash
cp .env.example .env  # configure provider:model-id and its API key
uv run code-assistant doctor
uv run code-assistant benchmark run runs/provider-pilot --mode model --limit 3
```

Changing model/provider cannot reproduce the original model's score. Source excerpts are
sent to the configured provider; do not place keys in public commands, reports or images.

## Historical CLI inference configuration

To attempt the **original** inference protocol, use a separate checkout of source commit
`3dc26ac14fe7573bb84ef851262645353842ef58`, its lockfile, and the original
[manifest](../reports/model-100/manifest.json). Its settings were five calls per role,
18 tools, two search passes, disabled tests, and no model patch-repair loop. Do not run the
current defaults and label them the same experiment. The original CLI binary/model alias
may not be available to another account; online sampling/server drift prevents a promise
of identical generations even with that source and configuration.

The commands below run **new** inference with the current implementation:

```bash
uv sync --locked --all-extras
codex login
export ASSISTANT_MODEL=codex-cli:gpt-6.1-sol
export ASSISTANT_CODEX_REASONING_EFFORT=medium
export ASSISTANT_CODEX_TRANSPORT=https
uv run code-assistant doctor
uv run code-assistant benchmark run runs/new-pilot --mode model --limit 3 --workers 2
uv run code-assistant benchmark run runs/new-model-100 --mode model --workers 6
uv run code-assistant benchmark export runs/new-model-100/predictions.jsonl runs/new-model-100/swebench-predictions.jsonl --model-name agentic-code-search-gpt-6.1-sol
```

`--resume` only accepts the same tasks, source digest, environment, model settings,
and worker count. Completed predictions remain fixed. Use a new directory for any
configuration change. Model inference consumes the signed-in account's allowance.

## Evaluate patches with the official harness

Inference and evaluation are separate. A source-only applicability check may mechanically
recount unified-diff hunk lengths, then runs `git apply --check` against a temporary copy.
It changes no source and executes no repository code. Invalid/unread-path patches are withheld.
The original candidate and both hashes remain in ignored local run artifacts; the
17 withheld historical candidates are also published in
[withheld-patches.jsonl](../reports/model-100/withheld-patches.jsonl).
Applicability does **not** establish functional correctness.

Current code retains the checker error and can request at most two pre-evaluation repairs
with `read_file` access, inside a shared model/tool call budget. `patch-attempts.json` records
each candidate and audit. Set `ASSISTANT_PATCH_REPAIR_ATTEMPTS=0` to disable this treatment.
The original frozen candidates were never repaired in place.

模型补丁冻结后，用官方 `swebench==5.0.2`、原始评测脚本及 FAIL_TO_PASS/PASS_TO_PASS
标签在 Linux Docker 中运行。每个官方镜像在拉取后记录实际 digest，逐个执行并清理，
避免百条任务占满磁盘。空补丁、失败、超时和环境错误仍保留在总分母中。

On a disposable Linux Docker host:

```bash
uv sync --locked --extra benchmark
uv pip install 'swebench==5.0.2'
uv run --no-sync python scripts/evaluate_patches.py runs/new-model-100/swebench-predictions.jsonl runs/official-patches
uv run python scripts/aggregate_patch_results.py runs/new-model-100/swebench-predictions.jsonl runs/official-patches runs/official-results.json
uv run code-assistant benchmark score runs/new-model-100/predictions.jsonl runs/new-model-100/final-scores.json --harness-report runs/official-results.json
```

The **Official patch evaluation** GitHub Actions workflow runs the same script in shards.
It takes a frozen predictions path under `reports/`. No model login or API secrets are needed.
The pinned parquet checksum is verified before any official test script is used.
Harness reports, test output, image digests, and errors are retained as run artifacts.

For this run, four consecutive 25-task batches let official tests overlap later inference.
`scripts/freeze_batch.py` freezes only completed newline-terminated records, preserves the
original task order, and records the parent manifest hash. The final aggregator checks each
evaluated patch hash against the full 100 predictions and rejects duplicate/missing outcomes.
Every empty patch and infrastructure error remains in the denominator.

## Root-cause review

```bash
uv run code-assistant benchmark review runs/new-model-100/predictions.jsonl runs/automated-review --workers 4
```

This compares frozen explanations with maintainer patches using an explicitly labeled
LLM reviewer. The reviewer has access to gold **after** actor predictions are frozen;
actor runs never receive it. `automated_root_cause_match_rate` is an automated agreement
measure and may have same-model bias. It never fills `root_cause_accuracy`, which requires
complete named human review. Official patch resolution is a separate functional metric.

自动评审不能冒充人工评审，也不能证明补丁通过测试。公开历史问题可能进入模型的训练
数据；本项目控制运行时答案泄漏，无法证明训练集无污染。在线模型的别名、服务端版本、
采样及依赖镜像可能变化，需保留本次清单、预测文件哈希和镜像 digest。

The original trace audit records 26 five-turn role limits and 10 abstentions. Current defaults
allow seven calls per role, reserve a final-answer turn, and cap the whole run at 18 model
calls. The controlled experiment sets its own fixed ten-call budget and disables repairs.
Neither a higher cap nor a passing unit test proves better resolution.
Local HTTP validation bypasses environment proxies for loopback (`curl --noproxy 127.0.0.1`
or an HTTPX client with `trust_env=False`), after an inherited proxy intercepted the smoke test.

The optional CLI adapter is a local research client, not the required service backend.
Use provider API credentials for independent services and check applicable
[account terms](https://openai.com/policies/terms-of-use/) and supported use before deploying
subscription authentication. No legal or eligibility conclusion is claimed here.

Primary references: [Codex non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode),
[Codex provider configuration](https://learn.chatgpt.com/docs/config-file/config-reference),
[SWE-bench official evaluation guide](https://www.swebench.com/SWE-bench/guides/evaluation/).
