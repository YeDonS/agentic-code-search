# Interview walkthrough / 面试讲解

These answers describe measured behavior. File localization, automated causal comparison,
human accuracy, and official functional resolution have distinct meanings.

## 1. How did routing choose an agent?

I used a deterministic LangGraph supervisor over observable state. Every issue starts with
code search. Missing source evidence permits another search pass. With source evidence and
execution enabled, the test specialist selects a narrow existing test and reads its output.
A real assertion failure permits another search pass using that evidence. Synthesis follows
when evidence is ready or the investigation budget is reached. No source or an explicit
model abstention yields insufficient evidence. Models choose tools within each role; the
supervisor chooses role transitions.

Each role has its own prompt, context, and tool allowlist. The roles execute sequentially
within an issue; the benchmark can run separate issues concurrently. All three can share a
model. See [`choose_route`](../src/code_assistant/workflow.py).

**中文：** 路由依据源码证据、是否尝试过测试、真实测试状态及预算，具有明确原因日志。
模型决定搜索词、读取文件和测试目标。真实模型在可信示例中实际走过“搜索 → 测试 →
再搜索 → 综合”。100 条历史推理采用源码取证，官方隐藏测试在预测冻结后单独执行。

## 2. What did the 100-issue benchmark look like?

I pinned SWE-bench Lite revision `b0dde1093fe417d83b7184254edf8199c1f0dff5` and selected
100 historical issue/merged-PR pairs from 12 repositories. A seed-2026 hash ranks issues
within each repository; sorted-repository round robin gives broad coverage. Selection never
uses predictions or outcomes. Actors see the report and the exact pre-fix snapshot, without
Git history, reference patches, or hidden tests.

The deterministic retrieval baseline scored Hit@1 40%, Hit@5 71%, and MRR@5 0.5202. The
real `gpt-6.1-sol` run completed all 100 tasks with 90 cited diagnoses and 10 abstentions:
file Hit@1 87%, Hit@5 88%, MRR@5 0.875. It used reasoning medium, five model turns per role,
18 application tool calls per issue, and six workers. These configurations have different
budgets, so this is not a controlled proof that multi-agent orchestration causes an improvement.

Post-freeze automated comparison with maintainer patches judged 87 correct, 1 partial,
2 incorrect, and 10 unscorable. That is **87% automated agreement**, with same-model bias;
complete named human adjudication has not occurred. Functional repair is separately tested
with official `swebench==5.0.2`, original hidden tests, pinned data, and recorded image digests.
The official result is **48/100 resolved**: 23 unresolved, 27 empty patches, and
2 test timeouts. Every case remains in the denominator. See [results](../reports/README.md).

**中文：** 已真实完成 100 条模型运行。文件定位 88%、自动根因核对 87%、官方修复率
48% 是不同指标；人工根因准确率仍为空。官方测试接受等效修复，不要求与维护者补丁逐字相同。
公开历史问题可能进入模型训练集，因此不声称这是完全未见过的数据。

## 3. How did the agent gather evidence before a fix?

The real-model trusted checkout integration followed search, source reads, focused pytest,
log inspection, another search, and synthesis. The baseline actually produced **1 failed,
2 passed**. The model explained that `discount or 10` replaces explicit zero, cited registered
source/test IDs, and proposed an explicit `None` check. A separate temporary-copy check
applied that real model's suggestion and obtained **3 passed**. The original checkout remained
unchanged. A real HTTP check also completed all three roles: health 200, an unauthenticated
request 401, and an authenticated model request 200.
[HTTP evidence](../reports/real-model-api/validation.json).

Historical inference is source-only: search repository symbols/error text, read relevant
functions/callers, then synthesize a cited cause and candidate patch. An isolated-copy
applicability check mechanically recounts hunks and runs `git apply --check`. It withheld
17 invalid patches; 73 could be submitted. Official functional tests run afterward.
The original diagnostic response keeps `patch_verified=false`; subsequent official results
are separate immutable evidence. See [real-model integration](../reports/real-model-checkout/).

**中文：** 证据由真实工具产生，模型不能自行宣布测试通过。可信示例确实执行了测试；
历史基准在推理阶段读取修复前代码，随后在官方容器验证冻结补丁。出处校验能阻止虚构
引用，但不能证明因果解释，因此还需要根因复核和功能测试。

## 4. What did structured logs reveal?

Events capture role/route reasons, paired tool starts/ends, outcomes, duration, evidence
counts, test exit status, patch applicability, token usage, and snapshot hashes. Logs exclude
prompts, source bodies, credentials, and hidden reasoning. The real 100-task run recorded
**541 model responses and 844 paired application tool calls**, with zero unfinished traces.
There were 26 agent-step-limit events, 7 recoverable tool errors, 10 abstentions, and 17
withheld patches. No index truncation, invalid synthesis, or run crash was observed.

The exploratory three-task pilot exposed 56 WebSocket reconnect events. The frozen full
run used the verified HTTPS configuration and had zero reconnects and zero observed built-in
CLI tool calls. An automated review also caught a concrete causal mismatch in requests-2674:
the prediction targeted ConnectTimeoutError while the maintainer fix handled ClosedPoolError.
Successful source access therefore did not establish a correct diagnosis or working patch.

Official test failures and infrastructure errors are retained separately, with per-issue
reports and image/patch hashes. Human accuracy stays unmeasured; logging is evidence for
execution behavior, not a substitute for semantic adjudication. Use `code-assistant logs`
and the [published event audit](../reports/model-100/log-audit.json) for actual counts.

**中文：** 真实日志发现了连接重试、轮数上限、工具错误和补丁无法应用；自动复核还
发现了异常类型判断错误。对应配置、哈希、失败案例和测试结果均保留，可以逐条核对。
