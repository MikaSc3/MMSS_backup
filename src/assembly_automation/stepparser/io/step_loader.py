"""XCAF STEP import with millimeter transfer and explicit instance placements."""

from collections import Counter
from pathlib import Path

from ..core.models import LoadedAssembly, PartDefinition, PartInstance


def make_compound(shapes):
    from OCC.Core.BRep import BRep_Builder
    from OCC.Core.TopoDS import TopoDS_Compound

    builder = BRep_Builder()
    compound = TopoDS_Compound()
    builder.MakeCompound(compound)
    for shape in shapes:
        builder.Add(compound, shape)
    return compound


def transform_matrix(location) -> list[list[float]]:
    transform = location.Transformation()
    return [[float(transform.Value(i, j)) for j in range(1, 5)] for i in range(1, 4)] + [[0., 0., 0., 1.]]


def load_step(path: str | Path) -> LoadedAssembly:
    from OCC.Core.IFSelect import IFSelect_RetDone
    from OCC.Core.STEPCAFControl import STEPCAFControl_Reader
    from OCC.Core.TCollection import TCollection_AsciiString
    from OCC.Core.TDF import TDF_Label, TDF_LabelSequence, TDF_Tool
    from OCC.Core.TDocStd import TDocStd_Document
    from OCC.Core.TopLoc import TopLoc_Location
    from OCC.Core.XCAFDoc import XCAFDoc_DocumentTool

    path = Path(path).resolve(strict=True)
    if path.suffix.lower() not in (".step", ".stp"):
        raise ValueError("Expected a .step or .stp file")
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise ValueError(f"STEP read failed: {path}")
    basic_reader = reader.ChangeReader()
    basic_reader.SetSystemLengthUnit(1.0)
    if abs(basic_reader.SystemLengthUnit() - 1.0) > 1e-12:
        raise ValueError("STEP transfer did not accept millimeter output units")
    document = TDocStd_Document("assembly-automation")
    if not reader.Transfer(document):
        raise ValueError("STEP transfer into XCAF failed")
    tool = XCAFDoc_DocumentTool.ShapeTool(document.Main())
    roots = TDF_LabelSequence()
    tool.GetFreeShapes(roots)
    if not roots.Length():
        raise ValueError("STEP contains no free shapes")
    definitions, instances = [], []
    by_definition, counts = {}, Counter()
    hierarchy = [{"assembly_id": "assy_001", "name": path.stem, "parent_id": None,
                  "assembly_ids": [], "instance_ids": []}]

    def label_id(label):
        entry = TCollection_AsciiString()
        TDF_Tool.Entry(label, entry)
        return entry.ToCString()

    def walk(label, parent_location, parent_record, source_path, active):
        entry = label_id(label)
        if entry in active:
            raise ValueError(f"Cyclic STEP definition reference: {entry}")
        if len(active) > 128:
            raise ValueError("STEP hierarchy exceeds supported nesting depth")
        current_path = source_path + [entry]
        if tool.IsReference(label):
            definition = TDF_Label()
            if not tool.GetReferredShape(label, definition):
                raise ValueError(f"Unresolved STEP reference: {entry}")
            walk(definition, parent_location.Multiplied(tool.GetLocation(label)),
                 parent_record, current_path, active | {entry})
            return
        shape = tool.GetShape(label)
        if shape.IsNull():
            raise ValueError(f"Null shape at STEP definition {entry}")
        location = parent_location.Multiplied(shape.Location())
        name = label.GetLabelName() or entry
        if tool.IsAssembly(label):
            record = {"assembly_id": f"assy_{len(hierarchy) + 1:03d}", "name": name,
                      "parent_id": parent_record["assembly_id"], "source_path": current_path,
                      "placement": transform_matrix(location), "assembly_ids": [], "instance_ids": []}
            parent_record["assembly_ids"].append(record["assembly_id"])
            hierarchy.append(record)
            components = TDF_LabelSequence()
            tool.GetComponents(label, components)
            if not components.Length():
                raise ValueError(f"Empty STEP assembly: {entry}")
            for index in range(1, components.Length() + 1):
                walk(components.Value(index), location, record, current_path, active | {entry})
            return
        if entry not in by_definition:
            part = PartDefinition(f"part_{len(definitions) + 1:03d}", name, entry,
                                  shape.Located(TopLoc_Location()))
            definitions.append(part)
            by_definition[entry] = part
        part = by_definition[entry]
        ordinal = counts[part.part_id]
        instance_id = part.part_id if ordinal == 0 else f"{part.part_id}_copy{ordinal}"
        counts[part.part_id] += 1
        instances.append(PartInstance(instance_id, part.part_id, name, parent_record["assembly_id"],
                                      current_path, location, part.shape.Located(location)))
        parent_record["instance_ids"].append(instance_id)

    for index in range(1, roots.Length() + 1):
        walk(roots.Value(index), TopLoc_Location(), hierarchy[0], [], set())
    if not instances:
        raise ValueError("STEP contains no part instances")
    return LoadedAssembly(path.stem, definitions, instances, hierarchy,
                          make_compound(i.shape for i in instances),
                          {"length": "mm", "area": "mm2", "volume": "mm3",
                           "normalization": "STEP reader SetSystemLengthUnit(1.0)"}, document)
