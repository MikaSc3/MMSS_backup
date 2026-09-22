# Interaction analysis

This LLM node analyzes the geometric and mechanical interaction for exactly one
assembly-sequence step. Workflow composition will fan out over all steps and
aggregate their artifacts later.

## Public entry point

```python
from assembly_automation.workflows.nodes.interaction_analysis import run_interaction_analysis

result = run_interaction_analysis(
    step_id=2,
    artifacts={
        "sequence": assembly_sequence,
        "bom_enriched": bom,
        "spatial_relations": spatial_relations,
        "interlocking": interlocking,
        "sequence_renderings": renderings_directory,
        "assembly_overview": assembly_overview,  # optional
        "images": preprocessing_images,          # optional and disabled by default
    },
    settings=config["nodes"]["interaction_analysis"],
    llm_profiles=config["llms"]["profiles"],
    output_path="interaction_analysis/steps/step_002.json",
)
```

The sequence and JSON artifacts may be mappings or paths. The sequence may be a
bare sequence or the complete `sequence_generation` artifact.

## Input preparation

`inputs.py` resolves sequence `instance_id` values through BOM `instances` and
then attaches the corresponding unique-part definition. Copies are kept as
physical instances; IDs are never normalized by removing `_copyN`.

For a joining operation, the node derives the globally assembled-before state.
It includes only spatial pairs between joining instances and parts present in
that state. Interlocking directions and blockers are filtered to the same state
so parts added by future steps do not appear as current obstacles. The first
step receives an explicit initial-placement base instead of a fabricated part.

The required visual input is `collage_step_XX.png`. Configured before-section
images provide a direct comparison with the state immediately before joining.
The unique joining-part collage is optional and disabled by default.

## Output

Each step artifact contains:

```text
step
interaction_analysis
inputs
images_used
execution
```

The structured analysis retains the established interaction categories and
adds `evidence_limitations`. Prompts explicitly prevent render colors from being
interpreted as materials and prevent invented numerical tolerances.

`fanout.parallel` and `fanout.max_workers` are stored with the node config for
the future workflow. The node validates but does not execute fan-out. Parallel
execution, retries, atomic `interaction_analysis_partial.json`, and final
aggregation belong to workflow orchestration.
