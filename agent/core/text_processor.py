"""
Text Processor - Lädt zusätzliche User-bereitgestellte Informationen.

Feature: Additional Assembly Info
- User kann optional .txt Dateien in data/input/Additional_info/ ablegen
- Name-Matching: IPA_Cranfield.STEP → IPA_Cranfield.txt
- Wenn keine Datei gefunden: Kein Fehler, gibt leeren String zurück
"""

import logging
import os
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def load_additional_info(
    assembly_name: str,
    textbased_data_root: Path = Path("data/input/Textbased_Data"),
) -> Optional[str]:
    """
    Lädt zusätzliche User-Informationen für eine Assembly.

    Sucht nach {assembly_name}/additional_info_{assembly_name}.txt in textbased_data_root.
    Falls gefunden: Gibt Text-Inhalt zurück.
    Falls nicht gefunden: Gibt None zurück (kein Fehler).

    Args:
        assembly_name: Name der Assembly (z.B. 'IPA_Cranfield', 'Gearbox')
        textbased_data_root: Pfad zum Textbased_Data Ordner (default: data/input/Textbased_Data/)

    Returns:
        str: Inhalt der .txt Datei, falls vorhanden
        None: Falls keine Datei gefunden (kein Fehler)

    Example:
        >>> info = load_additional_info("IPA_Cranfield")
        >>> if info:
        ...     print(f"User-Info: {info[:100]}...")
        ... else:
        ...     print("Keine zusätzlichen Infos vorhanden")
    """
    # Entferne .STEP Extension falls vorhanden
    clean_name = assembly_name.replace(".STEP", "").replace(".step", "")

    workspace_root = Path(__file__).resolve().parents[2]
    search_roots = []

    # Preferred for ASGT/evaluation runs: GT sequence folder can carry both
    # sequence.json and additional_info_{assembly}.txt side by side.
    env_gt_root = os.environ.get("APA_GROUND_TRUTH_SEQUENCE_ROOT")
    if env_gt_root:
        env_path = Path(env_gt_root)
        search_roots.append(env_path if env_path.is_absolute() else workspace_root / env_path)
    search_roots.append(workspace_root / "data" / "ground_truth" / "assembly_sequence_ground_truth")
    search_roots.append(textbased_data_root)

    txt_path = None
    for root in search_roots:
        candidate = root / clean_name / f"additional_info_{clean_name}.txt"
        if candidate.exists():
            txt_path = candidate
            break

    if txt_path is None:
        logger.debug(
            "no_additional_info_found",
            assembly_name=assembly_name,
            expected_path=str(search_roots[-1] / clean_name / f"additional_info_{clean_name}.txt"),
        )
        return None

    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        logger.info(
            "additional_info_loaded",
            assembly_name=assembly_name,
            txt_path=str(txt_path),
            content_length=len(content),
        )
        return content

    except Exception as e:
        logger.warning(
            "failed_to_load_additional_info",
            assembly_name=assembly_name,
            txt_path=str(txt_path),
            error=str(e),
        )
        return None


def load_assembly_order(
    assembly_name: str,
    textbased_data_root: Path = Path("data/input/Textbased_Data"),
) -> Optional[str]:
    """
    Lädt Assembly Sequence (vormals assembly_order) für eine Assembly.

    Sucht nach {assembly_name}/assembly_sequence_{assembly_name}.txt in textbased_data_root.
    Falls gefunden: Gibt Text-Inhalt zurück.
    Falls nicht gefunden: Gibt None zurück (kein Fehler).

    Args:
        assembly_name: Name der Assembly (z.B. 'IPA_Cranfield')
        textbased_data_root: Pfad zum Textbased_Data Ordner (default: data/input/Textbased_Data/)

    Returns:
        str: Inhalt der .txt Datei, falls vorhanden
        None: Falls keine Datei gefunden
    """
    # Entferne .STEP Extension falls vorhanden
    clean_name = assembly_name.replace(".STEP", "").replace(".step", "")

    # Konstruiere Pfad zu TXT-Datei: Textbased_Data/{assembly_name}/assembly_sequence_{assembly_name}.txt
    txt_path = textbased_data_root / clean_name / f"assembly_sequence_{clean_name}.txt"

    if not txt_path.exists():
        logger.debug(
            "no_assembly_sequence_found",
            assembly_name=assembly_name,
            expected_path=str(txt_path),
        )
        return None

    try:
        with open(txt_path, "r", encoding="utf-8") as f:
            content = f.read().strip()

        logger.info(
            "assembly_sequence_loaded",
            assembly_name=assembly_name,
            txt_path=str(txt_path),
            content_length=len(content),
        )
        return content

    except Exception as e:
        logger.warning(
            "failed_to_load_assembly_sequence",
            assembly_name=assembly_name,
            txt_path=str(txt_path),
            error=str(e),
        )
        return None
