import os
from typing import Callable, Tuple

import numpy as np
from PIL import Image, ImageEnhance


def normalize_and_validate_image_path(
    path: str,
    max_image_file_size: int,
) -> str:
    """Normalize and validate an image path before loading."""
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


def build_white_balance_effect(
    temp: int,
    tint: int,
) -> Callable[[Image.Image], Image.Image]:
    """Create a white balance effect function using temperature and tint."""
    def white_balance_func(img: Image.Image) -> Image.Image:
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
    """Convert slider values to clamped enhancement factors."""
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
    """Create fine-tune effect for brightness/contrast/saturation."""
    def fine_tune_func(img: Image.Image) -> Image.Image:
        img_proc = img.copy()
        enhancer = ImageEnhance.Brightness(img_proc)
        img_proc = enhancer.enhance(max(0.01, brightness))
        enhancer = ImageEnhance.Contrast(img_proc)
        img_proc = enhancer.enhance(max(0.01, contrast))
        enhancer = ImageEnhance.Color(img_proc)
        img_proc = enhancer.enhance(max(0.01, saturation))
        return img_proc

    return fine_tune_func
