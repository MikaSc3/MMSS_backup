"""Structured result owned by the assembly-analysis node."""

from pydantic import BaseModel, Field


class AssemblyAnalysis(BaseModel):
    assembly_description: str = Field(
        description="Concise engineering description grounded in supplied CAD evidence."
    )
    partslist: str = Field(
        description="Bullet list of identifiable parts with likely name, function and rendered color."
    )
    assembly_name_guess: str = Field(
        description="One short, suitable name for the assembly."
    )
    primary_function: str = Field(
        description="Concise description of the assembly's likely primary function."
    )


SCHEMAS = {"assembly_analysis_v1": AssemblyAnalysis}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown assembly-analysis schema: {schema_id}") from exc
