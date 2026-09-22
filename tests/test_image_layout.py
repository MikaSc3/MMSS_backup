"""Image layout checks; no OCC viewer or model inference required."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PIL import Image, ImageDraw
from assembly_automation.stepparser.rendering.image_layout import crop_to_content
from assembly_automation.stepparser.rendering.automaticimageselection import make_collage, select_images
from assembly_automation.stepparser.settings import ImageSelectionSettings


class ImageLayoutTests(unittest.TestCase):
    def test_assembly_exploded_iso1_is_last_and_not_duplicated(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            records = []
            for view, category in (("iso1", "assembly"), ("front", "assembly"),
                                   ("right", "assembly"), ("iso1", "exploded")):
                path = f"{category}_{view}.png"
                Image.new("RGB", (100, 100), "blue").save(root / path)
                records.append({"path": path, "view": view, "category": category})
            for include_exploded in (False, True):
                result = select_images(records, root, ImageSelectionSettings(include_exploded=include_exploded))[0]
                self.assertEqual(result["selected_images"],
                                 ["assembly_iso1.png", "assembly_front.png", "assembly_right.png", "exploded_iso1.png"])
            result = select_images(records[:-1], root, ImageSelectionSettings())[0]
            self.assertEqual(result["reason"], "missing_nonblank_iso1_exploded")

    def test_crop_keeps_margin_and_annotations(self):
        image = Image.new("RGB", (200, 100), "white")
        draw = ImageDraw.Draw(image)
        draw.rectangle((80, 20, 119, 79), fill="blue")
        draw.point((10, 50), fill="red")
        cropped = crop_to_content(image, padding=5)
        self.assertEqual(cropped.size, (120, 70))
        self.assertEqual(cropped.getpixel((5, 35)), (255, 0, 0))

    def test_blank_image_is_not_invalidly_cropped(self):
        self.assertEqual(crop_to_content(Image.new("RGB", (200, 100), "white")).size, (200, 100))

    def test_collage_columns_follow_content_aspect_ratios(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            paths = []
            for index, rectangle in enumerate(((45, 10, 54, 89), (10, 45, 89, 54), (10, 10, 89, 89))):
                image = Image.new("RGB", (100, 100), "white")
                ImageDraw.Draw(image).rectangle(rectangle, fill="blue")
                path = root / f"{index}.png"
                image.save(path)
                paths.append(path)
            target = root / "collage.png"
            make_collage(paths, ["iso1", "front", "right"], target, (100, 100), crop_padding_px=0)
            with Image.open(target) as collage:
                self.assertLess(collage.width, 300)
                self.assertLess(collage.height, 130)
            make_collage(paths, ["iso1", "front", "right"], target, (100, 100), crop_whitespace=False)
            with Image.open(target) as collage:
                self.assertEqual(collage.size, (324, 130))


if __name__ == "__main__":
    unittest.main()
