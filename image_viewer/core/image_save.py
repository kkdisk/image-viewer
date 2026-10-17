"""先完整編碼，再以同目錄原子取代保護原檔。"""

import os
import tempfile
from pathlib import Path

from PIL import Image


def atomic_save(image, path):
    destination = Path(path).absolute()
    Image.init()
    image_format = Image.registered_extensions().get(destination.suffix.lower())
    if image_format is None:
        raise ValueError("不支援的輸出副檔名")
    output = image
    if image_format == "JPEG" and image.mode != "RGB":
        output = Image.new("RGB", image.size, "white")
        if image.mode in ("RGBA", "LA"):
            output.paste(image.convert("RGB"), mask=image.getchannel("A"))
        else:
            output.paste(image.convert("RGB"))
    options = {}
    if image.info.get("icc_profile"):
        options["icc_profile"] = image.info["icc_profile"]
    exif = image.getexif()
    if exif:
        saved_exif = Image.Exif()
        saved_exif.load(exif.tobytes())
        saved_exif[274] = 1
        options["exif"] = saved_exif.tobytes()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=destination.suffix, delete=False) as handle:
            temporary = handle.name
        output.save(temporary, format=image_format, **options)
        os.replace(temporary, destination)
    finally:
        if output is not image:
            output.close()
        if temporary and os.path.exists(temporary):
            os.remove(temporary)
