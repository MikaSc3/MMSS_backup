# Automatisierungsplaner Spec

Stand: 2026-08-03

## Ziel

Der Automatisierungsplaner erweitert App Workflow V3 nach der vorhandenen FfA-Bewertung. Er nutzt die bereits erzeugten Session-Artefakte als technische Informationsbasis und plant daraus Automatisierungskonzepte, Variantenbewertungen, Stationskonzepte und detaillierte Montageplatzkonzepte.

Die initiale Testphase laeuft im Terminal auf einer vorhandenen `data/sessions_v3/...` Session. Der bestehende V3 Workflow bleibt unveraendert die Nutzerschnittstelle fuer STEP-Analyse, Sequenzdialog und FfA-Report.

## Position Im Bestehenden Workflow

Einstiegspunkt:

```text
App Workflow V3
  -> FfA report fertig
  -> Automatisierungsplaner
```

Der Planer ist ein Downstream-Workflow. Er rechnet keine CAD-Preprocessing-, Sequenz-, Interaktions- oder FfA-Knoten erneut. Stattdessen liest er:

```text
session_root/
  assembly_{assembly_name}_Overview_Enriched.json
  {assembly_name}_BOM_enriched.json
  enriched_parts/*_Data_enriched*.json
  assembly_sequence_runN/assembly_sequence.json
  assembly_sequence_runN/interaction_analysis.json
  ffa_assessment/ffa_assessment.json
  ffa_report/*_ffa_report.json
  Agent_txt_files/additional_context_block.md
```

Der aktuelle Test-Launcher ist:

```powershell
python 9_run_automationplanner_on_session.py
```

Der Session-Pfad ist oben im Script editierbar.

## Ausgabestruktur

Alle Ergebnisse werden in die aktive Session geschrieben:

```text
session_root/
  automation_planner/
    01_initiale_anforderungsklaerung.json
    02_prozessprinzipien/
      step_001_prozessprinzipien.json
      step_002_prozessprinzipien.json
    03_automatisierungsvarianten/
      variante_manuell.json
      variante_halbautomatisiert.json
      variante_vollautomatisiert.json
    04_variantenbewertungen/
      bewertung_manuell.json
      bewertung_halbautomatisiert.json
      bewertung_vollautomatisiert.json
    05_stationsplanung/
      stationskonzept_{strategie}.json
    06_montageplatzgestaltung/
      station_001_{strategie}.json
      detailliertes_anlagenkonzept_{strategie}.json
    automation_planner_summary.md
```

## Modulschnittstellen

### Modul 1: Initiale Anforderungsklaerung

Eingabe:

- `assembly_sequence.json`
- `*_Data_enriched*.json` fuer relevante Fuegeteile
- `*_ffa_report.json`
- Separation-Klassifikation aus `ffa_assessment.json`

Ausgabe:

- `InitialeAnforderungsklaerung`
- je Montageschritt: Basisteil, Fuegeteil, angenommene Bereitstellungsart, qualitative FfA, technische Risiken, Nutzerbestaetigungsbedarf

Integration:

- spaeter im V3 Agentendialog vor Modul 2 praesentieren
- Nutzerfeedback als Textkontext `automation_user_feedback` an Modul 2 uebergeben

### Modul 2: Prozessprinzip-Generator

Eingabe je Montageschritt:

- genau ein Sequenzschritt aus `assembly_sequence.json`
- passender Abschnitt aus `ffa_report`
- passender Abschnitt aus `ffa_assessment.json`
- passender Abschnitt aus `interaction_analysis.json`
- Einzelteilanalysen von Basis- und Fuegeteil
- bestaetigte oder angenommene Bereitstellungsart
- optionales Nutzerfeedback

Ausgabe:

- `ProzessprinzipErgebnis`
- drei Prozessprinzipien: `manuell`, `halbautomatisiert`, `vollautomatisiert`

Integration:

- spaeter als V3 Tool `Generate_Process_Principles_tool`
- bei Nutzerkorrektur nur betroffene Montageschritte erneut ausfuehren

### Modul 3: Automatisierungsvarianten-Generator

Eingabe:

- alle Prozessprinzipien einer Strategie
- verbindliche Montagereihenfolge

Ausgabe:

- `AutomatisierungsGesamtkonzept` je Strategie

Integration:

- wird dreimal aufgerufen
- Varianten sind Kandidaten fuer Agentenpraesentation und Nutzerwahl

### Modul 4: Variantenbewerter

Eingabe:

- ein Gesamtkonzept
- vollstaendiger FfA-Report

Ausgabe:

- `Variantenbewertung`

Integration:

- bewertet alle drei Varianten
- Agent praesentiert Staerken, Risiken, offene Punkte und Empfehlung

### Modul 5: Stationsplaner

Eingabe:

- eine ausgewaehlte und bewertete Variante
- Montagereihenfolge
- Prozessprinzipien und Produktinformationen

Ausgabe:

- `Stationskonzept`

Integration:

- in Testphase werden alle drei Strategien getrennt geplant
- spaeter waehlt der Nutzer eine, mehrere oder alle Varianten im V3 Dialog

### Modul 6: Montageplatzgestalter

Eingabe:

- genau eine Station aus dem Stationsplaner

Ausgabe:

- `DetailliertesStationskonzept` je Station
- aggregiertes `DetailliertesAnlagenkonzept`

Integration:

- ein LLM-Aufruf je Station
- Aggregation deterministisch im Planer-Modul

## Code-Integration

Neue additive Dateien:

```text
agent/automation_planner.py
9_run_automationplanner_on_session.py
docs/Automatisierungsplaner.spec.md
```

Erweiterte bestehende Dateien:

```text
agent/structured_output.py
configs/prompts.yaml
```

Der Planer verwendet die bestehenden Prompt- und LLM-Muster:

- Prompt-IDs in `configs/prompts.yaml`
- strukturierte Ausgabe ueber `llm.with_structured_output(...)`
- LLM-Erzeugung ueber bestehende Helper aus `agent.tools`

## Geplante V3 Tool-Grenzen

Spaetere App-V3-Tools:

```text
Prepare_Automation_Requirements_tool
Generate_Process_Principles_tool
Generate_Automation_Variants_tool
Evaluate_Automation_Variants_tool
Plan_Stations_tool
Design_Workplaces_tool
Finish_Automation_Planning_tool
```

Terminal-Testphase:

- deterministischer Python-Orchestrator
- keine Streamlit-Abhaengigkeit
- schreibt alle Zwischenergebnisse als JSON
- liest Nutzerfeedback optional aus CLI-Argument oder Textdatei
- plant Stations- und Montageplatzkonzepte fuer alle drei Strategien sauber getrennt

## Geklaerte Designentscheidungen

1. Die angenommene Bereitstellungsart in Modul 1 darf die FfA-Separation-Klassifikation direkt als vorrangige Quelle verwenden. Die Monopart-Analyse dient als Ergaenzung und Begruendung.
2. Die qualitative FfA pro Schritt wird aus dem FfA-Report uebernommen. Es wird keine zusaetzliche Subprozess-Bewertung fuer die Nutzeransicht erzeugt.
3. Der halbautomatisierte Ansatz bedeutet minimal sinnvolle Automatisierung: Subprozesse mit hoher und mittlerer FfA werden bevorzugt automatisiert, geringe FfA bleibt manuell oder manuell mit technischer Unterstuetzung.
4. In der Terminal-Testphase werden alle drei Strategien in Stationsplanung und Montageplatzgestaltung durchgeplant und sauber getrennt gespeichert.
5. Nutzerkorrekturen zur Teilebereitstellung muessen in der Testphase nicht persistent in der Session gespeichert werden.
6. Equipment-Bezeichnungen sollen so konkret wie moeglich sein, also bevorzugt industrielle Loesungsprinzipien statt nur generische Klassen.
