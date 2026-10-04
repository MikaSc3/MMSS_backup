# FFA scoring

This node converts completed `ffa_assessment` classifications into numerical
scores. It is deterministic and makes no LLM call. Workflow composition passes
either one step artifact, a list of step artifacts, an aggregate with `steps` or
`step_assessments`, or paths to those JSON documents.

## Public entry point

```python
from assembly_automation.workflows.nodes.ffa_scoring import run_ffa_scoring

result = run_ffa_scoring(
    assessments=step_assessment_artifacts,
    settings=config["nodes"]["ffa_scoring"],
    output_path="ffa_assessment/ffa_scores.json",
)
```

The node sorts steps by `step_id`, rejects duplicate IDs and, in the default
strict mode, rejects missing or unknown classifications. It produces criterion
details, the four subprocess scores, a total score per step, aggregate means and
the population standard deviation of total scores. Output writes are atomic.

## Scoring resource

`scoring_mapping.yaml` is package-local and versioned as `ffa_scoring_v1`.
Loading validates all 14 criteria against the enums in
`ffa_assessment/structured_output.py`, including exact option coverage, score
ranges and criterion/subprocess weights. Each output records the mapping ID,
status and SHA-256 hash so a report can be traced to the rules used.

The mapping is marked `authoritative_historical_baseline`. It preserves every
option ID, exact label, numeric value, criterion weight and subprocess weight
from `data/ground_truth/mapping/ffa_scoring_mapping.json`. The package resource
also records the SHA-256 hash of that supplied source file. Runtime scoring
accepts both the exact structured-output labels and the integer annotation IDs.

The scoring formulas preserve the legacy behavior: covered criterion weights
are normalized within each subprocess, the total is the weighted mean of the
available subprocess scores, and aggregate deviation is population standard
deviation. The default subprocess weights are equal, which is equivalent to the
legacy arithmetic mean.
