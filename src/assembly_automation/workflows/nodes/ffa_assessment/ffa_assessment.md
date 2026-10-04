# FFA assessment

This node classifies exactly one assembly step across Separation, Handling,
Positioning and Joining. Workflow composition will fan out over sequence steps
and aggregate the per-step artifacts.

## Public entry point

```python
from assembly_automation.workflows.nodes.ffa_assessment import run_ffa_assessment

result = run_ffa_assessment(
    step_id=2,
    artifacts={
        "sequence": assembly_sequence,
        "bom_enriched": bom,
        "interaction_step": interaction_step_artifact,
        "sequence_renderings": renderings_directory,
        "images": preprocessing_images_directory,
        "assembly_overview": assembly_overview,  # optional
    },
    settings=config["nodes"]["ffa_assessment"],
    llm_profiles=config["llms"]["profiles"],
    output_path="ffa_assessment/steps/step_002.json",
)
```

The node reuses interaction-analysis input preparation, including physical-copy
resolution and the initial-placement base contract. The interaction artifact is
checked against the requested step ID.

## Evidence

The configured default prompt receives:

- the sequence step;
- base and joining instance/definition data from the enriched BOM;
- the matching interaction-analysis result;
- the current step collage;
- available before-section images;
- the joining part's preprocessing collage;
- optional assembly overview and user context.

The prompt separates intrinsic joining-part criteria (Separation and Handling)
from operation criteria (Positioning and Joining). It explicitly treats render
colors as identifiers and prevents unsupported material, surface, tolerance,
packaging and delivery claims.

## Stable classifications

`structured_output.py` retains the exact historical FFA option strings,
including their original spelling, because evaluation and deterministic scoring
map those byte-identical values. The schema adds stronger validation:

- every criterion has exactly one enum value;
- `overall_ffa` contains each subprocess exactly once;
- evidence and missing-information fields cannot be empty;
- drawback lists have bounded sizes.

Each artifact stores `step`, `ffa_assessment`, configured input provenance,
images used, prompt hashes, model identity, measured token usage, elapsed time,
and tool-call counts.

## Fan-out and reuse

`fanout.parallel` and `fanout.max_workers` are workflow settings. This node does
not manage threads or shared caches. The legacy cache generated a complete LLM
assessment and only then overwrote Separation and Handling, so it saved no model
work. The new workflow should implement reusable intrinsic classifications as a
separate scheduled artifact if measurements show that repeated definitions make
the extra orchestration worthwhile.
