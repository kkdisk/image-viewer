import json
import logging
import importlib
from PIL import Image

from image_viewer._version import __version__

# Pillow 版本相容性處理
try:
    LANCZOS_RESAMPLE = Image.Resampling.LANCZOS
    BILINEAR_RESAMPLE = Image.Resampling.BILINEAR
    NEAREST_RESAMPLE = Image.Resampling.NEAREST
except AttributeError:
    LANCZOS_RESAMPLE = Image.LANCZOS
    BILINEAR_RESAMPLE = Image.BILINEAR
    NEAREST_RESAMPLE = Image.NEAREST

# 這些變數將由 check_optional_dependencies() 初始化
HEIC_SUPPORTED = False
NATSORT_ENABLED = False
_DEPENDENCIES_CHECKED = False


def check_optional_dependencies(force: bool = False):
    """檢查並初始化選擇性依賴項（如 HEIC 支援與自然排序）。
    此函式可在 logging 設置完成後呼叫，亦會在 Config 初次建立時自動自檢。
    """
    global HEIC_SUPPORTED, NATSORT_ENABLED, _DEPENDENCIES_CHECKED
    if _DEPENDENCIES_CHECKED and not force:
        return

    _DEPENDENCIES_CHECKED = True

    # HEIC 支援檢查
    try:
        import pillow_heif
        pillow_heif.register_heif_opener()
        HEIC_SUPPORTED = True
        logging.info("pillow_heif 已註冊，HEIC 支援已啟用。")
    except ImportError:
        logging.info("未安裝 pillow_heif，HEIC 支援已停用。")
    except Exception as e:
        logging.error(f"初始化 pillow_heif 時發生錯誤: {e}")

    # natsort 支援檢查 (自然排序)
    try:
        importlib.import_module("natsort")
        NATSORT_ENABLED = True
        logging.info("找到 natsort 模組。")
    except ImportError:
        logging.info("未找到 natsort 模組，將使用預設排序。")
    except Exception as e:
        logging.error(f"初始化 natsort 時發生錯誤: {e}")


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
        "MAX_ARCHIVE_FILES": 10000,
        "MAX_ARCHIVE_SINGLE_FILE_SIZE": 524288000,
        "MAX_ARCHIVE_UNCOMPRESSED_SIZE": 2147483648,
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

    # 需要確保為 tuple 的欄位名稱
    _TUPLE_FIELDS = (
        'DEFAULT_WINDOW_SIZE', 'SUPPORTED_IMAGE_EXTENSIONS', 'SUPPORTED_ARCHIVE_EXTENSIONS',
        'WHITE_BALANCE_TEMP_RANGE', 'WHITE_BALANCE_TINT_RANGE',
        'MAGNIFIER_FACTOR_RANGE', 'ADJUSTMENT_RANGE', 'THUMBNAIL_INTERMEDIATE_SIZE',
        'THUMBNAIL_SIZE',
    )

    def __init__(self):
        """初始化 config，使用預設值填充"""
        check_optional_dependencies()
        for key, value in self.DEFAULT_CONFIG.items():
            setattr(self, key, value)
        self._ensure_tuples()
        self.apply_heic_support()

    def _ensure_tuples(self):
        """確保所有應為 tuple 的欄位型別正確"""
        for field in self._TUPLE_FIELDS:
            if hasattr(self, field):
                val = getattr(self, field)
                if not isinstance(val, tuple):
                    setattr(self, field, tuple(val))

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

            self._ensure_tuples()
            # JSON 可能覆蓋 SUPPORTED_IMAGE_EXTENSIONS；重新合併動態格式。
            self.apply_heic_support()

        except FileNotFoundError:
            logging.info(f"設定檔 {file_path} 未找到，使用預設設定。")
        except json.JSONDecodeError:
            logging.error(f"解析 {file_path} 失敗，使用預設設定。", exc_info=True)
        except Exception as e:
            logging.error(f"載入設定時發生未知錯誤，使用預設設定: {e}", exc_info=True)

    def validate(self):
        """驗證配置的合理性 (實例方法)"""
        checks = (
            (isinstance(self.ZOOM_IN_FACTOR, (int, float)) and self.ZOOM_IN_FACTOR > 1.0,
             "ZOOM_IN_FACTOR 必須是大於 1.0 的數字"),
            (isinstance(self.ZOOM_OUT_FACTOR, (int, float)) and 0 < self.ZOOM_OUT_FACTOR < 1.0,
             "ZOOM_OUT_FACTOR 必須是介於 0 和 1 之間的數字"),
            (isinstance(self.MAX_UNDO_STEPS, int) and self.MAX_UNDO_STEPS > 0,
             "MAX_UNDO_STEPS 必須為正整數"),
            (isinstance(self.MAX_IMAGE_FILE_SIZE, int) and self.MAX_IMAGE_FILE_SIZE > 0,
             "MAX_IMAGE_FILE_SIZE 必須為正整數"),
            (isinstance(self.MAX_ARCHIVE_FILES, int) and self.MAX_ARCHIVE_FILES > 0,
             "MAX_ARCHIVE_FILES 必須為正整數"),
            (isinstance(self.MAX_ARCHIVE_SINGLE_FILE_SIZE, int)
             and self.MAX_ARCHIVE_SINGLE_FILE_SIZE > 0,
             "MAX_ARCHIVE_SINGLE_FILE_SIZE 必須為正整數"),
            (isinstance(self.MAX_ARCHIVE_UNCOMPRESSED_SIZE, int)
             and self.MAX_ARCHIVE_UNCOMPRESSED_SIZE > 0,
             "MAX_ARCHIVE_UNCOMPRESSED_SIZE 必須為正整數"),
            (self.DEFAULT_THEME in ("light", "dark"),
             "DEFAULT_THEME 必須是 'light' 或 'dark'"),
        )
        for is_valid, message in checks:
            if not is_valid:
                raise ValueError(message)

    def apply_heic_support(self):
        """如果支援 HEIC，將其添加到擴展名列表中"""
        if HEIC_SUPPORTED:
            if '.heic' not in self.SUPPORTED_IMAGE_EXTENSIONS:
                self.SUPPORTED_IMAGE_EXTENSIONS += ('.heic',)
