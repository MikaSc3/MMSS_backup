"""
FFA (Fitness for Automation) Schema - Vollständig mit allen 4 Subprozessen.

Diese Klasse repräsentiert die Automatisierungsbewertung nach dem FFA Assessment Node.
Das LLM muss für jedes Bewertungskriterium eine Auswahlmöglichkeit treffen.

Subprozesse:
1. Vereinzelung
2. Handhaben
3. Positionierung
4. Fügen
"""

from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, Field


# ============================================================================
# SUBPROZESS 1: VEREINZELUNG
# ============================================================================

class BereitstellungsartOption(str, Enum):
    """Auswahlmöglichkeiten für 'Art der Bereitstellung / Vereinzelbarkeit der Fügeteile'."""
    
    MAGAZINIERT_DEFINIERT = "magaziniert (definierte Position und Orientierung)"
    MAGAZINIERT_OHNE_DEFINITION = "magaziniert (ohne definierte Position oder Orientierung)"
    MAGAZINIERT_VERPACKUNGSPROBLEM = "magaziniert (Verpackungsproblem: Einzelverpackung oder haftende Zwischenlage)"
    MAGAZINIERT_ZWISCHENLAGE = "magaziniert (mit nicht haftender Zwischenlage)"
    SCHUETTGUT_EINFACH = "Schüttgut (einfach automatisierbar: z.B. Wendelförderer)"
    SCHUETTGUT_GRIFF_KISTE = "Schüttgut (mit 'Griff in die Kiste' automatisierbar)"
    SCHUETTGUT_NICHT_AUTO = "Schüttgut (nicht automatisierbar: z.B. Verhakung)"


class Vereinzelung(BaseModel):
    """Bewertung: Subprozess Vereinzelung."""
    
    bereitstellungsart: BereitstellungsartOption = Field(
        ..., 
        description="Art der Bereitstellung / Vereinzelbarkeit der Fügeteile"
    )
    reasoning: str = Field(..., description="Begründung für die Auswahl")
    evidence: Optional[List[str]] = Field(None, description="Belege aus BOM/Metadata")


# ============================================================================
# SUBPROZESS 2: HANDHABEN
# ============================================================================

class SteifigkeitOption(str, Enum):
    """Auswahlmöglichkeiten für Steifigkeit."""
    
    STARR = "starr"
    ELASTISCH = "elastisch"
    BIEGESCHLAFF = "biegeschlaff"


class GreifflaechenOption(str, Enum):
    """Auswahlmöglichkeiten für Greifflächen."""
    
    AUSGEPRAEGTE_GREIFFLAECHEN = "ausgeprägte Greifflächen vorhanden"
    KLEINE_GREIFFLAECHEN = "kleine Greifflächen vorhanden"
    KEINE_GREIFFLAECHEN = "keine Greifflächen vorhanden"


class OrientierungsmerkmaleOption(str, Enum):
    """Auswahlmöglichkeiten für Orientierungsmerkmale."""
    
    SELBSTAUSRICHTUNG = "Selbstausrichtung beim Schließen des Greifers"
    POSITIONSERFASSUNG = "Greifen basierend auf Positionserfassung des Bauteils erforderlich"
    AUSRICHTSTATION = "zusätzliche Ausrichtstation erforderlich"
    KEINE_MERKMALE = "keine Orientierungsmerkmale"


class OberflaechenempfindlichkeitOption(str, Enum):
    """Auswahlmöglichkeiten für Oberflächenempfindlichkeit."""
    
    UNEMPFINDLICH = "unempfindlich"
    EMPFINDLICH = "kratz-, bruch-, formempfindlich"


class Handhaben(BaseModel):
    """Bewertung: Subprozess Handhaben."""
    
    steifigkeit: SteifigkeitOption = Field(..., description="Steifigkeit der Bauteile")
    steifigkeit_reasoning: str = Field(..., description="Begründung für Steifigkeit-Auswahl")
    
    greifflaechen: GreifflaechenOption = Field(..., description="Verfügbarkeit von Greifflächen")
    greifflaechen_reasoning: str = Field(..., description="Begründung für Greifflächen-Auswahl")
    
    orientierungsmerkmale: OrientierungsmerkmaleOption = Field(..., description="Orientierungsmerkmale")
    orientierungsmerkmale_reasoning: str = Field(..., description="Begründung für Orientierungsmerkmale-Auswahl")
    
    oberflaechenempfindlichkeit: OberflaechenempfindlichkeitOption = Field(..., description="Oberflächenempfindlichkeit")
    oberflaechenempfindlichkeit_reasoning: str = Field(..., description="Begründung für Oberflächenempfindlichkeit-Auswahl")
    
    evidence: Optional[List[str]] = Field(None, description="Belege aus BOM/Metadata")


# ============================================================================
# SUBPROZESS 3: POSITIONIERUNG
# ============================================================================

class GenauigkeitZielpositionOption(str, Enum):
    """Auswahlmöglichkeiten für Genauigkeit Zielposition."""
    
    BEIDE_DEFINIERT = "Positionierung Basisteil definiert / Position Fügestelle definiert"
    BASISTEIL_DEFINIERT_FUEGESTELLE_TOLERANZ = "Positionierung Basisteil definiert / Position Fügestelle toleranzbehaftet"
    BASISTEIL_TOLERANZ_FUEGESTELLE_DEFINIERT = "Positionierung Basisteil toleranzbehaftet / Position Fügestelle definiert"
    BEIDE_TOLERANZ = "Positionierung Basisteil toleranzbehaftet / Position Fügestelle toleranzbehaftet"


class PositionierhilfenOption(str, Enum):
    """Auswahlmöglichkeiten für Positionierhilfen an den Bauteilen."""
    
    EINFUEHRSCHRAEGEN_UND_ANSCHLAEGE = "Einführschrägen und Endanschläge vorhanden"
    NUR_EINFUEHRSCHRAEGEN = "Einführschrägen vorhanden"
    NUR_ENDANSCHLAEGE = "Endanschläge vorhanden"
    KEINE_HILFEN = "keine Positionierhilfen vorhanden"


class OrientierungRotationOption(str, Enum):
    """Auswahlmöglichkeiten für zusätzliche Orientierung durch Rotation."""
    
    NICHT_BENOETIGT = "nicht benötigt"
    MECHANISCHE_FUEHRUNG = "mechanische Führung"
    OPTISCHE_INFO = "Bedarf optischer Informationen"
    NICHT_REALISIERBAR = "benötigt aber nicht realisierbar"


class ZugaenglichkeitOption(str, Enum):
    """Auswahlmöglichkeiten für Zugänglichkeit zur Fügestelle."""
    
    EINSEHBAR_WERKZEUGFREI = "Einsehbarkeit gegeben / Werkzeugfreiräume gegeben"
    NICHT_EINSEHBAR_WERKZEUGFREI = "Keine Einsehbarkeit / Werkzeugfreiräume gegeben"
    EINSEHBAR_KEIN_WERKZEUGFREIRAUM = "Einsehbarkeit gegeben / keine Werkzeugfreiräume gegeben"
    BLOCKIERT = "Keine Einsehbarkeit / keine Werkzeugfreiräume (z.B. blockiert durch Kabel, Schläuche etc.)"


class FuegebewegungOption(str, Enum):
    """Auswahlmöglichkeiten für Fügebewegung."""
    
    LINEAR = "lineare Fügebewegung"
    BAHNBEWEGUNG = "Bahnbewegung erforderlich"
    SENSOR_GEFUEHRT = "Sensor geführt (linear/Bahn)"


class FuegetoleranzOption(str, Enum):
    """Auswahlmöglichkeiten für Fügetoleranzen."""
    
    PLUS_MINUS_X_MM = "+/- x mm"
    PLUS_MINUS_0X_MM = "+/- 0,x mm"
    NULL_SPIEL = "\"0\"-Spiel"
    JUSTAGE_ERFORDERLICH = "Justage der Endposition nach Montage erforderlich"


class HaltestabilitaetOption(str, Enum):
    """Auswahlmöglichkeiten für Haltestabilität im positionierten Zustand."""
    
    SELBSTHALTEND = "stabil, selbsthaltend"
    HALTEN_ERFORDERLICH = "halten während des Fügeprozesses erforderlich"


class Positionierung(BaseModel):
    """Bewertung: Subprozess Positionierung."""
    
    genauigkeit_zielposition: GenauigkeitZielpositionOption = Field(..., description="Genauigkeit der Zielposition")
    genauigkeit_reasoning: str = Field(..., description="Begründung für Genauigkeits-Auswahl")
    
    positionierhilfen: PositionierhilfenOption = Field(..., description="Positionierhilfen an den Bauteilen")
    positionierhilfen_reasoning: str = Field(..., description="Begründung für Positionierhilfen-Auswahl")
    
    orientierung_rotation: OrientierungRotationOption = Field(..., description="Zusätzliche Orientierung durch Rotation")
    orientierung_reasoning: str = Field(..., description="Begründung für Orientierungs-Auswahl")
    
    zugaenglichkeit: ZugaenglichkeitOption = Field(..., description="Zugänglichkeit zur Fügestelle")
    zugaenglichkeit_reasoning: str = Field(..., description="Begründung für Zugänglichkeits-Auswahl")
    
    fuegebewegung: FuegebewegungOption = Field(..., description="Art der Fügebewegung")
    fuegebewegung_reasoning: str = Field(..., description="Begründung für Fügebewegung-Auswahl")
    
    fuegetoleranz: FuegetoleranzOption = Field(..., description="Fügetoleranzen")
    fuegetoleranz_reasoning: str = Field(..., description="Begründung für Fügetoleranz-Auswahl")
    
    haltestabilitaet: HaltestabilitaetOption = Field(..., description="Haltestabilität im positionierten Zustand")
    haltestabilitaet_reasoning: str = Field(..., description="Begründung für Haltestabilitäts-Auswahl")
    
    evidence: Optional[List[str]] = Field(None, description="Belege aus BOM/Metadata")


# ============================================================================
# SUBPROZESS 4: FÜGEN
# ============================================================================

class ZufuehrungVerbindungselementOption(str, Enum):
    """Auswahlmöglichkeiten für Zuführung des Verbindungselements."""
    
    NICHT_NOTWENDIG = "nicht notwendig"
    STANDARDLOESUNG = "Automatisierbar mit Standardlösung"
    EINGESCHRAENKT = "Eingeschränkte Zuführung (z.B. Zugänglichkeit)"
    SONDERENTWICKLUNG = "Automatisierbar mit Sonderentwicklung"
    NICHT_ABSEHBAR = "Sonderentwicklung, nicht absehbar"


class BefestigungOption(str, Enum):
    """Auswahlmöglichkeiten für Befestigung des Fügeteils."""
    
    STANDARDLOESUNG = "Automatisierbar mit Standardlösung"
    SONDERENTWICKLUNG = "Automatisierbar mit Sonderentwicklung"
    NICHT_ABSEHBAR = "Sonderentwicklung, nicht absehbar"


class Fuegen(BaseModel):
    """Bewertung: Subprozess Fügen."""
    
    zufuehrung_verbindungselement: ZufuehrungVerbindungselementOption = Field(
        ..., 
        description="Zuführung des Verbindungselements"
    )
    zufuehrung_reasoning: str = Field(..., description="Begründung für Zuführung-Auswahl")
    
    befestigung: BefestigungOption = Field(..., description="Befestigung des Fügeteils")
    befestigung_reasoning: str = Field(..., description="Begründung für Befestigung-Auswahl")
    
    evidence: Optional[List[str]] = Field(None, description="Belege aus BOM/Metadata")


# ============================================================================
# GESAMTBEWERTUNG
# ============================================================================

class APA_Bewertung(BaseModel):
    """
    Fitness for Automation Assessment - Gesamtbewertung aller 4 Subprozesse.
    
    Das LLM muss für jedes Bewertungskriterium eine Klassifikation vornehmen.
    """

    assembly_name: str = Field(..., description="Name der Baugruppe (z.B. 'IPA_Cranfield')")
    bom_reference: str = Field(
        ...,
        description="Pfad zur merged_bom.json (z.B. 'data/experiments/exp1/IPA_Cranfield/merged_bom.json')",
    )
    assembly_order_reference: Optional[str] = Field(
        None,
        description="Pfad zur assembly_order.json (z.B. 'data/input/assembly_order/IPA_Cranfield.json')",
    )

    # Bewertungen der 4 Subprozesse (ALLE PFLICHT)
    vereinzelung: Vereinzelung = Field(..., description="Bewertung Subprozess: Vereinzelung")
    handhaben: Handhaben = Field(..., description="Bewertung Subprozess: Handhaben")
    positionierung: Positionierung = Field(..., description="Bewertung Subprozess: Positionierung")
    fuegen: Fuegen = Field(..., description="Bewertung Subprozess: Fügen")

    # Gesamtbewertung und Zusammenfassung
    gesamtbewertung_text: str = Field(
        ..., 
        description="Zusammenfassende Bewertung der Automatisierbarkeit (2-3 Sätze)"
    )
    
    kritische_faktoren: List[str] = Field(
        default_factory=list,
        description="Haupthindernisse für Automation (z.B. ['Biegeschlaffe Bauteile', 'Keine Greifflächen', 'Komplexe Fügebewegung'])",
    )
    
    verbesserungsvorschlaege: List[str] = Field(
        default_factory=list,
        description="Wie könnte Automatisierbarkeit verbessert werden? (Design-Empfehlungen)",
    )
    
    automatisierbarkeit_score: Optional[int] = Field(
        None,
        ge=0,
        le=100,
        description="Gesamtscore 0-100% (optional, kann vom LLM geschätzt werden)"
    )

    # Metadaten
    llm_model: Optional[str] = Field(None, description="Verwendetes LLM-Modell")
    prompt_id: Optional[str] = Field(None, description="Verwendeter Prompt")
    experiment_name: Optional[str] = Field(
        None, description="Experiment-Name (z.B. 'exp1_baseline')"
    )



{
    "Subprozesse": [
    {
      "Subprozess": "Vereinzelung",
      "Bewertungskriterium": [
          "Art der Bereitstellung / Vereinzelbarkeit der Fügeteile"
      ],
      "Auswahlmöglichkeiten": {
        "Art der Bereitstellung / Vereinzelbarkeit der Fügeteile": [
        "magaziniert (definierte Position und Orientierung)",
        "magaziniert (ohne definierte Position oder Orientierung)",
        "magaziniert (Verpackungsproblem: Einzelverpackung oder haftende Zwischenlage)",
        "magaziniert (mit nicht haftender Zwischenlage)",
        "Schüttgut (einfach automatisierbar: z.B. Wendelförderer)",
        "Schüttgut (mit 'Griff in die Kiste' automatisierbar)",
        "Schüttgut (nicht automatisierbar: z.B. Verhakung)"
        ],
      }
    },
    {
      "Subprozess": "Handhaben",
      "Bewertungskriterium": [
        "Steifigkeit",
        "Greifflächen",
        "Orientierungsmerkmale",
        "Oberflächenempfindlichkeit"
      ],
      "Auswahlmöglichkeiten": {
        "Steifigkeit": [
          "starr",
          "elastisch",
          "biegeschlaff"
        ],
        "Greifflächen": [
          "ausgeprägte Greifflächen vorhanden",
          "kleine Greifflächen vorhanden",
          "keine Greifflächen vorhanden"
        ],
        "Orientierungsmerkmale": [
          "Selbstausrichtung beim Schließen des Greifers",
          "Greifen basierend auf Positionserfassung des Bauteils erforderlich",
          "zusätzliche Ausrichtstation erforderlich",
          "keine Orientierungsmerkmale"
        ],
        "Oberflächenempfindlichkeit": [
          "unempfindlich",
          "kratz-, bruch-, formempfindlich"
        ]
      }
    },
    {
      "Subprozess": "Positionierung",
      "Bewertungskriterium": [
        "Genauigkeit Zielposition",
        "Positionierhilfen an den Bauteilen",
        "Zusätzliche Orientierung durch Rotation",
        "Zugänglichkeit zur Fügestelle",
        "Fügebewegung",
        "Fügetoleranzen",
        "Haltestabilität im positionierten Zustand"
      ],
      "Auswahlmöglichkeiten": {
        "Genauigkeit Zielposition": [
          "Positionierung Basisteil definiert / Position Fügestelle definiert",
          "Positionierung Basisteil definiert / Position Fügestelle toleranzbehaftet",
          "Positionierung Basisteil toleranzbehaftet / Position Fügestelle definiert",
          "Positionierung Basisteil toleranzbehaftet / Position Fügestelle toleranzbehaftet"
        ],
        "Positionierhilfen an den Bauteilen": [
          "Einführschrägen und Endanschläge vorhanden",
          "Einführschrägen vorhanden",
          "Endanschläge vorhanden",
          "keine Positionierhilfen vorhanden"
        ],
        "Zusätzliche Orientierung durch Rotation": [
          "nicht benötigt",
          "mechanische Führung",
          "Bedarf optischer Informationen",
          "benötigt aber nicht realisierbar"
        ],
        "Zugänglichkeit zur Fügestelle": [
          "Einsehbarkeit gegeben / Werkzeugfreiräume gegeben",
          "Keine Einsehbarkeit / Werkzeugfreiräume gegeben",
          "Einsehbarkeit gegeben / keine Werkzeugfreiräume gegeben",
          "Keine Einsehbarkeit / keine Werkzeugfreiräume (z.B. blockiert durch Kabel, Schläuche etc.)"
        ],
        "Fügebewegung": [
          "lineare Fügebewegung",
          "Bahnbewegung erforderlich",
          "Sensor geführt (linear/Bahn)"
        ],
        "Fügetoleranzen": [
          "+/- x mm",
          "+/- 0,x mm",
          "\"0\"-Spiel",
          "Justage der Endposition nach Montage erforderlich"
        ],
        "Haltestabilität im positionierten Zustand": [
          "stabil, selbsthaltend",
          "halten während des Fügeprozesses erforderlich"
        ]
      }
    },
    {
      "Subprozess": "Fügen",
      "Bewertungskriterium": [
        "Zuführung des Verbindungselements",
        "Befestigung des Fügeteils"
      ],
      "Auswahlmöglichkeiten": {
        "Zuführung des Verbindungselements": [
          "nicht notwendig",
          "Automatisierbar mit Standardlösung",
          "Eingeschränkte Zuführung (z.B. Zugänglichkeit)",
          "Automatisierbar mit Sonderentwicklung",
          "Sonderentwicklung, nicht absehbar"
        ],
        "Befestigung des Fügeteils": [
          "Automatisierbar mit Standardlösung",
          "Automatisierbar mit Sonderentwicklung",
          "Sonderentwicklung, nicht absehbar"
        ]
      }
    }
  ]
}
