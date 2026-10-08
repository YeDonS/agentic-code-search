# Evidence-backed resume wording / 可核验简历表述

Use this version for the current implementation. Replace the evaluation bullet only after
the real-model run, complete causal review, and official patch evaluation have artifacts.

**Agentic Code-Search & Debugging Assistant | 2026**

*LangChain, LangGraph, FastAPI, Docker*

- Built a three-specialist debugging workflow with state-based routing between code search,
  focused test execution, and evidence-grounded synthesis.
- Exposed bounded repository-search, source-reading, pytest, and log-inspection tools through
  LangChain's native tool-calling protocol, with registered citations and explicit abstention.
- Executed a reproducible 100-issue retrieval benchmark on historical pre-fix repository
  snapshots, achieving 71% file Hit@5 against maintainer patch locations.
- Implemented a FastAPI service, Docker service/test images, structured JSONL traces, and
  CI checks across three Python versions; added separate human root-cause and official
  SWE-bench patch-scoring workflows.

**中文对应：** 实现三个专职 agent、可审计路由和真实工具；完成 100 条历史问题的
文件定位基线，前五候选命中率 71%；提供 FastAPI、Docker、结构化日志和 CI。
目前不要写“100 条大模型诊断已完成”“根因正确率 71%”或“修复成功率 71%”。
