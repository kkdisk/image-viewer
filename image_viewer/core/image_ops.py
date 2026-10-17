import logging
import os
from typing import Callable, Tuple

import numpy as np
from PIL import Image, ImageEnhance

try:
    import image_viewer_rs
    HAS_RUST_EXT = True
except ImportError:
    HAS_RUST_EXT = False


def normalize_and_validate_image_path(
    path: str,
    max_image_file_size: int,
) -> str:
    """正規化並驗證圖片路徑，在載入前確認檔案存在且大小合理。"""
    normalized_path = os.path.normcase(os.path.normpath(path))

    if not os.path.exists(normalized_path):
        raise FileNotFoundError(f"檔案不存在: {normalized_path}")
    if not os.path.isfile(normalized_path):
        raise ValueError(f"不是有效的檔案: {normalized_path}")

    file_size = os.path.getsize(normalized_path)
    if file_size > max_image_file_size:
        raise ValueError(
            f"檔案過大 ({file_size / (1024 * 1024):.1f} MB), "
            f"超過限制 ({max_image_file_size / (1024 * 1024):.0f} MB)"
        )
    if file_size == 0:
        raise ValueError("檔案為空")

    return normalized_path


def validate_image_dimensions(image, max_pixels):
    """在解碼像素前限制展開尺寸，避免小型壓縮圖片耗盡記憶體。"""
    if image.width <= 0 or image.height <= 0 or image.width * image.height > max_pixels:
        raise ValueError(f"圖片像素數超過安全限制 ({max_pixels:,} pixels)")


def build_white_balance_effect(
    temp: int,
    tint: int,
) -> Callable[[Image.Image], Image.Image]:
    """建立白平衡效果函式，根據色溫與色調參數調整圖片色彩。"""
    def white_balance_func(img: Image.Image) -> Image.Image:
        if HAS_RUST_EXT:
            try:
                img_rgba = img.convert("RGBA")
                result_bytes = image_viewer_rs.apply_white_balance(
                    img_rgba.tobytes(),
                    img_rgba.width,
                    img_rgba.height,
                    4,  # channels
                    temp,
                    tint
                )
                return Image.frombytes("RGBA", img_rgba.size, bytes(result_bytes)).convert(img.mode)
            except Exception as e:
                logging.warning(f"Rust 白平衡加速失敗，退回 Python 實作: {e}")

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

    return white_balance_func


def compute_fine_tune_factors(
    brightness_value: int,
    contrast_value: int,
    saturation_value: int,
    adjustment_default: int,
    adjustment_max: int,
) -> Tuple[float, float, float]:
    """將滑桿數值轉換為夾持後的增強因子，回傳 (brightness, contrast, saturation)。"""
    brightness = brightness_value / adjustment_default
    contrast = contrast_value / adjustment_default
    saturation = saturation_value / adjustment_default

    max_factor = adjustment_max / adjustment_default
    brightness = max(0.0, min(brightness, max_factor))
    contrast = max(0.0, min(contrast, max_factor))
    saturation = max(0.0, min(saturation, max_factor))
    return brightness, contrast, saturation


def build_fine_tune_effect(
    brightness: float,
    contrast: float,
    saturation: float,
) -> Callable[[Image.Image], Image.Image]:
    """建立亮度/對比/飽和度的細緻調整效果函式。"""
    def fine_tune_func(img: Image.Image) -> Image.Image:
        if HAS_RUST_EXT:
            try:
                img_rgba = img.convert("RGBA")
                result_bytes = image_viewer_rs.apply_fine_tune(
                    img_rgba.tobytes(),
                    img_rgba.width,
                    img_rgba.height,
                    4,  # channels
                    brightness,
                    contrast,
                    saturation
                )
                return Image.frombytes("RGBA", img_rgba.size, bytes(result_bytes)).convert(img.mode)
            except Exception as e:
                logging.warning(f"Rust 細部調整加速失敗，退回 Python 實作: {e}")

        img_proc = img.copy()
        try:
            enhancer = ImageEnhance.Brightness(img_proc)
            img_proc = enhancer.enhance(max(0.01, brightness))
            enhancer = ImageEnhance.Contrast(img_proc)
            img_proc = enhancer.enhance(max(0.01, contrast))
            enhancer = ImageEnhance.Color(img_proc)
            img_proc = enhancer.enhance(max(0.01, saturation))
        except Exception as e:
            logging.error(f"應用 Enhancer 時出錯: {e}")
            return img.copy()
        return img_proc

    return fine_tune_func
