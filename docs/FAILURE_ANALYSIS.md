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
- `psf__requests-2674`: automated review found that the diagnosis targeted
  `ConnectTimeoutError`, while the maintainer correction handled `ClosedPoolError`.
  [Review records](../reports/model-100/automated-review/reviews.jsonl).
- `psf__requests-2317` and `sympy__sympy-11870`: patches applied and tests began, then
  timed out at 600 seconds. The logs do not establish an infrastructure-only cause;
  both count as unresolved in the aggregate.
  [Requests excerpt](../reports/model-100/official-evaluation/psf__requests-2317/test-output-excerpt.txt) ·
  [SymPy excerpt](../reports/model-100/official-evaluation/sympy__sympy-11870/test-output-excerpt.txt).

## Improvements to evaluate separately

The current implementation preserves original candidates, checks cited/read file membership,
mechanically recounts diff hunk lengths, and validates applicability on an isolated copy.
That prevented invalid suggestions from becoming submitted patches, but 17 candidates still
failed the check. A future run could request a bounded model correction using only that
pre-evaluation applicability error. It must freeze a new configuration and retain the
original run as its baseline.

A larger investigation budget may reduce abstentions. Set `ASSISTANT_MAX_AGENT_STEPS=7`
and use a new output directory to measure the tradeoff in tokens, latency, and resolution.
Longer test timeouts are another separate protocol change; preserve the 600-second results
and do not merge retries into the original score. Neither change has been claimed as tested.

## 中文说明

最终官方修复率为 **48/100**。23 份补丁虽然能够应用，但未满足回归要求；17 份候选
未通过应用检查，10 条模型判断证据不足，因此共有 27 条空补丁；另有 2 条测试超时。
没有丢失样本，也没有因为失败而换题或删除分母。

自动根因核对认为正确的 87 条中，有 40 条没有通过官方功能验证。这说明解释正确、
补丁可应用和功能修复是不同要求，自动评审也可能过于宽松。全部原始预测、被拒候选、
官方结果、实际镜像 digest 和日志摘录均保留。增加轮数、补丁纠错或延长测试时间都应
作为新的实验，不能回写本次冻结成绩。
