import os
import pytest
from PIL import Image

from image_viewer.core.image_ops import (
    normalize_and_validate_image_path,
    build_white_balance_effect,
    compute_fine_tune_factors,
    build_fine_tune_effect,
)


# --- normalize_and_validate_image_path ---


class TestNormalizeAndValidateImagePath:
    """測試路徑正規化與驗證"""

    def test_valid_file(self, tmp_path):
        """測試正常檔案路徑"""
        img = Image.new("RGB", (10, 10))
        path = str(tmp_path / "test.png")
        img.save(path)

        result = normalize_and_validate_image_path(path, 524288000)
        assert os.path.isfile(result)

    def test_file_not_found(self, tmp_path):
        """測試檔案不存在時拋出 FileNotFoundError"""
        fake_path = str(tmp_path / "nonexistent.png")
        with pytest.raises(FileNotFoundError, match="檔案不存在"):
            normalize_and_validate_image_path(fake_path, 524288000)

    def test_not_a_file(self, tmp_path):
        """測試路徑指向目錄時拋出 ValueError"""
        with pytest.raises(ValueError, match="不是有效的檔案"):
            normalize_and_validate_image_path(str(tmp_path), 524288000)

    def test_file_too_large(self, tmp_path):
        """測試檔案超過大小限制時拋出 ValueError"""
        path = str(tmp_path / "big.bin")
        with open(path, "wb") as f:
            f.write(b"\x00" * 100)

        with pytest.raises(ValueError, match="檔案過大"):
            normalize_and_validate_image_path(path, 50)  # 限制 50 bytes

    def test_empty_file(self, tmp_path):
        """測試空檔案時拋出 ValueError"""
        path = str(tmp_path / "empty.png")
        with open(path, "wb"):
            pass

        with pytest.raises(ValueError, match="檔案為空"):
            normalize_and_validate_image_path(path, 524288000)


# --- compute_fine_tune_factors ---


class TestComputeFineTuneFactors:
    """測試滑桿值轉換為增強因子"""

    def test_default_values(self):
        """測試預設值回傳 (1.0, 1.0, 1.0)"""
        b, c, s = compute_fine_tune_factors(100, 100, 100, 100, 200)
        assert b == 1.0
        assert c == 1.0
        assert s == 1.0

    def test_clamping_high(self):
        """測試上限夾持"""
        b, c, s = compute_fine_tune_factors(300, 300, 300, 100, 200)
        assert b == 2.0  # max_factor = 200/100 = 2.0
        assert c == 2.0
        assert s == 2.0

    def test_clamping_low(self):
        """測試下限夾持 (不低於 0)"""
        b, c, s = compute_fine_tune_factors(-50, 0, 100, 100, 200)
        assert b == 0.0
        assert c == 0.0
        assert s == 1.0

    def test_normal_range(self):
        """測試正常範圍內的值"""
        b, c, s = compute_fine_tune_factors(150, 80, 120, 100, 200)
        assert b == 1.5
        assert c == 0.8
        assert s == 1.2


# --- build_white_balance_effect ---


class TestBuildWhiteBalanceEffect:
    """測試白平衡效果函式"""

    def test_returns_callable(self):
        """測試回傳可呼叫物件"""
        func = build_white_balance_effect(0, 0)
        assert callable(func)

    def test_neutral_effect(self):
        """測試中性值 (temp=0, tint=0) 不改變圖片"""
        img = Image.new("RGB", (10, 10), color=(128, 128, 128))
        func = build_white_balance_effect(0, 0)
        result = func(img)
        assert result.size == img.size
        assert result.mode == img.mode

    def test_warm_effect(self):
        """測試暖色調 (temp > 0) 增加紅色"""
        img = Image.new("RGB", (10, 10), color=(128, 128, 128))
        func = build_white_balance_effect(50, 0)
        result = func(img)
        r, g, b = result.getpixel((5, 5))
        # 暖色調應增加紅色 (r > 128)
        assert r > 128

    def test_cool_effect(self):
        """測試冷色調 (temp < 0) 增加藍色"""
        img = Image.new("RGB", (10, 10), color=(128, 128, 128))
        func = build_white_balance_effect(-50, 0)
        result = func(img)
        r, g, b = result.getpixel((5, 5))
        # 冷色調應增加藍色 (b > 128)
        assert b > 128

    def test_rgba_mode_preserved(self):
        """測試 RGBA 圖片模式被保留"""
        img = Image.new("RGBA", (10, 10), color=(128, 128, 128, 255))
        func = build_white_balance_effect(10, 10)
        result = func(img)
        assert result.mode == "RGBA"


# --- build_fine_tune_effect ---


class TestBuildFineTuneEffect:
    """測試細緻調整效果函式"""

    def test_returns_callable(self):
        """測試回傳可呼叫物件"""
        func = build_fine_tune_effect(1.0, 1.0, 1.0)
        assert callable(func)

    def test_neutral_effect(self):
        """測試中性值 (全為 1.0) 不改變圖片"""
        img = Image.new("RGB", (10, 10), color=(100, 100, 100))
        func = build_fine_tune_effect(1.0, 1.0, 1.0)
        result = func(img)
        assert result.size == img.size

    def test_brightness_increase(self):
        """測試提升亮度"""
        img = Image.new("RGB", (10, 10), color=(50, 50, 50))
        func = build_fine_tune_effect(2.0, 1.0, 1.0)
        result = func(img)
        r, g, b = result.getpixel((5, 5))
        # 亮度提升後，像素值應增加
        assert r > 50

    def test_error_handling_returns_original(self):
        """測試異常時回傳原始圖片的副本"""
        img = Image.new("RGB", (10, 10), color=(100, 100, 100))
        # 傳入極端值不應導致崩潰
        func = build_fine_tune_effect(0.01, 0.01, 0.01)
        result = func(img)
        assert result.size == img.size
