"""Typed persisted state used for agent capability eligibility."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class StaleArtifacts(BaseModel):
    assembly: bool = True
    monoparts: bool = True
    sequence: bool = True
    renderings: bool = True
    final: bool = True


class AgentSessionState(BaseModel):
    """Small agent projection; manifests remain the domain record."""

    # Ignore legacy keys during migration; the next write normalizes the file.
    model_config = ConfigDict(extra="ignore")

    active_sequence_revision: str | None = None
    active_assembly_revision: str | None = None
    active_monoparts_revision: str | None = None
    stale: StaleArtifacts = Field(default_factory=StaleArtifacts)
