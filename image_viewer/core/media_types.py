"""媒體檔案分類工具。"""

import os
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional


class MediaKind(Enum):
    IMAGE = "image"
    VIDEO = "video"
    ARCHIVE = "archive"
    UNSUPPORTED = "unsupported"


def classify_media_path(path: str, config) -> MediaKind:
    """依副檔名分類檔案；實際 codec 支援由播放器在載入時確認。"""
    extension = Path(path).suffix.lower()
    if extension in config.SUPPORTED_IMAGE_EXTENSIONS:
        return MediaKind.IMAGE
    if extension in config.SUPPORTED_VIDEO_EXTENSIONS:
        return MediaKind.VIDEO
    if extension in config.SUPPORTED_ARCHIVE_EXTENSIONS:
        return MediaKind.ARCHIVE
    return MediaKind.UNSUPPORTED


def supported_media_extensions(config) -> tuple[str, ...]:
    """回傳會顯示在一般 Filmstrip 的圖片與影片副檔名。"""
    return config.SUPPORTED_IMAGE_EXTENSIONS + config.SUPPORTED_VIDEO_EXTENSIONS


def first_supported_file(paths: Iterable[str], config) -> Optional[str]:
    """回傳拖放路徑中第一個存在且受支援的檔案。"""
    for path in paths:
        if (
            path
            and os.path.isfile(path)
            and classify_media_path(path, config) != MediaKind.UNSUPPORTED
        ):
            return path
    return None
