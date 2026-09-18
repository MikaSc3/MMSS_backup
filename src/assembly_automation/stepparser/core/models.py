from dataclasses import dataclass, field
from typing import Any


@dataclass
class PartDefinition:
    part_id: str
    name: str
    source_definition: str
    shape: Any
    validity: dict = field(default_factory=dict)
    geometry: dict = field(default_factory=dict)
    color: list[int] = field(default_factory=list)


@dataclass
class PartInstance:
    instance_id: str
    part_id: str
    name: str
    assembly_id: str
    source_path: list[str]
    location: Any
    shape: Any
    color: list[int] = field(default_factory=list)


@dataclass
class LoadedAssembly:
    name: str
    definitions: list[PartDefinition]
    instances: list[PartInstance]
    hierarchy: list[dict]
    shape: Any
    units: dict
    document: Any = None  # Keep the XCAF document alive during processing.
