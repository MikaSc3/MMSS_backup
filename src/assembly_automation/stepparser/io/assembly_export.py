"""Assembly facts without processing diagnostics or invented CAD containers."""


def build_assembly_json(loaded, geometry):
    roots = [record["assembly_id"] for record in loaded.hierarchy if record["parent_id"] is None]
    root_instances = [item.instance_id for item in loaded.instances if item.assembly_id is None]
    root_id = roots[0] if len(roots) == 1 and not root_instances else None
    hierarchy_fields = ("assembly_id", "name", "parent_id", "assembly_ids", "instance_ids")
    measurement_fields = ("coordinate_frame", "volume", "surface_area", "center_of_mass", "size",
                          "bounding_box", "oriented_bounding_box")
    measurements = {key: value for key, value in geometry.items() if key in measurement_fields}
    for key in ("bounding_box", "oriented_bounding_box"):
        if key in measurements:
            measurements[key] = {name: value for name, value in measurements[key].items() if name != "status"}
    result = {"assembly_id": root_id, "name": loaded.name,
              "units": {key: loaded.units[key] for key in ("length", "area", "volume")},
              "total_parts": len(loaded.instances), "unique_parts": len(loaded.definitions),
              "hierarchy": [{key: record[key] for key in hierarchy_fields if key in record}
                            for record in loaded.hierarchy],
              "geometry": measurements, "spatial_relations_file": "spatial_relations.json"}
    if root_id is None:
        result["root_assembly_ids"] = roots
        result["root_instance_ids"] = root_instances
    return result
