import json
import logging
from PIL import Image

# Pillow 版本相容性處理
try:
    LANCZOS_RESAMPLE = Image.Resampling.LANCZOS
    BILINEAR_RESAMPLE = Image.Resampling.BILINEAR
    NEAREST_RESAMPLE = Image.Resampling.NEAREST
except AttributeError:
    LANCZOS_RESAMPLE = Image.LANCZOS
    BILINEAR_RESAMPLE = Image.BILINEAR
    NEAREST_RESAMPLE = Image.NEAREST

# HEIC 支援檢查
HEIC_SUPPORTED = False
try:
    import pillow_heif
    pillow_heif.register_heif_opener()
    HEIC_SUPPORTED = True
    logging.info("pillow_heif 已註冊，HEIC 支援已啟用。")
except ImportError:
    logging.info("未安裝 pillow_heif，HEIC 支援已停用。")

# natsort 支援檢查 (自然排序)
NATSORT_ENABLED = False
try:
    import natsort
    NATSORT_ENABLED = True
    logging.info("找到 natsort 模組。")
except ImportError:
    logging.info("未找到 natsort 模組，將使用預設排序。")

from image_viewer._version import __version__

class Config:
    """集中管理應用程式的所有設定 (實例化版本)。"""
    
    DEFAULT_CONFIG = {
        "BASE_WINDOW_TITLE": f"增強型圖片瀏覽器 v{__version__}",
        "DEFAULT_THEME": "dark", # [v1.6 新增] "light" 或 "dark"
        "DEFAULT_WINDOW_SIZE": (1200, 800),
        "THUMBNAIL_SIZE": (128, 128),
        "MAX_UNDO_STEPS": 20,
        "ZOOM_IN_FACTOR": 1.25,
        "ZOOM_OUT_FACTOR": 0.8,
        "BLUR_RADIUS": 2,
        "MAX_IMAGE_FILE_SIZE": 524288000,
        "SUPPORTED_IMAGE_EXTENSIONS": ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.webp'),
        "SUPPORTED_ARCHIVE_EXTENSIONS": ('.7z',),
        "MEMORY_THRESHOLD_MB": 800,
        "MEMORY_CHECK_INTERVAL_MS": 30000,
        "HISTOGRAM_WIDTH": 280,
        "HISTOGRAM_HEIGHT": 150,
        "WHITE_BALANCE_TEMP_RANGE": (-100, 100),
        "WHITE_BALANCE_TINT_RANGE": (-100, 100),
        "MAGNIFIER_SIZE": 180,
        "MAGNIFIER_FACTOR_RANGE": (1.5, 8.0),
        "MAGNIFIER_DEFAULT_FACTOR": 2.0,
        "ADJUSTMENT_RANGE": (0, 200),
        "ADJUSTMENT_DEFAULT": 100,
        "THUMBNAIL_DRAFT_FACTOR": 2,
        "THUMBNAIL_MAX_DIMENSION_BEFORE_DOWNSCALE": 1000,
        "THUMBNAIL_INTERMEDIATE_SIZE": (500, 500),
        "CACHE_STATS_LOG_INTERVAL": 50,
        "MAGNIFIER_WINDOW_OFFSET": 20,
    }

    def __init__(self):
        """初始化 config，使用預設值填充"""
        for key, value in self.DEFAULT_CONFIG.items():
            setattr(self, key, value)
            
        self.DEFAULT_WINDOW_SIZE = tuple(self.DEFAULT_WINDOW_SIZE)
        self.SUPPORTED_IMAGE_EXTENSIONS = tuple(self.SUPPORTED_IMAGE_EXTENSIONS)
        self.WHITE_BALANCE_TEMP_RANGE = tuple(self.WHITE_BALANCE_TEMP_RANGE)
        self.WHITE_BALANCE_TINT_RANGE = tuple(self.WHITE_BALANCE_TINT_RANGE)
        self.MAGNIFIER_FACTOR_RANGE = tuple(self.MAGNIFIER_FACTOR_RANGE)
        self.ADJUSTMENT_RANGE = tuple(self.ADJUSTMENT_RANGE)
        self.THUMBNAIL_INTERMEDIATE_SIZE = tuple(self.THUMBNAIL_INTERMEDIATE_SIZE)

    def load_from_json(self, file_path: str):
        """嘗試從 JSON 檔案載入設定並覆蓋預設值"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                loaded_config = json.load(f)
            
            logging.info(f"成功從 {file_path} 載入設定。")
            
            for key, value in loaded_config.items():
                if hasattr(self, key):
                    if isinstance(getattr(self, key), tuple) and isinstance(value, list):
                        setattr(self, key, tuple(value))
                    else:
                        setattr(self, key, value)
                else:
                    logging.warning(f"Config JSON 中有多餘鍵值: {key}")
            
            self.DEFAULT_WINDOW_SIZE = tuple(self.DEFAULT_WINDOW_SIZE)
            self.SUPPORTED_IMAGE_EXTENSIONS = tuple(self.SUPPORTED_IMAGE_EXTENSIONS)

        except FileNotFoundError:
            logging.info(f"設定檔 {file_path} 未找到，使用預設設定。")
        except json.JSONDecodeError:
            logging.error(f"解析 {file_path} 失敗，使用預設設定。", exc_info=True)
        except Exception as e:
            logging.error(f"載入設定時發生未知錯誤，使用預設設定: {e}", exc_info=True)

    def validate(self):
        """驗證配置的合理性 (實例方法)"""
        assert self.ZOOM_IN_FACTOR > 1.0, "ZOOM_IN_FACTOR 必須大於 1.0"
        assert 0 < self.ZOOM_OUT_FACTOR < 1.0, "ZOOM_OUT_FACTOR 必須在 0 和 1 之間"
        assert self.MAX_UNDO_STEPS > 0, "MAX_UNDO_STEPS 必須為正數"
        assert self.MAX_IMAGE_FILE_SIZE > 0, "MAX_IMAGE_FILE_SIZE 必須為正數"
        assert self.DEFAULT_THEME in ["light", "dark"], "DEFAULT_THEME 必須是 'light' 或 'dark'"

    def apply_heic_support(self):
        """如果支援 HEIC，將其添加到擴展名列表中"""
        if HEIC_SUPPORTED:
            if '.heic' not in self.SUPPORTED_IMAGE_EXTENSIONS:
                self.SUPPORTED_IMAGE_EXTENSIONS += ('.heic',)
