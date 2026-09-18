"""
Core Business Logic für APA_from_CAD.

Enthält:
- text_processor: Laden von Additional Info TXT-Dateien
- (später) image_processor, json_processor, assembly_order_loader
"""

from agent.core.text_processor import load_additional_info

__all__ = ["load_additional_info"]
