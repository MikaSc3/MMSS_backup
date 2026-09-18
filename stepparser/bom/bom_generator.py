# ============================================
# src/bom/bom_generator.py
# ============================================
"""Deprecated.

Die BOM-Erzeugung wurde durch einen Export einer konsolidierten Parts-Tabelle
(CSV) aus Part-Metadaten ersetzt. Siehe `MetadataManager.save_parts_table()`.
"""

raise ImportError(
    "src.bom.bom_generator ist deprecated und wird nicht mehr unterstützt. "
    "Nutze stattdessen den Parts-CSV Export über MetadataManager.save_parts_table()."
)