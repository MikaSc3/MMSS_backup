"""
BOM (Bill of Materials) Schema - Rudimentäre Version.

Diese Klasse repräsentiert die fusionierte Teileliste nach dem Merge BOM Node.
Der LLM entscheidet zwischen widersprüchlichen Vorhersagen aus Assembly- und Monopart-Analysen.
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class BOMEntry(BaseModel):
    """Einzelner BOM-Eintrag für ein Part."""

    part_id: str = Field(..., description="Unique Part ID (z.B. 'Part_1_unique')")
    part_name: str = Field(
        ..., description="Finaler Part-Name (LLM-Entscheidung aus Assembly vs. Monopart)"
    )
    part_type: Optional[str] = Field(
        None, description="Part-Typ (z.B. 'Bracket', 'Shaft', 'Housing')"
    )

    # Finale Material-Entscheidung (jeweils nur EIN Wert)
    material: str = Field(
        ..., description="Finales Material (z.B. 'Aluminium', 'Stahl', 'Kunststoff')"
    )
    material_certainty: int = Field(
        ..., ge=0, le=100, description="Confidence des LLM in die Material-Entscheidung"
    )

    # Geometrie-Daten (aus enriched monopart data)
    volume_mm3: Optional[float] = Field(
        None, description="Volumen in mm³ (aus STEP-Geometrie)"
    )
    surface_area_mm2: Optional[float] = Field(
        None, description="Oberfläche in mm² (aus STEP-Geometrie)"
    )
    bounding_box: Optional[Dict[str, float]] = Field(
        None, description="Bounding Box: {x_min, x_max, y_min, y_max, z_min, z_max}"
    )

    # Features (finale konsolidierte Liste)
    geometric_features: List[str] = Field(
        default_factory=list,
        description="Liste von Features (z.B. ['M8 Thread', 'Chamfer 1x45°', 'Bohrung Ø12mm'])",
    )

    # LLM-Reasoning (Transparenz)
    llm_reasoning: Optional[str] = Field(
        None,
        description="Begründung des LLM für Material-Entscheidung (Assembly vs. Monopart Context)",
    )
    alternative_materials: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Nicht-gewählte Material-Alternativen mit Certainty",
    )

    @field_validator("material_certainty")
    @classmethod
    def validate_certainty(cls, v: int) -> int:
        """Validiert Certainty-Wert (0-100)."""
        if not 0 <= v <= 100:
            raise ValueError(f"material_certainty muss 0-100 sein, ist {v}")
        return v


class BOM(BaseModel):
    """Bill of Materials - Finale Baugruppenliste nach Merge-Prozess."""

    assembly_name: str = Field(..., description="Name der Baugruppe (z.B. 'IPA_Cranfield')")
    total_parts: int = Field(..., description="Anzahl Parts in BOM", ge=0)

    entries: List[BOMEntry] = Field(
        default_factory=list, description="BOM-Einträge (Parts)"
    )

    # Metadaten
    created_from_experiment: Optional[str] = Field(
        None, description="Experiment-Name (z.B. 'exp1_baseline')"
    )
    llm_model: Optional[str] = Field(None, description="Verwendetes LLM-Modell")
    prompt_id: Optional[str] = Field(None, description="Verwendeter Prompt")

    @field_validator("entries")
    @classmethod
    def validate_entries_match_total(cls, v: List[BOMEntry], info) -> List[BOMEntry]:
        """Validiert, dass Anzahl Entries mit total_parts übereinstimmt."""
        if "total_parts" in info.data and len(v) != info.data["total_parts"]:
            raise ValueError(
                f"Anzahl Entries ({len(v)}) stimmt nicht mit total_parts ({info.data['total_parts']}) überein"
            )
        return v

    def get_entry_by_id(self, part_id: str) -> Optional[BOMEntry]:
        """Findet BOMEntry anhand Part ID."""
        for entry in self.entries:
            if entry.part_id == part_id:
                return entry
        return None

    @property
    def materials_used(self) -> Dict[str, int]:
        """Gibt Dictionary mit Materialien und deren Häufigkeit zurück."""
        materials: Dict[str, int] = {}
        for entry in self.entries:
            materials[entry.material] = materials.get(entry.material, 0) + 1
        return materials
