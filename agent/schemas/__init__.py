"""
Pydantic Schemas für APA_from_CAD Workflow.

Enthält:
- BOM (Bill of Materials) - Fusionierte Teileliste
- FFA (Fitness for Automation) - Automatisierungsbewertung
"""

from agent.schemas.bom import BOM, BOMEntry
from agent.schemas.ffa import (
    APA_Bewertung,
    FFAKategorie,
    FFAKriterium,
    VerbindungselementeOption,
)

__all__ = [
    "BOM",
    "BOMEntry",
    "APA_Bewertung",
    "FFAKategorie",
    "FFAKriterium",
    "VerbindungselementeOption",
]
