"""Rust 擴充模組 (image_viewer_rs) 功能測試。

測試 Rust 加速路徑是否與 Python 實作產生一致的結果。
"""

import pytest
from pathlib import Path
from PIL import Image
import hashlib

# 嘗試 import Rust 模組
try:
    import image_viewer_rs
    HAS_RUST = True
except ImportError:
    HAS_RUST = False

# 跳過條件：Rust 模組不可用時跳過所有測試
pytestmark = pytest.mark.skipif(not HAS_RUST, reason="Rust 擴充模組未安裝")


# ============================================================================
# MD5 雜湊測試
# ============================================================================


class TestRustMD5:
    """測試 Rust MD5 計算與 Python hashlib 的一致性。"""

    def _python_md5(self, filepath: Path) -> str:
        """Python 參考實作"""
        md5 = hashlib.md5()
        with open(filepath, "rb") as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                md5.update(data)
        return md5.hexdigest()

    def test_single_md5_basic(self, tmp_path):
        """測試單檔 MD5 基本功能"""
        img_path = tmp_path / "test.png"
        Image.new("RGB", (100, 100), color="red").save(img_path)

        rust_hash = image_viewer_rs.compute_single_md5(str(img_path))
        python_hash = self._python_md5(img_path)

        assert rust_hash == python_hash
        assert len(rust_hash) == 32

    def test_single_md5_file_not_found(self):
        """測試檔案不存在時拋出例外"""
        with pytest.raises(Exception):
            image_viewer_rs.compute_single_md5("non_existent_file.png")

    def test_batch_md5(self, tmp_path):
        """測試批次 MD5 計算"""
        paths = []
        for i in range(5):
            p = tmp_path / f"img_{i}.png"
            Image.new("RGB", (50 + i, 50 + i), color=(i * 50, 0, 0)).save(p)
            paths.append(str(p))

        results = image_viewer_rs.batch_md5(paths)
        assert len(results) == 5

        for path_str, hash_val in results:
            assert not hash_val.startswith("ERROR:")
            python_hash = self._python_md5(Path(path_str))
            assert hash_val == python_hash

    def test_batch_md5_with_invalid(self, tmp_path):
        """測試批次 MD5 中包含無效檔案"""
        valid_path = tmp_path / "valid.png"
        Image.new("RGB", (10, 10)).save(valid_path)

        results = image_viewer_rs.batch_md5([
            str(valid_path),
            "non_existent.png",
        ])
        assert len(results) == 2
        assert not results[0][1].startswith("ERROR:")
        assert results[1][1].startswith("ERROR:")


# ============================================================================
# pHash 感知雜湊測試
# ============================================================================


class TestRustPHash:
    """測試 Rust pHash 計算。"""

    def test_single_phash_basic(self, tmp_path):
        """測試單檔 pHash 基本功能"""
        img_path = tmp_path / "test.png"
        Image.new("RGB", (200, 200), color="blue").save(img_path)

        hash_bytes = image_viewer_rs.compute_single_phash(str(img_path), 8)
        # hash_size=8 → 64 bits → 8 bytes
        assert len(hash_bytes) == 8

    def test_identical_images_same_hash(self, tmp_path):
        """測試相同圖片產生相同 pHash"""
        p1 = tmp_path / "img1.png"
        p2 = tmp_path / "img2.png"
        img = Image.new("RGB", (200, 200), color="green")
        img.save(p1)
        img.save(p2)

        h1 = image_viewer_rs.compute_single_phash(str(p1), 8)
        h2 = image_viewer_rs.compute_single_phash(str(p2), 8)
        assert h1 == h2

    def test_different_images_different_hash(self, tmp_path):
        """測試明顯不同的圖片產生不同 pHash"""
        p1 = tmp_path / "red.png"
        p2 = tmp_path / "blue.png"
        Image.new("RGB", (200, 200), color="red").save(p1)
        Image.new("RGB", (200, 200), color="blue").save(p2)

        h1 = image_viewer_rs.compute_single_phash(str(p1), 8)
        h2 = image_viewer_rs.compute_single_phash(str(p2), 8)

        # 計算 hamming distance
        dist = image_viewer_rs.hamming_distance(h1, h2)
        # 紅色和藍色圖片的 pHash 應有明顯差異
        assert dist > 0

    def test_batch_phash(self, tmp_path):
        """測試批次 pHash 計算"""
        paths = []
        for i in range(5):
            p = tmp_path / f"img_{i}.png"
            Image.new("RGB", (100, 100), color=(i * 50, 0, 0)).save(p)
            paths.append(str(p))

        results = image_viewer_rs.batch_phash(paths, 8)
        assert len(results) == 5
        for _, hash_bytes in results:
            assert len(hash_bytes) == 8

    def test_phash_file_not_found(self, tmp_path):
        """測試檔案不存在時拋出例外"""
        with pytest.raises(Exception):
            image_viewer_rs.compute_single_phash("non_existent.png", 8)


# ============================================================================
# Hamming Distance & 相似度比對測試
# ============================================================================


class TestRustComparison:
    """測試 Rust 的 Hamming distance 和 Union-Find 分組。"""

    def test_hamming_distance_identical(self):
        """測試相同 hash 的距離為 0"""
        a = [0xFF, 0x00]
        b = [0xFF, 0x00]
        assert image_viewer_rs.hamming_distance(a, b) == 0

    def test_hamming_distance_all_different(self):
        """測試完全不同的 hash"""
        a = [0xFF]
        b = [0x00]
        assert image_viewer_rs.hamming_distance(a, b) == 8

    def test_hamming_distance_one_bit(self):
        """測試只有 1 bit 差異"""
        a = [0b11111111]
        b = [0b11111110]
        assert image_viewer_rs.hamming_distance(a, b) == 1

    def test_find_similar_groups_basic(self):
        """測試基本的相似群組分類"""
        hashes = [
            [0xFF, 0x00],
            [0xFF, 0x00],  # 和 0 完全相同
            [0x00, 0xFF],  # 距離 = 16
        ]
        groups = image_viewer_rs.find_similar_groups(hashes, 5)
        assert len(groups) == 1
        indices, max_dist = groups[0]
        assert set(indices) == {0, 1}
        assert max_dist == 0

    def test_find_similar_groups_no_duplicates(self):
        """測試無重複時回傳空清單"""
        hashes = [[0x00], [0xFF]]
        groups = image_viewer_rs.find_similar_groups(hashes, 2)
        assert len(groups) == 0

    def test_find_similar_groups_transitive(self):
        """測試遞移性分組（a~b, b~c → a,b,c 同組）"""
        hashes = [
            [0b11111111],
            [0b11111100],  # 距離 a=2
            [0b11110000],  # 距離 b=2, 距離 a=4
        ]
        groups = image_viewer_rs.find_similar_groups(hashes, 4)
        assert len(groups) == 1
        indices, _ = groups[0]
        assert len(indices) == 3

    def test_find_similar_groups_empty(self):
        """測試空清單"""
        groups = image_viewer_rs.find_similar_groups([], 5)
        assert len(groups) == 0

    def test_find_similar_groups_single(self):
        """測試只有 1 個 hash"""
        groups = image_viewer_rs.find_similar_groups([[0xFF]], 5)
        assert len(groups) == 0


# ============================================================================
# 整合測試：Python 適配層
# ============================================================================


class TestPythonIntegration:
    """測試 Python 適配層與 Rust 模組的整合。"""

    def test_hasher_md5_uses_rust(self, tmp_path):
        """測試 ImageHasher.compute_file_hash 使用 Rust 路徑"""
        from image_viewer.duplicate_checker.core.hasher import ImageHasher

        img_path = tmp_path / "test.png"
        Image.new("RGB", (50, 50), color="red").save(img_path)

        hasher = ImageHasher(algorithm="phash")
        result = hasher.compute_file_hash(img_path)

        # 與 Python 參考實作比較
        md5 = hashlib.md5()
        with open(img_path, "rb") as f:
            md5.update(f.read())
        assert result == md5.hexdigest()

    def test_hasher_phash_uses_rust(self, tmp_path):
        """測試 ImageHasher.compute_perceptual_hash 使用 Rust 路徑"""
        import imagehash
        from image_viewer.duplicate_checker.core.hasher import ImageHasher

        img_path = tmp_path / "test.png"
        Image.new("RGB", (200, 200), color="green").save(img_path)

        hasher = ImageHasher(algorithm="phash", hash_size=8)
        result = hasher.compute_perceptual_hash(img_path)

        # 應回傳 imagehash.ImageHash 物件
        assert isinstance(result, imagehash.ImageHash)
        # hash 矩陣應為 8x8
        assert result.hash.shape == (8, 8)

    def test_comparator_find_exact_duplicates(self, tmp_path):
        """測試 ImageComparator 精確比對（透過 Rust 路徑）"""
        from image_viewer.duplicate_checker.core.comparator import ImageComparator

        p1 = tmp_path / "img1.png"
        p2 = tmp_path / "img2.png"
        p3 = tmp_path / "img3.png"

        img_data = Image.new("RGB", (10, 10), color="blue")
        img_data.save(p1)
        img_data.save(p2)  # 和 p1 相同
        Image.new("RGB", (10, 10), color="red").save(p3)  # 不同

        comparator = ImageComparator(mode="exact")
        comparator.process_files([p1, p2, p3])
        groups = comparator.find_duplicates()

        assert len(groups) == 1
        assert groups[0].file_count == 2
        assert groups[0].match_type == "exact"
