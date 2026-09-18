import os
import json
from typing import Any, Dict

def round_nested(obj: Any, decimals: int = 3) -> Any:
    """Recursively round numerical values"""
    if isinstance(obj, dict):
        return {k: round_nested(v, decimals) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [round_nested(item, decimals) for item in obj]
    elif isinstance(obj, float):
        return 0.0 if abs(obj) < 1e-10 else round(obj, decimals)
    return obj


def save_json(path: str, data: Dict) -> None:
    """Save rounded data as JSON"""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf8") as f:
        json.dump(round_nested(data), f, indent=2, default=str)
    print(f"[DEBUG] Saved: {path}")