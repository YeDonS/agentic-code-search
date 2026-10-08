# Interview walkthrough / 面试讲解

These answers describe this repository's actual implementation and evidence. They do not
claim a real-model 100-issue experiment or maintainer-level semantic accuracy that has not run.

## 1. How did routing choose an agent?

I used a deterministic LangGraph supervisor over observable state. It sends every new issue
to code search. If source evidence is missing, search can refine once. With source evidence
and execution enabled, it invokes the test specialist. A real assertion failure allows one
additional search pass using the failure log. It then invokes synthesis, or returns insufficient
evidence if no source was read. A global tool budget overrides further investigation.

The model decides searches, files, and test targets inside each specialist's allowed tools.
The supervisor decides specialist transitions. Separate prompts and tool lists provide role
boundaries even when all three roles share one model. This is sequential orchestration.

**中文：** 我把角色路由做成可审计的状态规则，依据是否读到源码、是否执行过测试、
真实退出状态和剩余预算判断下一步。模型决定角色内部用什么搜索词、读什么文件、运行
哪个测试，但不能增加权限。对应 [`choose_route`](../src/code_assistant/workflow.py)。

## 2. What did the 100-issue benchmark look like?

I pinned a SWE-bench Lite dataset revision and selected 100 historical issue/merged-PR pairs
across 12 repositories. A seeded hash ranks issues within each repository; round-robin
selection improves coverage and does not depend on results. Each issue has a base commit,
the original report, a solution PR URL, and separately stored maintainer reference labels.

I completed a deterministic retrieval baseline on all 100 pre-fix snapshots: Hit@1 was 40%,
Hit@5 was 71%, and MRR@5 was 0.5202. These are file-localization metrics. Real-model causal
accuracy remains unmeasured. The implemented review workflow requires a causal explanation
matching the maintainer fix, with reviewer/rationale fields for all 100 cases; official patch
resolution requires SWE-bench tests. Failures remain in the denominator.

**中文：** 真实做过的是固定版本的 100 条文件定位评测。不能把 71% 写成 bug 修复率，
也不能声称已经跑过 100 条大模型诊断。根因正确性由人工对照维护者修复判定，补丁效果
由官方回归测试判定。见[协议](BENCHMARK.md)和[运行证据](../reports/README.md)。

## 3. How did the agent gather evidence before a fix?

The runnable synthetic example follows this actual sequence:

1. `search_repository("calculate_total discount")` finds source and related tests.
2. `read_file("checkout.py")` registers the function body and line numbers.
3. `run_tests(["tests/test_checkout.py"])` produces a real result: 1 failed, 2 passed.
4. `inspect_logs("test-1")` reads the assertion showing `90.0` instead of `100`.
5. Code search reads the source again with the failed-test context.
6. Synthesis cites source/test evidence, explains why `discount or 10` replaces zero,
   and proposes an explicit `None` check.

The demo's choices are scripted, while search, reads, tests, and logs are real. In model mode,
native LangChain tool calls choose the sequence within the same boundaries. The service never
applies the patch. A separate regression test applies the demo suggestion to a temporary copy
and confirms 3 passed.

**中文：** 先定位、读函数，再运行最小测试，读取真实断言错误，回到源码核对机制，
最后给出引用和建议。演示的模型选择是固定脚本，不能说成大模型自主推理；真实模型
接入走相同工具协议，尚未进行在线调用。源码引用校验也不能替代正确性评测。

## 4. What did the structured logs reveal?

Each run records start/end, routing reason, role, tool start/end, duration, outcome, evidence
counts, test exit codes/status, truncation, and provider token usage when supplied. Historical
runs also record snapshot hashes. Logs omit prompts, source bodies, secrets, and hidden reasoning.

For the completed 100-issue baseline, the trace audit found 100 complete runs, 399 paired tool
calls, zero empty searches, zero tool errors, and zero truncated indexes. Scoring still found
29 top-five localization misses: successful tool execution is not successful diagnosis.
There were no LLM-routing failures to report because this baseline did not call an LLM.

Fault-injection tests separately verify timeout handling, dependency-import/collection errors,
unknown tools, budget limits, secret redaction, and invented-citation rejection. Those are tested
failure patterns, not incidents invented for the historical benchmark. Use
`code-assistant logs runs/<run-directory>` to inspect actual counts and raw tool durations.

**中文：** 我会对齐每条 issue 的开始/结束、每次工具的开始/结束，以及退出状态、耗时
和证据数。真实基线没有执行错误，但有 29 条前五候选未命中，说明工具运行成功不等于
诊断成功。超时、环境错误和伪造引用是在故障注入测试中验证的，不能说成真实模型评测
期间出现过的问题。
