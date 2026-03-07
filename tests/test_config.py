import pytest
from image_viewer.config import Config

def test_config_default_values():
    config = Config()
    assert config.DEFAULT_THEME in ["light", "dark"]
    assert config.ZOOM_IN_FACTOR > 1.0
    assert 0 < config.ZOOM_OUT_FACTOR < 1.0
    assert config.MAX_UNDO_STEPS > 0
    assert isinstance(config.SUPPORTED_IMAGE_EXTENSIONS, tuple)

def test_config_validation():
    config = Config()
    # 預設應該通過驗證
    config.validate()
    
    # 測試驗證失敗
    config.ZOOM_IN_FACTOR = 0.5
    with pytest.raises(AssertionError, match="ZOOM_IN_FACTOR 必須大於 1.0"):
        config.validate()
