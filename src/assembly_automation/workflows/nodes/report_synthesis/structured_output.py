"""Structured output for the small, evidence-bound report synthesis call."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


Subprocess = Literal["separation", "handling", "positioning", "joining"]
Rating = Literal["high", "medium", "low"]


class SynthesizedFinding(BaseModel):
    finding_key: str = Field(pattern=r"^[a-z][a-z0-9_]{2,40}$")
    scope: Literal["assembly", "part", "step"]
    title: str = Field(min_length=3, max_length=100)
    statement: str = Field(min_length=10, max_length=600)
    severity: Rating
    confidence: Rating
    step_ids: list[int] = Field(default_factory=list)
    part_ids: list[str] = Field(default_factory=list)
    subprocesses: list[Subprocess] = Field(default_factory=list)
    source_refs: list[str] = Field(min_length=1)


class SynthesizedRecommendation(BaseModel):
    title: str = Field(min_length=3, max_length=100)
    action: str = Field(min_length=10, max_length=600)
    expected_effect: str = Field(min_length=5, max_length=400)
    priority: Rating
    origin: Literal["source_derived", "proposed_hypothesis"]
    addresses_findings: list[str] = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(default_factory=list)


class ReportInsights(BaseModel):
    executive_summary: list[str] = Field(min_length=1, max_length=5)
    findings: list[SynthesizedFinding] = Field(min_length=1, max_length=12)
    recommendations: list[SynthesizedRecommendation] = Field(min_length=1, max_length=12)

    @model_validator(mode="after")
    def references_known_finding_keys(self):
        keys = [item.finding_key for item in self.findings]
        if len(keys) != len(set(keys)):
            raise ValueError("finding_key values must be unique")
        known = set(keys)
        for recommendation in self.recommendations:
            unknown = set(recommendation.addresses_findings) - known
            if unknown:
                raise ValueError(f"recommendation references unknown finding keys: {sorted(unknown)}")
        return self


SCHEMAS = {"report_insights_v1": ReportInsights}


def get_schema(schema_id: str) -> type[BaseModel]:
    try:
        return SCHEMAS[schema_id]
    except KeyError as exc:
        raise ValueError(f"Unknown report-synthesis schema: {schema_id}") from exc
