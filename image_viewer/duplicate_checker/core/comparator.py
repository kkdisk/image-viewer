"""重複圖片比對與分組模組。"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Literal, Optional

from image_viewer.duplicate_checker.core.hasher import ImageHasher, ImageInfo

# Rust 擴充模組 (graceful fallback)
try:
    import image_viewer_rs
    _USE_RUST = True
except ImportError:
    _USE_RUST = False

CompareMode = Literal["exact", "similar", "both"]

# 預設相似度門檻（Hamming distance）
DEFAULT_THRESHOLD: int = 5


@dataclass
class DuplicateGroup:
    """一組重複或相似的圖片。

    Attributes:
        group_id: 群組識別碼。
        images: 群組中的圖片資訊清單。
        match_type: 比對類型（exact=精確, similar=相似）。
        max_distance: 群組中最大的 Hamming distance。
    """
    group_id: int
    images: list[ImageInfo] = field(default_factory=list)
    match_type: str = "exact"
    max_distance: int = 0

    @property
    def file_count(self) -> int:
        """群組中的檔案數量。"""
        return len(self.images)

    @property
    def total_size(self) -> int:
        """群組中所有檔案的總大小。"""
        return sum(img.file_size for img in self.images)

    @property
    def saveable_size(self) -> int:
        """可節省的空間（保留最大的那張）。"""
        if len(self.images) <= 1:
            return 0
        sizes = sorted([img.file_size for img in self.images], reverse=True)
        return sum(sizes[1:])  # 除了最大的之外的總和

    def get_best_image(self) -> ImageInfo | None:
        """取得建議保留的圖片（解析度最高、檔案最大）。"""
        if not self.images:
            return None
        return max(
            self.images,
            key=lambda img: (
                img.dimensions[0] * img.dimensions[1],  # 像素數
                img.file_size,  # 檔案大小
            ),
        )


class ImageComparator:
    """比對圖片並分組。

    支援精確比對（file hash）、相似比對（perceptual hash）、
    或同時使用兩種模式。
    """

    def __init__(
        self,
        mode: CompareMode = "both",
        threshold: int = DEFAULT_THRESHOLD,
        hasher: ImageHasher | None = None,
    ) -> None:
        """初始化比對器。

        Args:
            mode: 比對模式。
            threshold: 相似度門檻（Hamming distance），僅在相似比對時使用。
            hasher: 圖片雜湊計算器，若為 None 則使用預設設定。
        """
        self._mode = mode
        self._threshold = threshold
        self._hasher = hasher or ImageHasher()
        self._image_infos: list[ImageInfo] = []
        self._errors: list[tuple[Path, str]] = []

    @property
    def mode(self) -> CompareMode:
        return self._mode

    @property
    def threshold(self) -> int:
        return self._threshold

    @property
    def errors(self) -> list[tuple[Path, str]]:
        """取得處理過程中發生的錯誤清單。"""
        return list(self._errors)

    def process_files(
        self,
        filepaths: list[Path],
        progress_callback: Optional[Callable] = None,
    ) -> list[ImageInfo]:
        """計算所有檔案的雜湊值。

        支援 Rust 批次平行處理（graceful fallback）。

        Args:
            filepaths: 圖片檔案路徑清單。
            progress_callback: 進度回呼函式，接收 (current, total) 參數。

        Returns:
            已處理的 ImageInfo 清單。
        """
        self._image_infos = []
        self._errors = []
        total = len(filepaths)

        # Rust 批次加速路徑（檔案數 > 10 時才啟用，避免少量檔案的開銷）
        if _USE_RUST and total > 10:
            try:
                return self._process_files_rust(filepaths, progress_callback)
            except Exception as e:
                logging.warning(f"Rust 批次處理失敗，回退至逐檔處理: {e}")
                self._image_infos = []
                self._errors = []

        # Python 回退路徑（逐檔處理）
        for i, filepath in enumerate(filepaths):
            try:
                info = ImageInfo(filepath)

                if self._mode in ("exact", "both"):
                    info.file_hash = self._hasher.compute_file_hash(filepath)

                if self._mode in ("similar", "both"):
                    info.perceptual_hash = self._hasher.compute_perceptual_hash(
                        filepath
                    )

                self._image_infos.append(info)

            except Exception as e:
                self._errors.append((filepath, str(e)))

            if progress_callback:
                progress_callback(i + 1, total)

        return self._image_infos

    def _process_files_rust(
        self,
        filepaths: list[Path],
        progress_callback: Optional[Callable] = None,
    ) -> list[ImageInfo]:
        """使用 Rust 批次平行處理檔案雜湊計算。"""
        from image_viewer.duplicate_checker.core.hasher import _rust_bytes_to_imagehash

        total = len(filepaths)
        str_paths = [str(p) for p in filepaths]

        # 階段 1：批次 MD5
        md5_results = {}
        if self._mode in ("exact", "both"):
            if progress_callback:
                progress_callback(0, total)
            raw_md5 = image_viewer_rs.batch_md5(str_paths)
            for path_str, hash_val in raw_md5:
                if not hash_val.startswith("ERROR:"):
                    md5_results[path_str] = hash_val
                else:
                    self._errors.append(
                        (Path(path_str), hash_val[6:])  # 去掉 "ERROR:" 前綴
                    )

        # 階段 2：批次 pHash
        phash_results = {}
        if self._mode in ("similar", "both"):
            # 過濾掉 MD5 階段已失敗的檔案
            valid_paths = [
                p for p in str_paths
                if p not in {str(ep) for ep, _ in self._errors}
            ]
            if valid_paths and self._hasher.algorithm == "phash":
                raw_phash = image_viewer_rs.batch_phash(
                    valid_paths, self._hasher._hash_size
                )
                for path_str, hash_bytes in raw_phash:
                    if hash_bytes:  # 空的 bytes 表示失敗
                        phash_results[path_str] = _rust_bytes_to_imagehash(
                            hash_bytes, self._hasher._hash_size
                        )
                    else:
                        self._errors.append(
                            (Path(path_str), "pHash 計算失敗")
                        )
            elif valid_paths:
                # 非 pHash 演算法，回退 Python 逐檔處理
                for i, path_str in enumerate(valid_paths):
                    try:
                        ph = self._hasher.compute_perceptual_hash(Path(path_str))
                        phash_results[path_str] = ph
                    except Exception as e:
                        self._errors.append((Path(path_str), str(e)))

        # 組合結果
        error_paths = {str(ep) for ep, _ in self._errors}
        for i, filepath in enumerate(filepaths):
            path_str = str(filepath)
            if path_str in error_paths:
                continue

            info = ImageInfo(filepath)
            if path_str in md5_results:
                info.file_hash = md5_results[path_str]
            if path_str in phash_results:
                info.perceptual_hash = phash_results[path_str]

            self._image_infos.append(info)

            if progress_callback and (i + 1) % 50 == 0:
                progress_callback(i + 1, total)

        if progress_callback:
            progress_callback(total, total)

        return self._image_infos

    def find_duplicates(self) -> list[DuplicateGroup]:
        """根據已處理的雜湊值，尋找重複群組。

        Returns:
            重複群組清單（每組至少 2 張圖片）。
        """
        groups: list[DuplicateGroup] = []
        group_id = 0

        if self._mode in ("exact", "both"):
            exact_groups = self._find_exact_duplicates()
            for g in exact_groups:
                g.group_id = group_id
                group_id += 1
            groups.extend(exact_groups)

        if self._mode in ("similar", "both"):
            # 排除已在精確比對中找到的檔案（避免重複列出）
            exact_paths: set[Path] = set()
            if self._mode == "both":
                for g in groups:
                    for img in g.images:
                        exact_paths.add(img.filepath)

            similar_groups = self._find_similar_duplicates(
                exclude_paths=exact_paths
            )
            for g in similar_groups:
                g.group_id = group_id
                group_id += 1
            groups.extend(similar_groups)

        return groups

    def _find_exact_duplicates(self) -> list[DuplicateGroup]:
        """以檔案雜湊找出完全相同的圖片。"""
        hash_map: dict[str, list[ImageInfo]] = {}

        for info in self._image_infos:
            if info.file_hash:
                hash_map.setdefault(info.file_hash, []).append(info)

        groups: list[DuplicateGroup] = []
        for file_hash, images in hash_map.items():
            if len(images) >= 2:
                group = DuplicateGroup(
                    group_id=0,
                    images=images,
                    match_type="exact",
                    max_distance=0,
                )
                groups.append(group)

        return groups

    def _find_similar_duplicates(
        self,
        exclude_paths: set[Path] | None = None,
    ) -> list[DuplicateGroup]:
        """以感知雜湊找出視覺相似的圖片。

        支援 Rust 加速的 Union-Find 演算法（graceful fallback）。
        """
        exclude = exclude_paths or set()

        # 過濾出有感知雜湊且未在精確比對中的圖片
        candidates = [
            info
            for info in self._image_infos
            if info.perceptual_hash is not None and info.filepath not in exclude
        ]

        if len(candidates) < 2:
            return []

        # Rust 加速路徑（候選數 > 50 時啟用，避免小規模的開銷）
        if _USE_RUST and len(candidates) > 50:
            try:
                return self._find_similar_rust(candidates)
            except Exception as e:
                logging.warning(f"Rust 比對失敗，回退至 Python: {e}")

        # Python 回退路徑：Union-Find
        n = len(candidates)
        parent = list(range(n))
        max_dist: dict[int, int] = {}

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(x: int, y: int, dist: int) -> None:
            rx, ry = find(x), find(y)
            if rx != ry:
                parent[rx] = ry
                # 記錄群組中的最大距離
                current_max = max(
                    max_dist.get(ry, 0),
                    max_dist.get(rx, 0),
                    dist,
                )
                max_dist[ry] = current_max

        # 比對所有配對
        for i in range(n):
            for j in range(i + 1, n):
                dist = candidates[i].perceptual_hash - candidates[j].perceptual_hash
                if dist <= self._threshold:
                    union(i, j, dist)

        # 收集群組
        group_map: dict[int, list[int]] = {}
        for i in range(n):
            root = find(i)
            group_map.setdefault(root, []).append(i)

        groups: list[DuplicateGroup] = []
        for root, indices in group_map.items():
            if len(indices) >= 2:
                images = [candidates[i] for i in indices]
                group = DuplicateGroup(
                    group_id=0,
                    images=images,
                    match_type="similar",
                    max_distance=max_dist.get(root, 0),
                )
                groups.append(group)

        return groups

    def _find_similar_rust(
        self,
        candidates: list[ImageInfo],
    ) -> list[DuplicateGroup]:
        """使用 Rust 擴充模組執行相似圖片分組。"""
        import numpy as np

        # 將 imagehash.ImageHash 轉為 bytes
        hashes_bytes: list[list[int]] = []
        for info in candidates:
            # imagehash.ImageHash.hash 是 numpy bool 陣列
            bool_array = info.perceptual_hash.hash.flatten()
            # 打包為 bytes
            packed = np.packbits(bool_array.astype(np.uint8))
            hashes_bytes.append(packed.tolist())

        # 呼叫 Rust 的 find_similar_groups
        rust_groups = image_viewer_rs.find_similar_groups(
            hashes_bytes, self._threshold
        )

        # 轉換回 DuplicateGroup
        groups: list[DuplicateGroup] = []
        for indices, max_distance in rust_groups:
            if len(indices) >= 2:
                images = [candidates[i] for i in indices]
                group = DuplicateGroup(
                    group_id=0,
                    images=images,
                    match_type="similar",
                    max_distance=int(max_distance),
                )
                groups.append(group)

        return groups
