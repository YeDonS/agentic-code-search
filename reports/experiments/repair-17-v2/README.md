# Bounded repair of all 17 originally invalid candidates

**17/17 patches apply; 11/17 resolve official SWE-bench regressions.** Six apply but remain
functionally unresolved. All 17 outcomes are present; no failures are excluded.

This is a selected, extra-budget post-hoc study using the original frozen diagnoses and
candidates. It is separate from the original **48/100** source-only run and from
[development v1](../repair-17-v1/), which resolved 9/17. Every candidate was rerun in v2;
the best patches from different runs were not pooled. Sampling and provider variation
prevent attributing the v1/v2 difference solely to exception handling.

The actor received the original issue/candidate, pre-fix source observations and the apply
error, with at most two correction attempts, six model calls and eight tool calls per case.
It received no reference fix or official-test feedback. The original causal explanation
and file scope stayed fixed. The model may still change implementation details when
repairing context, so this does not isolate formatting as the only cause of improvement.

The copied original diagnoses retain their original limitations, including the historical
"candidate withheld" notice. That notice describes the ancestor run; the current repair
status is in `checks/` and the official outcomes. It does not mean repaired patches remained
withheld. Subsequent code removes this generated stale notice when rechecking a diagnosis.

- [Manifest](manifest.json), [source proof](source-proof.json), [usage](model-usage.json)
- [Frozen official predictions](swebench-predictions.jsonl)
- [Original and corrected attempts](attempts/), [final checks](checks/)
- [Official outcomes](official-evaluation/results.json), [workflow/image provenance](official-evaluation/manifest.json)
- [Official workflow](https://github.com/YeDonS/agentic-code-search/actions/runs/37849300774)

The 40 model invocations reported 519,468 input and 22,898 output tokens, with no model
errors, built-in tool calls or transport reconnects. Applicability checks never executed
repository code; functional testing ran afterward in the pinned official containers.

中文：全部 17 条原无效补丁恢复为可应用，其中 11 条通过官方回归，6 条仍失败。
这是额外预算的事后补救，不能加回原 48/100 冒充首次成功率；第一轮记录保留，未择优合并。
