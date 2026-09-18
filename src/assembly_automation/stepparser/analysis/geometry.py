"""Geometry measurements with full precision and explicit coordinate frames."""

from collections import Counter


def xyz(point) -> list[float]:
    return [float(point.X()), float(point.Y()), float(point.Z())]


def validate_shape(shape) -> dict:
    from OCC.Core.BRepCheck import BRepCheck_Analyzer

    if shape.IsNull():
        return {"status": "invalid", "is_valid": False, "reason": "null_shape"}
    valid = bool(BRepCheck_Analyzer(shape).IsValid())
    return {"status": "valid" if valid else "invalid", "is_valid": valid,
            "method": "BRepCheck_Analyzer", "healing_applied": False}


def bounding_box(shape) -> dict:
    from OCC.Core.Bnd import Bnd_Box
    from OCC.Core.BRepBndLib import brepbndlib

    box = Bnd_Box()
    brepbndlib.AddOptimal(shape, box, False, False)
    if box.IsVoid() or box.IsWhole():
        raise ValueError("Shape has no finite bounding box")
    limits = list(map(float, box.Get()))
    low, high = limits[:3], limits[3:]
    return {"min": low, "max": high,
            "dimensions": [b - a for a, b in zip(low, high)],
            "center": [(a + b) / 2 for a, b in zip(low, high)]}


def oriented_box(shape) -> dict:
    from OCC.Core.Bnd import Bnd_OBB
    from OCC.Core.BRepBndLib import brepbndlib

    box = Bnd_OBB()
    brepbndlib.AddOBB(shape, box, False, True, False)
    if box.IsVoid():
        raise ValueError("Shape has no oriented bounding box")
    return {"center": xyz(box.Center()),
            "axes": [xyz(box.XDirection()), xyz(box.YDirection()), xyz(box.ZDirection())],
            "dimensions": [2 * box.XHSize(), 2 * box.YHSize(), 2 * box.ZHSize()],
            "status": "complete", "method": "BRepBndLib.AddOBB"}


def _topology_counts(shape):
    from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE, TopAbs_EDGE, TopAbs_VERTEX
    from OCC.Core.TopExp import topexp
    from OCC.Core.TopTools import TopTools_IndexedMapOfShape

    result = {}
    for name, kind in (("solids", TopAbs_SOLID), ("shells", TopAbs_SHELL),
                       ("faces", TopAbs_FACE), ("edges", TopAbs_EDGE), ("vertices", TopAbs_VERTEX)):
        mapping = TopTools_IndexedMapOfShape()
        topexp.MapShapes(shape, kind, mapping)
        result[name] = mapping.Size()
    return result


def _properties(shape, kind):
    from OCC.Core.BRepGProp import brepgprop
    from OCC.Core.GProp import GProp_GProps

    props = GProp_GProps()
    if kind == "volume":
        brepgprop.VolumeProperties(shape, props, True)
    else:
        brepgprop.SurfaceProperties(shape, props)
    return props


def surface_details(shape) -> list[dict]:
    from OCC.Core.BRepAdaptor import BRepAdaptor_Surface
    from OCC.Core.GeomAbs import (GeomAbs_Plane, GeomAbs_Cylinder, GeomAbs_Cone,
                                  GeomAbs_Sphere, GeomAbs_Torus, GeomAbs_BSplineSurface,
                                  GeomAbs_BezierSurface)
    from OCC.Core.TopAbs import TopAbs_FACE
    from OCC.Core.TopExp import TopExp_Explorer
    from OCC.Core.TopoDS import topods

    names = {GeomAbs_Plane: "plane", GeomAbs_Cylinder: "cylinder", GeomAbs_Cone: "cone",
             GeomAbs_Sphere: "sphere", GeomAbs_Torus: "torus",
             GeomAbs_BSplineSurface: "bspline", GeomAbs_BezierSurface: "bezier"}
    faces = []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = topods.Face(explorer.Current())
        adaptor = BRepAdaptor_Surface(face)
        kind = adaptor.GetType()
        props = _properties(face, "surface")
        record = {"face_id": f"face_{len(faces) + 1:04d}", "type": names.get(kind, "other"),
                  "area": float(props.Mass()), "centroid": xyz(props.CentreOfMass()),
                  "orientation": int(face.Orientation()), "bounding_box": bounding_box(face)}
        if kind == GeomAbs_Plane:
            plane = adaptor.Plane()
            record["plane"] = {"origin": xyz(plane.Location()), "axis_direction": xyz(plane.Axis().Direction())}
        elif kind == GeomAbs_Cylinder:
            cylinder = adaptor.Cylinder()
            record["cylinder"] = {"radius": float(cylinder.Radius()),
                                  "axis_origin": xyz(cylinder.Location()),
                                  "axis_direction": xyz(cylinder.Axis().Direction()),
                                  "axial_parameter_range": [adaptor.FirstVParameter(), adaptor.LastVParameter()]}
        elif kind == GeomAbs_Cone:
            cone = adaptor.Cone()
            record["cone"] = {"apex": xyz(cone.Apex()), "semi_angle_radians": cone.SemiAngle(),
                              "reference_radius": cone.RefRadius(), "axis_direction": xyz(cone.Axis().Direction())}
        elif kind == GeomAbs_Sphere:
            sphere = adaptor.Sphere()
            record["sphere"] = {"center": xyz(sphere.Location()), "radius": sphere.Radius()}
        elif kind == GeomAbs_Torus:
            torus = adaptor.Torus()
            record["torus"] = {"center": xyz(torus.Location()), "major_radius": torus.MajorRadius(),
                               "minor_radius": torus.MinorRadius(), "axis_direction": xyz(torus.Axis().Direction())}
        faces.append(record)
        explorer.Next()
    return faces


def measure_shape(shape, *, detailed: bool = True, coordinate_frame: str = "part_local") -> dict:
    counts = _topology_counts(shape)
    surface = _properties(shape, "surface")
    volume = _properties(shape, "volume") if counts["solids"] else None
    mass = float(volume.Mass()) if volume else None
    result = {"status": "complete", "coordinate_frame": coordinate_frame,
              "volume": mass, "volume_status": "complete" if volume else "not_a_solid",
              "surface_area": float(surface.Mass()),
              "center_of_mass": xyz(volume.CentreOfMass()) if volume and mass else None,
              "bounding_box": bounding_box(shape), "oriented_bounding_box": oriented_box(shape),
              "topology": counts}
    if detailed:
        details = surface_details(shape)
        result["surface_details"] = details
        result["surface_type_counts"] = dict(Counter(f["type"] for f in details))
    return result
