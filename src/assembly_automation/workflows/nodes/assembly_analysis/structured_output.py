"""Structured result owned by the assembly-analysis node."""

from pydantic import BaseModel, Field


class AssemblyAnalysis(BaseModel):
    partslist: list[str] = Field(
    description="Identifiable parts with likely name, rendered color, function, function within the assembly and quantity. Words over sentences. "
    )

    assembly_description: list[str] = Field(
        description="Concise engineering description of the assembly grounded in supplied CAD evidence. "
    )
    assembly_name_guess: list[str] = Field(
        description="One short, suitable name for the assembly. Max 3 words."
    )
    primary_function: list[str] = Field(
        description="Most likely primary function of the assembly."
    )


SCHEMAS = {"assembly_analysis_v1": AssemblyAnalysis}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown assembly-analysis schema: {schema_id}") from exc
