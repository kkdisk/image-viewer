"""檔案掃描器模組 — 遞迴掃描資料夾中的圖片檔案。"""

from pathlib import Path

# 支援的圖片格式
SUPPORTED_FORMATS: set[str] = {
    ".jpg", ".jpeg", ".png", ".bmp", ".gif",
    ".webp", ".tiff", ".tif",
}


class ImageScanner:
    """掃描指定資料夾中的圖片檔案。

    支援多個資料夾、遞迴掃描、格式過濾。
    """

    def __init__(
        self,
        directories: list[str | Path],
        recursive: bool = True,
        formats: set[str] | None = None,
    ) -> None:
        """初始化掃描器。

        Args:
            directories: 要掃描的資料夾路徑清單。
            recursive: 是否遞迴掃描子資料夾。
            formats: 要篩選的圖片格式（副檔名集合），預設為所有支援格式。
        """
        self._directories = [Path(d) for d in directories]
        self._recursive = recursive
        self._formats = formats or SUPPORTED_FORMATS

    @property
    def directories(self) -> list[Path]:
        """取得掃描的資料夾清單。"""
        return list(self._directories)

    def scan(self) -> list[Path]:
        """掃描所有指定資料夾，回傳圖片檔案路徑清單。

        Returns:
            圖片檔案路徑清單（已排序、去重複）。

        Raises:
            FileNotFoundError: 資料夾不存在。
            NotADirectoryError: 路徑不是資料夾。
        """
        all_files: set[Path] = set()

        for directory in self._directories:
            if not directory.exists():
                raise FileNotFoundError(f"資料夾不存在: {directory}")
            if not directory.is_dir():
                raise NotADirectoryError(f"路徑不是資料夾: {directory}")

            files = self._scan_directory(directory)
            all_files.update(files)

        # 回傳排序後的清單（以字串排序確保一致性）
        return sorted(all_files, key=lambda p: str(p).lower())

    def _scan_directory(self, directory: Path) -> list[Path]:
        """掃描單一資料夾中的圖片檔案。

        Args:
            directory: 要掃描的資料夾。

        Returns:
            該資料夾中的圖片檔案清單。
        """
        results: list[Path] = []

        if self._recursive:
            pattern = "**/*"
        else:
            pattern = "*"

        for filepath in directory.glob(pattern):
            if filepath.is_file() and self._is_supported_format(filepath):
                try:
                    # 解析為絕對路徑，處理符號連結
                    resolved = filepath.resolve()
                    results.append(resolved)
                except (OSError, ValueError):
                    # 跳過無法解析的路徑
                    continue

        return results

    def _is_supported_format(self, filepath: Path) -> bool:
        """檢查檔案是否為支援的圖片格式。

        Args:
            filepath: 檔案路徑。

        Returns:
            True 表示格式支援。
        """
        return filepath.suffix.lower() in self._formats
