# Failure analysis / 失败分析

The frozen real-model run finished all 100 selected tasks. Official `swebench==5.0.2`
evaluation produced the following complete accounting:

| Outcome | Count | Meaning |
|---|---:|---|
| Resolved | 48 | Official FAIL_TO_PASS and PASS_TO_PASS requirements satisfied |
| Unresolved | 23 | Nonempty patch applied, but official regression requirements failed |
| Empty patch | 27 | 17 invalid candidates withheld; 10 model abstentions |
| Test timeout | 2 | Test execution exceeded the fixed 600-second limit |
| Missing outcome / image-pull failure | 0 | All 100 outcomes accounted for |

The resolution rate is **48/100**, with no denominator exclusions. Predictions were never
repaired after seeing reference patches or official results. The three-issue pilot is a
separate protocol check; its 3/3 result is not added to the full-run denominator.
[Raw counts](../reports/model-100/failure-analysis.json) ·
[Official outcomes](../reports/model-100/official-evaluation/results.json).

## What the evidence establishes

The source audit found 26 role turn-limit events, 7 recoverable tool errors, 10 abstentions,
and 17 invalid patches. There were no run crashes, invalid synthesis outputs, unpaired tools,
or unfinished traces. A role hitting its turn limit can still synthesize from existing
evidence, so 26 limit events do not mean 26 failed issues.

Post-freeze automated review marked 87 explanations correct, yet **40 of those cases did
not resolve in official tests**. The reviewer evaluates the causal explanation; it does not
prove implementation completeness. It also shares the actor's model family, which can bias
agreement. Named human root-cause accuracy remains unmeasured.

Examples retained for inspection:

- `astropy__astropy-14365`: the candidate applied, but the official
  `test_roundtrip[True]` regression still failed.
  [Report](../reports/model-100/official-evaluation/astropy__astropy-14365/report.json).
- `psf__requests-2674`: **the submitted patch resolved the official tests** although the
  automated causal reviewer marked the explanation incorrect (`ConnectTimeoutError` versus
  the maintainer's `ClosedPoolError`). This is a judge/functional disagreement, not an
  unresolved patch. Tests do not prove every sentence of the explanation, and the reviewer
  cannot substitute for the functional grade.
  [Official passing report](../reports/model-100/official-evaluation/psf__requests-2674/report.json) ·
  [Review records](../reports/model-100/automated-review/reviews.jsonl).
- `psf__requests-2317` and `sympy__sympy-11870`: patches applied and tests began, then
  timed out at 600 seconds. The logs do not establish an infrastructure-only cause;
  both count as unresolved in the aggregate.
  [Requests excerpt](../reports/model-100/official-evaluation/psf__requests-2317/test-output-excerpt.txt) ·
  [SymPy excerpt](../reports/model-100/official-evaluation/sympy__sympy-11870/test-output-excerpt.txt).

## Maintainer-patch sanity controls

Two unresolved cases with incidental fixture/import errors were checked using the exact
maintainer patches, after inference froze. Both controls **resolved the official required
tests** using the same recorded image digests. Other errors in the larger test output still
occurred, so those messages alone do not invalidate the targeted grade. Both original
agent failures remain unresolved; the score stays 48/100.
[Maintainer controls and reports](../reports/evaluation-controls/README.md).

## Improvements evaluated separately

The current implementation preserves original candidates, checks cited/read file membership,
mechanically recounts diff hunk lengths, and validates applicability on an isolated copy.
That prevented invalid suggestions from becoming submitted patches, but 17 candidates still
failed the check. The revised implementation feeds that error back for at most two repairs,
lets synthesis read exact source, and keeps the original candidate and every attempt.
New/deleted regular text files are supported; path escape and symlinks remain forbidden.
The original 100 predictions are immutable; the 17-candidate post-hoc study is separate.

The original window retained only the last 24 evidence records. Of 39 issues exceeding that
window, 10 abstained; none of the other 61 did. Difficulty and search behavior confound this
association. Source-priority selection and a matched recent-window control are implemented
to investigate it, without claiming this correlation proves causation.
[Separate protocol and results](EXPERIMENTS.md).

The default role ceiling is now seven calls with a final-answer turn and a shared global
ceiling. The paired experiments freeze their own equal budgets and report actual costs.
Longer test timeouts are another separate protocol change; preserve the 600-second results
and do not merge retries into the original score.

## 中文说明

最终官方修复率为 **48/100**。23 份补丁虽然能够应用，但未满足回归要求；17 份候选
未通过应用检查，10 条模型判断证据不足，因此共有 27 条空补丁；另有 2 条测试超时。
没有丢失样本，也没有因为失败而换题或删除分母。

自动根因核对认为正确的 87 条中，有 40 条没有通过官方功能验证。这说明解释正确、
补丁可应用和功能修复是不同要求，自动评审也可能过于宽松。全部原始预测、被拒候选、
官方结果、实际镜像 digest 和日志摘录均保留。增加轮数、补丁纠错或延长测试时间都应
作为新的实验，不能回写本次冻结成绩。

`psf__requests-2674` 的补丁实际通过官方测试，自动评审却把解释判错；已纠正此前将其
混在失败示例中且未说明官方成功的文档。根因判断与功能验证不一致时分别保留，自动
“87%”不再作为 README 主成绩，未用模型伪造人工抽检。

另对两条出现夹具/依赖报错的失败样本运行维护者补丁对照，两份都通过官方指定回归，
无关报错仍会出现。因此不能把这些报错直接当作排除失败样本的依据。对照单独记录，
不增加模型成绩；两条超时的具体原因仍未确定。
