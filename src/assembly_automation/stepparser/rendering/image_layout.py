"""Trim white CAD image borders while keeping all visible annotations."""


def crop_to_content(image, padding=16):
    from PIL import Image, ImageChops

    rgb = image.convert("RGB")
    difference = ImageChops.difference(rgb, Image.new("RGB", rgb.size, "white"))
    red, green, blue = difference.split()
    difference = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    # Ignore almost-white antialiasing noise when locating the content bounds.
    bounds = difference.point(lambda value: 255 if value > 10 else 0).getbbox()
    if bounds is None:
        return rgb
    left, top, right, bottom = bounds
    return rgb.crop((max(0, left - padding), max(0, top - padding),
                     min(rgb.width, right + padding), min(rgb.height, bottom + padding)))
