import pytest
from PIL import Image

from image_viewer.core.image_save import atomic_save


def test_png_retains_alpha_icc_and_exif(tmp_path):
    source = Image.new("RGBA", (8, 8), (20, 40, 60, 42))
    source.info["icc_profile"] = b"test-profile"
    source.getexif()[315] = "test-author"
    source.getexif()[274] = 6
    path = tmp_path / "output.png"
    atomic_save(source, path)
    with Image.open(path) as result:
        assert result.getpixel((0, 0)) == (20, 40, 60, 42)
        assert result.info["icc_profile"] == b"test-profile"
        assert result.getexif()[315] == "test-author"
        assert result.getexif()[274] == 1


def test_failed_encoding_keeps_existing_file(tmp_path, monkeypatch):
    path = tmp_path / "output.png"
    Image.new("RGB", (8, 8), "red").save(path)
    before = path.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(Image.Image, "save", fail)
    with pytest.raises(OSError):
        atomic_save(Image.new("RGB", (8, 8), "blue"), path)
    assert path.read_bytes() == before
    assert list(tmp_path.iterdir()) == [path]


def test_jpeg_transparency_uses_white_background(tmp_path):
    path = tmp_path / "output.jpg"
    atomic_save(Image.new("RGBA", (8, 8), (0, 0, 0, 0)), path)
    with Image.open(path) as result:
        assert result.mode == "RGB"
        assert result.getpixel((0, 0)) == (255, 255, 255)
