"""圖片雜湊計算模組 — 支援檔案雜湊與感知雜湊。"""

import hashlib
from pathlib import Path
from typing import Literal

from PIL import Image
import imagehash

# 支援的感知雜湊演算法
HASH_ALGORITHMS = {
    "phash": imagehash.phash,
    "dhash": imagehash.dhash,
    "average_hash": imagehash.average_hash,
    "whash": imagehash.whash,
}

HashAlgorithm = Literal["phash", "dhash", "average_hash", "whash"]

# 檔案讀取緩衝區大小 (64KB)
_FILE_BUFFER_SIZE: int = 65536


class ImageHasher:
    """計算圖片的檔案雜湊與感知雜湊。

    支援 MD5 檔案雜湊（精確比對）和多種感知雜湊演算法（相似比對）。
    """

    def __init__(
        self,
        algorithm: HashAlgorithm = "phash",
        hash_size: int = 8,
    ) -> None:
        """初始化雜湊計算器。

        Args:
            algorithm: 感知雜湊演算法名稱。
            hash_size: 雜湊大小（影響精確度）。

        Raises:
            ValueError: 不支援的演算法。
        """
        if algorithm not in HASH_ALGORITHMS:
            raise ValueError(
                f"不支援的演算法: {algorithm}。"
                f"支援的演算法: {', '.join(HASH_ALGORITHMS.keys())}"
            )
        self._algorithm = algorithm
        self._hash_func = HASH_ALGORITHMS[algorithm]
        self._hash_size = hash_size

    @property
    def algorithm(self) -> str:
        """取得目前使用的演算法名稱。"""
        return self._algorithm

    def compute_file_hash(self, filepath: Path) -> str:
        """計算檔案的 MD5 雜湊值（用於精確比對）。

        以串流方式讀取檔案，不會一次載入整個檔案至記憶體。

        Args:
            filepath: 圖片檔案路徑。

        Returns:
            十六進位 MD5 雜湊字串。

        Raises:
            FileNotFoundError: 檔案不存在。
            PermissionError: 沒有讀取權限。
        """
        if not filepath.exists():
            raise FileNotFoundError(f"檔案不存在: {filepath}")

        md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            while True:
                data = f.read(_FILE_BUFFER_SIZE)
                if not data:
                    break
                md5.update(data)
        return md5.hexdigest()

    def compute_perceptual_hash(self, filepath: Path) -> imagehash.ImageHash:
        """計算圖片的感知雜湊值（用於相似比對）。

        Args:
            filepath: 圖片檔案路徑。

        Returns:
            圖片的感知雜湊值。

        Raises:
            FileNotFoundError: 檔案不存在。
            OSError: 圖片檔案損壞或無法開啟。
        """
        if not filepath.exists():
            raise FileNotFoundError(f"檔案不存在: {filepath}")

        with Image.open(filepath) as img:
            # 轉換為 RGB 以確保一致性（處理 RGBA、P 等模式）
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")
            return self._hash_func(img, hash_size=self._hash_size)

    def compute_both(self, filepath: Path) -> tuple[str, imagehash.ImageHash]:
        """同時計算檔案雜湊和感知雜湊。

        Args:
            filepath: 圖片檔案路徑。

        Returns:
            (file_hash, perceptual_hash) 元組。
        """
        file_hash = self.compute_file_hash(filepath)
        perceptual_hash = self.compute_perceptual_hash(filepath)
        return file_hash, perceptual_hash


class ImageInfo:
    """儲存圖片的完整資訊。"""

    def __init__(
        self,
        filepath: Path,
        file_hash: str = "",
        perceptual_hash: imagehash.ImageHash | None = None,
    ) -> None:
        self.filepath = filepath
        self.file_hash = file_hash
        self.perceptual_hash = perceptual_hash
        self._file_size: int | None = None
        self._dimensions: tuple[int, int] | None = None
        self._modified_time: float | None = None

    @property
    def file_size(self) -> int:
        """檔案大小（bytes）。"""
        if self._file_size is None:
            self._file_size = self.filepath.stat().st_size
        return self._file_size

    @property
    def dimensions(self) -> tuple[int, int]:
        """圖片尺寸 (寬, 高)。"""
        if self._dimensions is None:
            try:
                with Image.open(self.filepath) as img:
                    self._dimensions = img.size
            except Exception:
                self._dimensions = (0, 0)
        return self._dimensions

    @property
    def modified_time(self) -> float:
        """檔案修改時間戳。"""
        if self._modified_time is None:
            self._modified_time = self.filepath.stat().st_mtime
        return self._modified_time

    @property
    def filename(self) -> str:
        """檔案名稱。"""
        return self.filepath.name

    def __repr__(self) -> str:
        return f"ImageInfo({self.filepath.name})"
