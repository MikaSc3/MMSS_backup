"""Structured result owned by the monopart-analysis node."""

from pydantic import BaseModel, Field


class MonopartAnalysis(BaseModel):
    material_and_mechanical_behavior: str = Field(description="Likely material, sensitive surfaces, rigidity, deformation and damage risks, with evidence and uncertainty.")
    bulk_behavior: str = Field(description="Tendency to interlock, nest, stack, roll or tangle and implications for bulk separation.")
    magazine_behavior: str = Field(description="Stability, stackability, protection and separator requirements in magazines or load carriers.")
    nature_of_provision_guess: str = Field(description="Most plausible real-world provision method with concise reasoning.")
    geometric_characteristics: str = Field(description="Dominant shape, symmetry, dimensions and distinctive geometric features.")
    gripping_analysis: str = Field(description="Feasible gripping surfaces and strategies, orientation constraints and sensitive areas.")
    handling_implications: str = Field(description="Intrinsic handling stability, alignment complexity and deformation risks.")
    intrinsic_summary: str = Field(description="Concise summary of intrinsic automation-relevant characteristics.")


class SinglePartAnalysis(BaseModel):
    part_identification: str = Field(description="Likely task of the part in the assembly, with uncertainty where needed.")
    part_name_guess: str = Field(description="Short suitable part name.")
    part_color: str = Field(description="Rendered identification color, not inferred material.")
    monopart_analysis: MonopartAnalysis


SCHEMAS = {"monopart_analysis_v1": SinglePartAnalysis}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown monopart-analysis schema: {schema_id}") from exc
