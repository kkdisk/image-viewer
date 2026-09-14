from image_viewer.config import Config
from image_viewer.core.media_types import (
    MediaKind,
    classify_media_path,
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
