"""Structured output for one semantic artifact change."""

from pydantic import BaseModel, Field


class FieldEdit(BaseModel):
    field: str = Field(description="One exact field name from the supplied editable-field list.")
    new_value: str = Field(description="Complete replacement text incorporating the correction.")
    reason: str = Field(description="Short explanation connecting this edit to the user's statement.")


class ArtifactChangePlan(BaseModel):
    edits: list[FieldEdit] = Field(min_length=1, description="Only the fields necessary for the correction.")
    summary: str = Field(description="Concise past-tense summary of what was changed.")


SCHEMAS = {"artifact_change_v1": ArtifactChangePlan}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown artifact-change schema: {schema_id}") from exc
