# Report synthesis

This package builds the editable decision model used by final report renderers
and the user-facing agent. It does not render a PDF.

## Responsibilities

`report_data.py` loads explicit assembly overview, enriched BOM, approved
sequence, per-step FFA assessments and deterministic FFA scores. It validates
matching step identities and constructs a compact evidence catalog with stable
logical references. Existing facts, step summaries, numerical scores, part
profiles, unknowns and image references are copied deterministically.

One configured LLM call receives only that catalog. Its task is limited to
deduplicating and ranking cross-step findings, linking improvements to findings,
and writing a short executive summary. Every finding and recommendation must
cite known source references. Source-derived actions must cite an improvement
already present in an FFA assessment. New proposals are labeled
`proposed_hypothesis` and require explicit assumptions.

The deterministic compiler assigns stable report IDs, adds structured
`validation_status` values and links findings and recommendations back to parts
and steps. Validation status is metadata rather than `[]` or `[x]` embedded in
the prose.

## Public entry point

```python
from assembly_automation.workflows.nodes.report_synthesis import run_report_synthesis

result = run_report_synthesis(
    artifacts={
        "assembly_overview": assembly_overview,
        "bom_enriched": enriched_bom,
        "sequence": approved_sequence,
        "ffa_assessments": per_step_assessment_artifacts,
        "ffa_scores": ffa_scores,
    },
    settings=config["nodes"]["report_synthesis"],
    llm_profiles=config["llms"]["profiles"],
    context={"user_context": user_context},
    output_path="reports/report.json",
)
```

The output contains assembly overview, executive summary, scorecard, findings,
recommendations, deterministic step records, part profiles, unknowns and full
synthesis provenance. Report rendering should treat this JSON as its only
content input and expose separate executive and engineering-detail profiles.
