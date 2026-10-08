# Maintainer-patch controls / 维护者补丁对照

These are **two post-hoc environment sanity checks**, separate from the agent's 100-task
experiment. The original model outputs had unresolved grades and incidental pytest
fixture/import errors. To test whether those observations invalidate the grade, the exact
pinned maintainer patches were evaluated with the same official harness and image digests.

| Instance | Agent result | Maintainer control | Required regressions |
|---|---|---|---|
| `psf__requests-3362` | Unresolved | Resolved | 1 FAIL_TO_PASS, 75 PASS_TO_PASS |
| `pydata__xarray-4493` | Unresolved | Resolved | 1 FAIL_TO_PASS, 1,689 PASS_TO_PASS |

Both controls passed the official required tests. Incidental fixture/import errors elsewhere
in the test output still occurred. SWE-bench grades the specified FAIL_TO_PASS/PASS_TO_PASS
requirements, so an unrelated error in the larger test suite does not alone invalidate the
grade. These controls support retaining both original unresolved outcomes. They do not
establish that every environment in the 100-task experiment is sound, explain the two
timeouts, or increase the agent's score.

[Results](results.json) · [Manifest](manifest.json) ·
[Frozen maintainer predictions](swebench-predictions.jsonl) ·
[Official workflow](https://github.com/YeDonS/agentic-code-search/actions/runs/37827800765).
Per-instance reports, excerpts, image digests, and raw-log hashes are committed alongside
this file. Reference patches were used only after actor predictions froze.

Reproduce separately from model predictions:

```bash
# On a disposable Linux Docker host with swebench==5.0.2 installed:
uv run --no-sync python scripts/evaluate_patches.py reports/evaluation-controls/swebench-predictions.jsonl runs/new-maintainer-controls
uv run python scripts/aggregate_patch_results.py reports/evaluation-controls/swebench-predictions.jsonl runs/new-maintainer-controls runs/new-maintainer-controls-results.json
```

中文：两条模型失败日志包含测试夹具或依赖报错，因此使用维护者原始补丁做了额外对照。
同一镜像 digest 和官方 harness 下，两份维护者补丁均满足指定回归要求，其他报错仍存在。
这说明不能仅凭无关报错删除模型失败样本。本次模型修复率仍为 **48/100**；对照的
2/2 不加入分子或分母，也不代表排除了其他样本的全部环境风险。
