"""Deterministic preprocessing with consolidated JSON artifacts."""

from collections import Counter
from datetime import datetime, timezone
import hashlib
from pathlib import Path
import time

from .analysis.geometry import bounding_box, measure_shape, validate_shape, xyz
from .analysis.spatial_relations import compute_spatial_relations
from .io.metadata_manager import write_json
from .io.step_loader import load_step, transform_matrix
from .rendering.color_generator import assign_colors
from .settings import StepParserSettings


class StepProcessor:
    def __init__(self, settings: StepParserSettings | None = None):
        self.settings = settings or StepParserSettings()

    def process_step_file(self, step_file: str | Path, output_dir: str | Path, *, progress=None) -> dict:
        output = Path(output_dir).resolve()
        if output.exists() and any(output.iterdir()):
            raise FileExistsError(f"Use an empty output directory: {output}")
        output.mkdir(parents=True, exist_ok=True)
        started = time.monotonic()
        manifest = {"schema_version": "1.0", "status": "running",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "settings": self.settings.to_dict(), "stages": {}, "warnings": [], "artifacts": []}
        manifest_path = output / "manifest.json"
        stage = "loading"

        def begin(name):
            nonlocal stage
            stage = name
            manifest["stages"][name] = "running"
            write_json(manifest_path, manifest)
            if progress:
                progress(name, 0, None)

        def done():
            manifest["stages"][stage] = "complete"
            write_json(manifest_path, manifest)

        try:
            begin("loading")
            source = Path(step_file).resolve(strict=True)
            manifest["input"] = {"name": source.name, "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}
            loaded = load_step(source)
            manifest["units"] = loaded.units
            import OCC
            manifest["occ_version"] = OCC.VERSION
            done()

            begin("validation")
            invalid = []
            for definition in loaded.definitions:
                definition.validity = validate_shape(definition.shape)
                if not definition.validity["is_valid"]:
                    invalid.append(definition.part_id)
            manifest["shape_validity"] = {d.part_id: d.validity for d in loaded.definitions}
            aggregate_validity = validate_shape(loaded.shape)
            manifest["assembly_validity"] = aggregate_validity
            if invalid or not aggregate_validity["is_valid"]:
                raise ValueError(f"Invalid BREP geometry; part IDs: {invalid}; aggregate: {aggregate_validity['status']}")
            done()

            begin("geometry")
            for index, definition in enumerate(loaded.definitions, 1):
                definition.geometry = measure_shape(definition.shape)
                if progress:
                    progress("geometry", index, len(loaded.definitions))
            aggregate = measure_shape(loaded.shape, detailed=False, coordinate_frame="assembly")
            done()

            begin("colors")
            assign_colors(loaded.definitions, loaded.instances, self.settings.color_mode)
            done()

            begin("spatial_relations")
            relations = compute_spatial_relations(loaded.instances, self.settings.spatial_relations, progress)
            if relations["status"] == "partial":
                manifest["warnings"].append("Some pairwise distances failed; inspect spatial_relations.pairs")
                manifest["stages"][stage] = "partial"
            else:
                done()

            begin("export")
            quantities = Counter(i.part_id for i in loaded.instances)
            by_id = {d.part_id: d for d in loaded.definitions}
            instances = []
            for instance in loaded.instances:
                definition = by_id[instance.part_id]
                local_com = definition.geometry["center_of_mass"]
                world_com = None
                if local_com is not None:
                    from OCC.Core.gp import gp_Pnt
                    world_com = xyz(gp_Pnt(*local_com).Transformed(instance.location.Transformation()))
                instances.append({"instance_id": instance.instance_id, "part_id": instance.part_id,
                                  "name": instance.name, "assembly_id": instance.assembly_id,
                                  "source_path": instance.source_path, "color": instance.color,
                                  "placement": {"coordinate_frame": "part_local_to_assembly",
                                                "matrix": transform_matrix(instance.location)},
                                  "bounding_box": bounding_box(instance.shape), "center_of_mass": world_com})
            bom = {"schema_version": "1.0", "units": loaded.units,
                   "grouping_method": "STEP_definition_identity",
                   "parts": [{"part_id": d.part_id, "name": d.name, "source_definition": d.source_definition,
                              "quantity": quantities[d.part_id], "color": d.color,
                              "validity": d.validity, "geometry": d.geometry} for d in loaded.definitions],
                   "instances": instances}
            assembly = {"schema_version": "1.0", "assembly_id": "assy_001", "name": loaded.name,
                        "units": loaded.units, "total_parts": len(instances), "unique_parts": len(loaded.definitions),
                        "hierarchy": loaded.hierarchy, "validity": aggregate_validity,
                        "geometry": aggregate, "spatial_relations": relations}
            write_json(output / "bom.json", bom)
            write_json(output / "assembly.json", assembly)
            manifest["artifacts"] = ["bom.json", "assembly.json"]
            done()

            begin("rendering")
            if self.settings.rendering.enabled:
                from .rendering.renderer import Renderer
                manifest["images"] = Renderer(self.settings.rendering).render(loaded, output, progress)
                manifest["artifacts"].extend(image["path"] for image in manifest["images"])
                done()
            else:
                manifest["images"] = []
                manifest["stages"][stage] = "disabled"
            begin("sam_segmentation")
            if self.settings.sam.enabled:
                from .rendering.sam_segmentation import SamSegmenter
                manifest["sam_images"] = SamSegmenter(self.settings.sam).segment_images(
                    manifest["images"], output, progress)
                manifest["artifacts"].extend(image["path"] for image in manifest["sam_images"])
                done()
            else:
                manifest["sam_images"] = []
                manifest["stages"][stage] = "disabled"
            begin("automaticimageselection")
            if self.settings.automaticimageselection.enabled and manifest["images"]:
                from .rendering.automaticimageselection import select_images
                manifest["collages"] = select_images(manifest["images"], output,
                    self.settings.automaticimageselection, progress)
                manifest["artifacts"].extend(item["path"] for item in manifest["collages"] if "path" in item)
                done()
            else:
                manifest["collages"] = []
                manifest["stages"][stage] = "disabled" if not self.settings.automaticimageselection.enabled else "skipped"
            manifest["status"] = "partial" if manifest["warnings"] else "complete"
        except Exception as exc:
            manifest["status"] = "failed"
            manifest["stages"][stage] = "failed"
            manifest["error"] = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            manifest["elapsed_seconds"] = time.monotonic() - started
            write_json(manifest_path, manifest)
        return manifest
