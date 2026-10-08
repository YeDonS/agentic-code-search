# Paired 20-task controls

**Single conversation: 11/20 resolved. Routed recent: 10/20. Routed source-priority: 10/20.**
This exploratory pilot provides no evidence that the routed architecture improves resolution.
All arms retain every failure, abstention and timeout in the denominator.

| Arm | Official resolved | Applicable patches | Model invocations | Reported input / output tokens |
|---|---:|---:|---:|---:|
| [Routed recent](routed_recent/) | 10/20 | 15/20 | 118 | 1,261,205 / 24,485 |
| [Routed source-priority](routed_source/) | 10/20 | 15/20 | 121 | 1,299,138 / 26,966 |
| [Single conversation](single/) | **11/20** | 16/20 | 102 | 1,119,272 / 18,638 |

The two routed arms resolve exactly the same ten cases. The single arm additionally resolves
`psf__requests-2674`. One stochastic run on twenty public tasks cannot establish superiority;
different provider failures also confound small differences (recent: one, source-priority:
zero, single: two). Reported tokens cover completed responses; failed-call usage is unknown.
The single arm uses fewer observed calls and reported tokens in this run, without a claim
about general speed or monetary cost.

[The plan](plan.json) and [selected actor inputs](tasks.jsonl) were frozen before inference.
Selection used SHA256(`controls:20261008:instance_id`) over the original 100-task frame,
without filtering by original outcomes or judge labels. Every arm uses source commit
`6b61f9a4ac9ac5b5420caf1eba7d3d503f33c9fb`, model `codex-cli:gpt-6.1-sol`, medium reasoning,
HTTPS, CLI `0.162.0-alpha.2`, and four workers. Every task has the same ceilings of ten model
and eighteen tool calls. Repairs and test-agent execution are disabled in all three arms.
Equal ceilings do not mean equal consumed tokens or exactly matched compute cost.

The [comparison](comparison.json) rejects configuration differences beyond the intended
architecture/window factor, verifies actual call ceilings, joins official grades by patch
hash, and includes per-issue source retention and errors. The recent handoff loses three
unique source observations across two tasks; source priority loses none. The functional
grade remains 10/20 for both, so retention is a demonstrated mechanism without a demonstrated
resolution gain. Another [100-ledger replay](../historical-context-replay.json) provides the
original-window audit without rerunning a model.

Official workflows: [recent](https://github.com/YeDonS/agentic-code-search/actions/runs/37848455841),
[source-priority](https://github.com/YeDonS/agentic-code-search/actions/runs/37849298422),
[single](https://github.com/YeDonS/agentic-code-search/actions/runs/37850192309).
Reports, image digests, test excerpts and raw-log hashes are retained under each arm's
`official-evaluation/`. The original 48/100 and separate 17-candidate repair study are unchanged.

中文：同模型、相同调用预算上限的 20 题试验中，单 agent 为 11/20，两种两步流程均为
10/20。单 agent 本次实际调用和报告 token 更少；样本小、有提供商调用失败且未按实际
token 成本严格匹配，不能据此宣称普遍优势。源码优先减少了源码丢失，但未提高这批题的
官方修复率。测试 agent 未参与，故不能用这些结果证明三 agent 架构的收益。
