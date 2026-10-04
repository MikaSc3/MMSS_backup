"""Structured result owned by the monopart-analysis node."""

from pydantic import BaseModel, Field


class SinglePartAnalysis(BaseModel):
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
