# Published evidence / 运行证据

Real execution on 2026-10-08 includes the original retrieval baseline, a complete 100-issue
LLM run, post-freeze automated review, and official SWE-bench Docker tests on GitHub Actions.
Model inference reused a local Codex login; authentication files and API secrets are excluded.

| Evidence | Meaning |
|---|---|
| [Model manifest](model-100/manifest.json) | Fixed 100 tasks, model/reasoning/transport, budgets, environment, CLI version |
| [Source proof](model-100/source-proof.json) | Inference source digest matches the recorded Git commit |
| [Predictions](model-100/predictions.jsonl) | All 100 diagnoses/abstentions and submitted patches |
| [Diagnoses and citation provenance](model-100/diagnoses.jsonl) | Causal explanations, source paths/lines, route history; source excerpts omitted |
| [Localization scores](model-100/scores.json) and [final scores](model-100/final-scores.json) | File metrics and official 48/100 resolution; human accuracy remains null |
| [Official results](model-100/official-evaluation/results.json) and [manifest](model-100/official-evaluation/manifest.json) | All 100 outcomes, exact patch hashes, image digests, 20 shard manifests |
| [Failure analysis](../docs/FAILURE_ANALYSIS.md) and [counts](model-100/failure-analysis.json) | 23 test failures, 27 empty patches, 2 timeouts; complete denominator |
| [Withheld candidates](model-100/withheld-patches.jsonl) | 17 original invalid patches retained for audit |
| [Model usage](model-100/model-usage.json) | 541 responses, reported tokens, reconnects, patch checks |
| [Events](model-100/trace-events.jsonl) and [audit](model-100/log-audit.json) | 844 paired tools, budgets/errors, raw durations and trace conservation |
| [Automated causal review](model-100/automated-review/summary.json) | 87 correct, 1 partial, 2 incorrect, 10 unscorable; not human accuracy |
| [Frozen batches](model-batches/) | Four consecutive 25-task batches for overlapping official evaluation |
| [Pilot official results](model-pilot-3/official-evaluation/results.json) | Three real historical patches resolved; reports, test excerpts, raw-log hashes |
| [Real-model checkout](real-model-checkout/) | Real search/test/synthesis routing, actual baseline failure and patched-copy success |
| [Real-model HTTP](real-model-api/validation.json) | Bearer auth and actual three-role model workflow through FastAPI |
| [Retrieval baseline](retrieval-100/scores.json) | Original Hit@1 40%, Hit@5 71%, MRR@5 0.5201667 |
| [Retrieval reproduction](retrieval-100/reproduction.json) | Second full run produced identical ranked predictions |
| [Validation](validation.json) and [CI](github-ci.json) | Local checks and actual multi-version/container evidence |

The LLM run completed **100/100**: 90 cited diagnoses and 10 explicit abstentions. File
Hit@1 is **87%**, Hit@5 **88%**, MRR@5 **0.875**. The automated comparison rate is **87%**;
named human adjudication remains unmeasured. There are 73 applicable patches, 17 withheld
candidates, and 10 abstentions. The complete official evaluation resolved **48/100**;
23 were unresolved, 27 had empty patches, and 2 tests timed out. No outcomes are missing.
The fixed denominator includes all empty patches, failures, and timeouts.

Official workflow runs: [batch 1](https://github.com/YeDonS/agentic-code-search/actions/runs/37823468905),
[batch 2](https://github.com/YeDonS/agentic-code-search/actions/runs/37823608201),
[batch 3](https://github.com/YeDonS/agentic-code-search/actions/runs/37824041242),
[batch 4](https://github.com/YeDonS/agentic-code-search/actions/runs/37824921353).
The [three-issue pilot](https://github.com/YeDonS/agentic-code-search/actions/runs/37822223997)
resolved all three patches. Raw official logs remain in GitHub run artifacts and ignored
local `runs/`; durable reports/excerpts/hashes are curated here. The synthetic fixture is
excluded from the historical task set. Full source archives, prompts, and hidden reasoning
are not published.

中文：100 条真实模型运行及官方测试已完成，官方修复率 48/100；定位命中、自动根因
核对和官方功能修复分别评分。
自动核对 87% 不能称为人工根因准确率。所有失败和空补丁都保留在总分母中，原始预测
不会根据测试结果修改。镜像 digest、补丁哈希、逐条结果和日志支持核验与复现。
