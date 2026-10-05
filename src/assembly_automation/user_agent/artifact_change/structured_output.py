"""Structured output for a schema-preserving whole-artifact rewrite."""

from pydantic import BaseModel, Field

class ArtifactRewrite(BaseModel):
    artifact_json: str = Field(
        min_length=2,
        description=(
            "The complete replacement artifact encoded as one valid JSON object string. "
            "Preserve the full schema and all unaffected content while applying the "
            "requested correction everywhere it is relevant."
        ))
    changed_locations: list[str] = Field(
        min_length=1,
        description="Concise JSON-style locations changed in the replacement artifact.")
    summary: str = Field(
        min_length=1,
        description="Concise past-tense summary of the correction applied.")


SCHEMAS = {
    "artifact_change_v1": ArtifactRewrite,
    "artifact_rewrite_v1": ArtifactRewrite,
}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown artifact-change schema: {schema_id}") from exc
