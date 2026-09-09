import pytest
from PIL import Image
import numpy as np

try:
    import image_viewer_rs
    HAS_RUST_EXT = True
except ImportError:
    HAS_RUST_EXT = False

# 導入原始 Python 實作以供比較
# 我們需要定義原始的 numpy 實作來比對，因為 image_ops.py 中的函數已經被我們加上 if HAS_RUST_EXT 攔截了
# 但沒關係，我們可以強制呼叫原始版本，或者直接將 image_ops.py 的函數裡 temporarily bypass

def py_apply_white_balance(img: Image.Image, temp: int, tint: int) -> Image.Image:
    img_rgb = img.convert("RGB")
    img_np = np.array(img_rgb, dtype=np.float32) / 255.0
    r, g, b = img_np[:, :, 0], img_np[:, :, 1], img_np[:, :, 2]

    temp_factor = temp / 100.0
    if temp_factor > 0:
        r *= 1.0 + temp_factor * 0.8
        b *= 1.0 - temp_factor * 0.5
    else:
        r *= 1.0 + temp_factor * 0.5
        b *= 1.0 - temp_factor * 0.8

    tint_factor = tint / 100.0
    g *= 1.0 + tint_factor * 0.6
    r *= 1.0 - tint_factor * 0.1
    b *= 1.0 - tint_factor * 0.1

    img_np = np.clip(np.stack([r, g, b], axis=-1), 0.0, 1.0) * 255.0
    return Image.fromarray(img_np.astype(np.uint8)).convert(img.mode)

@pytest.fixture
def test_image():
    # 建立一張包含所有基本顏色與灰階的漸層測試圖
    img = Image.new('RGBA', (100, 100))
    pixels = img.load()
    for x in range(100):
        for y in range(100):
            pixels[x, y] = (int(x * 2.55), int(y * 2.55), int((x + y) / 2 * 2.55), 255)
    return img

@pytest.mark.skipif(not HAS_RUST_EXT, reason="Rust 擴充模組未安裝")
def test_white_balance_rust_vs_python(test_image):
    # 測試多組極端與正常的色溫/色調參數
    params = [
        (0, 0),         # 中性
        (50, 0),        # 偏暖
        (-50, 0),       # 偏冷
        (0, 50),        # 偏綠/洋紅
        (0, -50),
        (30, -20),
        (-80, 70),
    ]

    for temp, tint in params:
        # Python Numpy 版本
        img_py = py_apply_white_balance(test_image, temp, tint)

        # Rust 版本
        img_rgba = test_image.convert("RGBA")
        result_bytes = image_viewer_rs.apply_white_balance(
            img_rgba.tobytes(),
            img_rgba.width,
            img_rgba.height,
            4,
            temp,
            tint
        )
        img_rs = Image.frombytes("RGBA", img_rgba.size, bytes(result_bytes)).convert(test_image.mode)

        # 比較兩張圖片的差異
        np_py = np.array(img_py)
        np_rs = np.array(img_rs)

        # 由於浮點數計算順序差異，容許最大的像素差異為 1
        max_diff = np.max(np.abs(np_py.astype(int) - np_rs.astype(int)))
        assert max_diff <= 1, f"白平衡結果不一致 (temp={temp}, tint={tint}), 最大差異: {max_diff}"

@pytest.mark.skipif(not HAS_RUST_EXT, reason="Rust 擴充模組未安裝")
def test_fine_tune_rust_basic(test_image):
    # 由於 Python 原本使用的是 PIL ImageEnhance，其內部有建立 Lookup Table 與多重轉換
    # 而 Rust 使用了我們手寫的點運算以追求效能，兩者的結果不一定完全位元級相同，
    # 但應該要能正確運行並且視覺上等效。這裡我們確保 Rust 函數不會掛掉並返回正確形狀與長度。

    img_rgba = test_image.convert("RGBA")

    # 測試增強對比與飽和度
    result_bytes = image_viewer_rs.apply_fine_tune(
        img_rgba.tobytes(),
        img_rgba.width,
        img_rgba.height,
        4,
        1.2, # brightness
        1.5, # contrast
        0.8  # saturation
    )

    assert len(result_bytes) == len(img_rgba.tobytes())
    img_rs = Image.frombytes("RGBA", img_rgba.size, bytes(result_bytes)).convert(test_image.mode)

    # 確定不是全黑或全白
    np_rs = np.array(img_rs)
    assert np.mean(np_rs) > 10.0
    assert np.mean(np_rs) < 245.0

    # 測試 1.0 (不改變) 的情況
    result_bytes_identity = image_viewer_rs.apply_fine_tune(
        img_rgba.tobytes(),
        img_rgba.width,
        img_rgba.height,
        4,
        1.0, 1.0, 1.0
    )
    img_identity = Image.frombytes("RGBA", img_rgba.size, bytes(result_bytes_identity)).convert(test_image.mode)

    max_diff = np.max(np.abs(np.array(img_identity).astype(int) - np.array(test_image).astype(int)))
    assert max_diff == 0, "增強因子為 1.0 時應該返回原圖"
