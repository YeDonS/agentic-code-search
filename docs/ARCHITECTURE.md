# Architecture / 架构

## Control flow

[`workflow.py`](../src/code_assistant/workflow.py) builds a LangGraph state machine with a
router and three specialist nodes. The router's input is observable state: completed search
passes, registered source reads, whether tests were attempted, test outcome, and tool budget.
It does not rely on a model's unvalidated claim that a test passed.

1. Always search first.
2. If no source was read and another search pass is allowed, refine the search.
3. With source evidence, run the test specialist once if execution is enabled.
4. After an actual baseline assertion failure, permit one further source investigation.
5. Synthesize when evidence is available or limits are reached. Without a source read,
   return insufficient evidence. Explicit model abstention has the same status.

The model is shared, but each specialist receives its own system prompt, message history,
and tool list. Evidence and short findings cross role boundaries. This is sequential specialist
orchestration, not parallel independent model processes. The supervisor's rules are deliberate:
they are cheap to audit and guarantee an evidence-gathering opportunity before synthesis.

## Tool protocol

[`agents.py`](../src/code_assistant/agents.py) uses LangChain `BaseChatModel.bind_tools`,
`AIMessage.tool_calls`, `StructuredTool.invoke`, and paired `ToolMessage` results. The model
chooses tools and arguments. Application code validates them, performs execution, registers
evidence, and returns the tool output to the model. LangGraph controls the specialist transitions.

[`tools.py`](../src/code_assistant/tools.py) provides:

| Tool | Actual operation | Boundary |
|---|---|---|
| `search_repository` | BM25 over current source files | No Git history or network search; max 10 hits |
| `read_file` | UTF-8 source excerpt with path and line range | Relative paths; max 120 lines |
| `run_tests` | Fixed `python -m pytest` argument vector | Explicit test files/node IDs; no shell |
| `inspect_logs` | Retrieve a test output registered in this run | No arbitrary filesystem log paths |

The index skips hidden directories, dependency/build caches, excluded gold folders, symlinks,
binary data, and files larger than 500 KB. It caps 20,000 files / 80 MB and logs truncation.
Each evidence record has an immutable ID for that run. Source reads and search snippets have
distinct kinds: a search snippet alone cannot satisfy the final source-read requirement.

## Output and verification

Synthesis produces a Pydantic `Diagnosis`: conclusion, causal explanation, affected files,
evidence IDs, proposed change, optional unified diff, confidence, and limitations. Unknown IDs
or affected files absent from cited reads are rejected. The response includes the full route
trace, real baseline test status, mode, and run ID.

Citation checks establish provenance only. A model can still misunderstand genuine evidence.
Confidence is model-reported, not a calibrated probability. Semantic review and official
regression tests are required for correctness claims. The service never applies patches;
`patch_verified` remains false. Project tests separately verify the synthetic example's patch.

## Execution and service boundaries

Local execution is disabled by default. Opting into local pytest executes repository code
with the current operating-system user's privileges; it is not a sandbox. Provider credentials
are removed from the subprocess environment, but that does not prevent filesystem/network
access by trusted local code. Use the Docker runner for process isolation, and official
per-instance containers for historical tests.

The Docker runner disables networking, mounts source read-only, uses a non-root user,
drops capabilities, limits CPU/memory/PIDs, and uses a temporary filesystem. Timeout/output
limits kill the process group; timed-out Docker containers are explicitly removed by ID.
Containers are an isolation mechanism, not a guarantee against hostile code. The generic
image only includes pytest, so missing project dependencies are environment failures.

FastAPI resolves relative repository names under a configured workspace, blocks root escape,
offers optional constant-time bearer-token checks, and permits two concurrent runs. The
provided launch paths bind loopback. Remote access requires authentication and deployment-level
rate limiting/TLS. No wildcard CORS or Docker socket is exposed by the supplied configuration.

Run artifacts are local, private-permission files ignored by Git. Event logs omit source and
prompt bodies and redact configured environment secrets. Detailed responses contain source
excerpts; publish only deliberately curated records. Native providers receive selected source.

## References

The implementation follows the documented [LangChain tool protocol](https://docs.langchain.com/oss/python/langchain/tools),
[LangGraph workflow model](https://docs.langchain.com/oss/python/langgraph/workflows-agents),
and [OpenAI function-calling flow](https://developers.openai.com/api/docs/guides/function-calling).
Historical patch evaluation follows [SWE-bench](https://www.swebench.com/SWE-bench/guides/evaluation/).

## 中文要点

监督器依据真实状态路由；模型只决定角色内部的工具调用。三个角色独立上下文、顺序运行。
搜索片段不等于已经读取源码，综合结果必须引用登记的源码证据，未知引用会被拒绝。

测试工具运行真实 pytest，但只代表修复前状态。服务不会应用补丁，也不把建议包装成验证
成功的修复。默认不执行测试，本地执行只适合可信仓库；受限容器和官方评测环境另有入口。
引用校验不能证明因果解释正确，真实模型准确率需人工核对，补丁效果需正式回归测试。
