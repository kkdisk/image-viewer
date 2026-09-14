from image_viewer.config import Config
from image_viewer.core.media_types import (
    MediaKind,
    classify_media_path,
    first_supported_file,
    supported_media_extensions,
)


def test_classify_media_path_is_case_insensitive():
    config = Config()

    assert classify_media_path("photo.JPG", config) == MediaKind.IMAGE
    assert classify_media_path("clip.MP4", config) == MediaKind.VIDEO
    assert classify_media_path("album.7Z", config) == MediaKind.ARCHIVE
    assert classify_media_path("notes.txt", config) == MediaKind.UNSUPPORTED


def test_supported_media_extensions_excludes_archives():
    config = Config()
    extensions = supported_media_extensions(config)

    assert ".png" in extensions
    assert ".mp4" in extensions
    assert ".7z" not in extensions


def test_first_supported_file_skips_invalid_entries(tmp_path):
    config = Config()
    unsupported = tmp_path / "notes.txt"
    video = tmp_path / "clip.mp4"
    image = tmp_path / "photo.png"
    unsupported.write_text("notes", encoding="utf-8")
    video.write_bytes(b"video")
    image.write_bytes(b"image")

    result = first_supported_file(
        [str(tmp_path / "missing.mp4"), str(unsupported), str(video), str(image)],
        config,
    )

    assert result == str(video)


def test_first_supported_file_accepts_archive(tmp_path):
    archive = tmp_path / "album.7z"
    archive.write_bytes(b"archive")

    assert first_supported_file([str(archive)], Config()) == str(archive)
