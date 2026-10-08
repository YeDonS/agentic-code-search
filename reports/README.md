# Published evidence / 运行证据

The checked-in artifacts record real local execution on 2026-10-08. No model provider
credentials or local Docker engine were available. Docker evidence is provided separately
by the repository's [GitHub Actions runs](https://github.com/YeDonS/agentic-code-search/actions).

| Artifact | Meaning |
|---|---|
| `retrieval-100/manifest.json` | Ordered task IDs, data hash, settings, environment and implementation fingerprint |
| `retrieval-100/predictions.jsonl` | Actual ranked files for all 100 issues; source excerpts omitted for publication |
| `retrieval-100/scores.json` | Per-issue localization metrics and fixed 100-issue denominator |
| `retrieval-100/trace-events.jsonl` | All per-issue structured events, grouped by run ID |
| `retrieval-100/log-audit.json` | Run/tool conservation counts, failure-pattern counts, raw tool durations |
| `retrieval-100/reproduction.json` | Equality check against the first full 100-issue run |
| `demo/response.json` | Scripted diagnosis with actual source/test evidence from the original demo fixture |
| `demo/events.jsonl` | Search → test → search → synthesis transitions and real tool events |
| `validation.json` | Local checks and remaining evaluation limits |
| `github-ci.json` | Successful Docker and Python 3.11/3.12/3.13 jobs for the implementation commit |

All 100 historical runs completed. File Hit@1 = **0.40**, Hit@5 = **0.71**, MRR@5 = **0.5201667**.
The audit records 100 complete runs and 399 paired tool calls, with no empty searches, tool
errors, or index truncation. There are 29 localization misses despite successful tool execution.

[The implementation CI run](https://github.com/YeDonS/agentic-code-search/actions/runs/37818447547)
passed all four jobs, including actual container API and restricted-runner checks.
The final evidence-only documentation commit does not change the verified implementation.

Root-cause accuracy and patch resolution remain `null`: neither can be inferred from file
localization. The demo is synthetic, uses a fixed model script, and is excluded from the
historical benchmark. Full local responses and source archives remain in ignored directories.

中文：这些是实际运行产生的文件定位与工具验证证据。100 条全部跑完，71% 只表示前五
候选文件命中维护者修改位置。真实模型根因正确率和官方回归通过率尚未产生，不填数字。
