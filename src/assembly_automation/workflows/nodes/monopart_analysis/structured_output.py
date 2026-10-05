"""Structured result owned by the monopart-analysis node."""

from pydantic import BaseModel, Field

class SinglePartAnalysis(BaseModel):
    geometric_characteristics: list[str] = Field(
        description=(
            "Up to 10 compact, feature-led bullets using 'Feature: description'. "
            "Start with the base body, then describe distinctive geometric features as precise as possible"
            "Describe shapes, arrangement, and geometric features like (flanges, bores, holes, chamfers, fillets, slots, bosses, tabs, lips, ridges etc.), and useful dimensions. "
            "Geometry only; no function or handling implications. "      
        )
    )

    part_identification: str = Field(
        description=(
            "One short statement of the part's best-supported assembly role. "
            "Target 6–14 words."
        )
    )

    part_name_guess: str = Field(
        description="One suitable engineering part name. Maximum 2 words."
    )

    material_and_mechanical_behavior: list[str] = Field(
        description=(
            "Up to 4 compact bullets: working material class, mechanical "
            "behavior, and damage-sensitive regions. State estimates directly; "
            "record consequential unverified premises in assumptions. "
            "Avoid unsupported material grades or precision requirements."
        )
    )

    bulk_behavior: list[str] = Field(
        description=(
            "Up to 3 compact bullets covering dominant loose-part interactions "
            "and singulation obstacles: nesting, interlocking, rolling, "
            "tangling, or overlap. Omit irrelevant behavior categories."
        )
    )

    magazine_behavior: list[str] = Field(
        description=(
            "Up to 3 compact bullets covering controlled support, stacking, "
            "orientation retention, or separator requirements."
        )
    )

    nature_of_provision_guess: list[str] = Field(
        description=(
            "1-2 bullet naming the preferred automation presentation "
            "and its decisive reason. This is a recommendation, not a claim "
            "about actual supplier packaging."
        )
    )

    orientation_analysis: list[str] = Field(default_factory=list,
        description=(
            "Up to 2 compact bullets: relevant resting or assembly orientations, "
            "symmetry-related ambiguity, and features resolving orientation. "
            "Do not assume every geometric difference matters functionally."
        )
    )

    handling_implications: list[str] = Field(
        description=(
            "Up to 2 compact bullets identifying useful placement references "
            "and decisive handling constraints. Do not repeat material risks, "
            "provision recommendations, or gripping strategies."
        )
    )

    gripping_analysis: list[str] = Field(
        description=(
            "Up to 3 credible strategies, strongest first. Each compact bullet "
            "names method and contact region; add the decisive feasibility "
            "condition when needed. Do not fill a quota with weak options."
        )
    )

    intrinsic_summary: list[str] = Field(
        description=(
            "Up to 4 compact bullets summarizing the part analysis."
        )
    )

    assumptions: list[str] = Field(default_factory=list,
        description=(
            "Up to 3 compact bullets recording consequential unverified "
            "premises behind material, function, sensitivity, or feasibility "
            "conclusions. Prioritize premises affecting automation decisions. "
            "Empty when no consequential assumptions were used."
        )
    )

    remarkforadmin: list[str] = Field(default_factory=list,
        description=(
            "Up to 10 short bullet statements for internal use only. "
            "Include any relevant information that may you help future analysis."
            "Use an empty list when none are relevant."
            "Are there problems in the prompt, provided data or anything?"
            "how can we help you improve the prompt or the data to get better results?"
        )
    )   





class SinglePartAnalysis_LEGACY(BaseModel):
    geometric_characteristics: list[str] = Field(description="Dominant shape, symmetry, dimensions and distinctive geometric features.")
    part_identification: str = Field(description="Likely task of the part in the assembly.")
    part_name_guess: str = Field(description="Short suitable part name. Max. 2 words.")
    material_and_mechanical_behavior: list[str] = Field(description="Likely material, sensitive surfaces, rigidity, deformation and damage risks, with evidence and uncertainty.")
    bulk_behavior: list[str] = Field(description="Tendency to interlock, nest, stack, roll or tangle and implications for bulk separation.")
    magazine_behavior: list[str] = Field(description="Stability, stackability, protection and separator requirements in magazines or load carriers.")
    nature_of_provision_guess: list[str] = Field(description="Most plausible real-world provision method based on bulk and magazine behaviour.")
    handling_implications: list[str] = Field(description="Intrinsic handling stability, alignment complexity and deformation, sensitivity risks.")
    gripping_analysis: list[str] = Field(description="Feasible gripping surfaces and strategies based on geometry characteristics and handling implications. Be aware of sensitive areas. Give 3 gripping strategies.")
    intrinsic_summary: list[str] = Field(description="Concise summary characteristics. Tackle: Geometry, material, most likely provision method, gripping possibilities.")


SCHEMAS = {"monopart_analysis_v1": SinglePartAnalysis}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown monopart-analysis schema: {schema_id}") from exc
