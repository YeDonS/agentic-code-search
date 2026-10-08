# Evidence-backed resume wording / 可核验简历表述

The following wording describes the measured implementation and its published evidence.

**Agentic Code-Search & Debugging Assistant | 2026**

*LangChain, LangGraph, FastAPI, Docker*

- Built a three-agent debugging assistant with state-based routing between code search,
  focused test execution, and evidence-grounded synthesis.
- Integrated bounded search, source-reading, test-running, and log-inspection tools with
  validated citations, explicit abstention, and isolated patch applicability checks.
- Evaluated a real LLM on 100 pinned historical SWE-bench Lite issues across 12 repositories,
  achieving 88% file Hit@5 and **48/100 functional resolutions** in official Docker tests.
- Delivered an authenticated FastAPI service, Docker images, and structured traces covering
  541 model responses and 844 tool calls; verified 75 tests and multi-version/container CI.

**中文：**

- 使用 LangChain/LangGraph 构建三个专职 agent，依据证据、测试状态及预算在代码搜索、
  测试执行与综合诊断之间路由。
- 接入真实仓库检索、源码读取、测试及日志工具，校验引用，支持证据不足时放弃，
  并在隔离副本检查补丁能否应用。
- 在覆盖 12 个仓库的 100 条固定历史问题上运行真实 LLM，文件 Hit@5 达 88%，
  官方 SWE-bench Docker 测试确认 **48/100** 功能修复。
- 提供带认证的 FastAPI 服务、Docker 镜像和结构化日志，记录 541 次模型响应及
  844 次工具调用；通过 75 项测试与多 Python 版本、容器 CI。

The 100-task inference phase is source-only. The test specialist actually runs on trusted
repositories, demonstrated separately through real-model CLI and HTTP integration checks.
Historical hidden tests run after predictions freeze in the official evaluation environment.
Failures, abstentions, and timeouts remain in the denominator. The subset is not an official
leaderboard submission and has not undergone a controlled orchestration ablation.

Automatic root-cause comparison judged 87 correct, 1 partial, 2 incorrect, and 10 unscorable.
This is **87% automated agreement**, with possible same-model bias. Do not describe it as
human-validated root-cause accuracy. File Hit@5, causal agreement, and functional resolution
measure different outcomes. [Evidence](../reports/README.md) · [Interview answers](INTERVIEW.md).
