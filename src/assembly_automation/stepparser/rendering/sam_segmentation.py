"""Optional SAM 1 automatic masks visualized over the original CAD images."""

from pathlib import Path


class SamSegmenter:
    def __init__(self, settings):
        self.settings = settings
        self.generator = None
        self.device = None

    def _initialize(self):
        if self.generator is not None:
            return
        checkpoint = Path(self.settings.checkpoint).expanduser().resolve()
        if not checkpoint.is_file():
            raise FileNotFoundError(
                f"SAM checkpoint missing: {checkpoint}. Download the matching official "
                "SAM checkpoint and set nodes.step_preprocessing.sam.checkpoint.")
        try:
            import torch
            from segment_anything import SamAutomaticMaskGenerator, sam_model_registry
        except ImportError as exc:
            raise RuntimeError("SAM requires its optional dependencies. In the OCC environment "
                               f"run: pip install -e '.[sam]'. Import error: {exc}") from exc
        self.device = ("cuda" if torch.cuda.is_available() else "cpu") if self.settings.device == "auto" else self.settings.device
        if self.device == "cuda" and not torch.cuda.is_available():
            raise RuntimeError("SAM device is cuda, but CUDA is unavailable; use cpu or auto")
        model = sam_model_registry[self.settings.model_type](checkpoint=str(checkpoint))
        model.to(device=self.device)
        model.eval()
        self.generator = SamAutomaticMaskGenerator(
            model, points_per_side=self.settings.points_per_side,
            points_per_batch=self.settings.points_per_batch,
            pred_iou_thresh=self.settings.pred_iou_thresh,
            stability_score_thresh=self.settings.stability_score_thresh,
            min_mask_region_area=self.settings.min_mask_region_area,
            output_mode="binary_mask")

    def segment_images(self, images, output_dir, progress=None):
        import numpy as np
        from PIL import Image

        if not images:
            raise ValueError("SAM needs rendered images; enable rendering and select at least one view")
        self._initialize()
        records = []
        for index, source in enumerate(images, 1):
            relative = Path(source["path"])
            with Image.open(Path(output_dir) / relative) as image:
                rgb = np.array(image.convert("RGB"))
            masks = self.generator.generate(rgb)
            result = overlay_masks(rgb, masks, self.settings.overlay_alpha)
            target = relative.with_name("SAM_" + relative.name)
            Image.fromarray(result).save(Path(output_dir) / target)
            records.append({**source, "path": target.as_posix(), "source_image": relative.as_posix(),
                            "category": "sam_segmentation", "source_category": source.get("category"),
                            "model_type": self.settings.model_type, "device": self.device,
                            "mask_count": len(masks), "status": "complete" if masks else "no_masks"})
            if progress:
                progress("sam_segmentation", index, len(images))
        return records


def overlay_masks(rgb, masks, alpha):
    """Large masks first so smaller surface candidates stay visible on top."""
    import numpy as np

    result = rgb.astype(np.float32).copy()
    rng = np.random.default_rng(42)
    for mask in sorted(masks, key=lambda item: item["area"], reverse=True):
        selection = np.asarray(mask["segmentation"], dtype=bool)
        color = rng.integers(40, 230, size=3)
        # Blend against the source, avoiding repeated darkening of nested masks.
        result[selection] = rgb[selection] * (1 - alpha) + color * alpha
    return np.clip(result, 0, 255).astype(np.uint8)
