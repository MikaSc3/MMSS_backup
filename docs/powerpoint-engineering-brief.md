# Engineering PowerPoint export — implementation brief

## Goal
Implement a reusable, deterministic PowerPoint exporter for the existing product-analysis pipeline. Use saved structured outputs and existing CAD images to generate editable `.pptx` engineering reports. An agent-bound tool must trigger generation. No additional LLM call is required to render the report.

## Initial scope
Implement two section renderers:
- **Assembly:** assembly name, overview image, primary function, and assembly description.
- **Monopart:** one section per distinct part, including stable part ID/name, CAD image, part identification, and intrinsic summary.

Support assembly-only, monopart-only and combined reports. The initial agent tool
exports the active assembly and all distinct monoparts without arguments; section
selection remains an open builder API for future programmatic callers. Sequence,
FfA and layout are future renderers, outside this first implementation.

## Architecture
1. Inspect the existing schemas, artifact storage and agent tool registration before coding. Reuse their conventions.
2. Create adapters from current module outputs to validated report data. Keep presentation field mappings separate from analysis prompts/schemas. Do not rename existing output keys solely for PowerPoint.
3. Use one report builder to load the design/template, select sections, invoke renderers, add cover/footer/page numbers and save the result.
4. Each renderer appends slides to the supplied presentation; it must not create or save a separate deck itself.
5. Share layouts and formatting helpers across renderers: overview, image plus properties/findings, component table and continuation slide.
6. Resolve analysis and images through stable assembly/part IDs. Read one saved project/run revision per export.

Conceptual API:
```python
build_report(context, sections=["assembly", "monopart"], part_ids=None)
render_assembly(presentation, context)
render_monoparts(presentation, context, part_ids=None)
```
Choose a library compatible with the repository. For a Python backend, `python-pptx` with a reusable PowerPoint template is a suitable starting option. Keep library-specific code inside the presentation layer.

## Agent-bound tool
Expose a tool such as `generate_engineering_powerpoint` through the existing agent framework (use the project's current tool-binding mechanism).

- Enable the agent to call this tool when the user requests an engineering PowerPoint. Successful generation should make the downloadable artifact available in a seperate folder in the session

## Presentation rules
- Engineering detail, consistent 16:9 layout, readable typography and explicit units.
- Use editable PowerPoint text and tables. CAD views remain embedded images; preserve aspect ratio and avoid cropping geometry.
- Keep extracted geometric facts, inferred analysis and unresolved assumptions distinguishable.
- Use available schema fields; do not invent material, tolerances or other absent information.
- Split long findings/tables into continuation slides instead of truncating content or shrinking text indefinitely.
- Missing optional fields show an appropriate unavailable state or are omitted. Missing images produce a labelled placeholder and warning; invalid required data prevents export.
- Generate combined reports from saved data using the same renderers, rather than merging generated decks. Regeneration does not preserve manual edits to previous exports.

## Acceptance criteria
- Agent tool produces a downloadable assembly-and-monopart `.pptx` report from representative existing results.
- The assembly section includes only name, primary function, and description from the saved assembly JSON.
- The monopart section includes only name, part identification, and intrinsic summary from each distinct part.
- The assembly and each monopart include the saved `iso1` CAD image when available.

Deliver the exporter, both renderers, shared layouts/template, registered agent tool and a short usage note. Keep the interfaces open for future sequence, FfA and layout renderers.
