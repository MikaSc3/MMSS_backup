"""Structured result owned by the assembly-analysis node."""

from pydantic import BaseModel, Field


from pydantic import BaseModel, Field


class AssemblyComponent(BaseModel):
    instance_ids: list[str] = Field(
        description=(
            "Exact supplied instance identifiers represented by this entry. "
            "Group instances only when geometry and assembly role match. "
            "Quantity is derived from this list."
        )
    )

    name: str = Field(
        description=(
            "Short engineering component name. Prefer a conservative geometric "
            "name when the functional identity is uncertain."
        )
    )

    rendered_color: str | None = Field(
        description=(
            "Visible render color used for identification, or null if unclear. "
            "Does not indicate material."
        )
    )

    geometry: list[str] = Field(
        description=(
            "1–3 short bullet statements describing distinctive geometry. "
            "Include dimensions only when useful for interpretation. "
            "Do not attempt a complete individual-part analysis."
        )
    )

    assembly_role: list[str] = Field(
        description=(
            "1–3 short bullet statements explaining this component's role "
            "within the assembly. Qualify inferred functions locally."
        )
    )


class AssemblyInterface(BaseModel):
    instance_ids: list[str] = Field(
        description=(
            "Exact supplied instance identifiers participating in this interface. "
            "For an external interface, include only the modeled participants."
        )
    )

    statements: list[str] = Field(
        description=(
            "1–2 short bullet statements identifying the mating features "
            "and their supported or likely mechanical relationship. "
            "For an external interface, name the external connection in the text. "
            "Distinguish proximity from contact and retention from preload. "
            "Do not repeat component geometry or assembly roles."
        )
    )


class AssemblyAnalysis(BaseModel):
    
    assembly_description: str = Field(
        description=(
            "One short sentence describing the overall assembly architecture. "
            "Target no more than 35 words. Avoid component-by-component detail."
        )
    )    

    primary_function: list[str] = Field(
        description=(
            "1–2 short bullet statements describing the assembly's most likely "
            "primary purpose. Qualify uncertainty where needed."
        )
    )

    partslist: list[AssemblyComponent] = Field(
        description=(
            "Components represented in the supplied assembly. Preserve exact "
            "instance identifiers and group equivalent repeated instances."
        )
    )
    
    assembly_name_guess: str = Field(
        description=(
            "One short engineering assembly name, preferably no more than 3 words. Reflect the best-supported interpretation."
        )
    )

    interfaces: list[AssemblyInterface] = Field(default_factory=list,
        description=(
            "Important internal and external mechanical interfaces needed "
            "to understand the assembly and interpret individual components. "
            "Group equivalent interfaces where useful; omit incidental proximity."
        )
    )

    uncertainties: list[str] = Field(default_factory=list,
        description=(
            "Up to 3 short bullet statements describing unresolved issues "
            "that materially affect functional or individual-part interpretation. "
            "Use an empty list when none are relevant. Avoid generic caveats."
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






class AssemblyAnalysisLEGACY(BaseModel):
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
