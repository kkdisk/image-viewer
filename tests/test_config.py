import pytest
import json
import image_viewer.config as config_module
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
    with pytest.raises(ValueError, match="ZOOM_IN_FACTOR"):
        config.validate()


def test_config_validation_rejects_wrong_type():
    config = Config()
    config.MAX_ARCHIVE_FILES = "many"
    with pytest.raises(ValueError, match="MAX_ARCHIVE_FILES"):
        config.validate()


def test_config_optional_dependencies():
    from image_viewer.config import check_optional_dependencies, HEIC_SUPPORTED
    check_optional_dependencies()
    config = Config()
    if HEIC_SUPPORTED:
        assert '.heic' in config.SUPPORTED_IMAGE_EXTENSIONS


def test_json_load_preserves_heic_support(tmp_path, monkeypatch):
    monkeypatch.setattr(config_module, "HEIC_SUPPORTED", True)
    monkeypatch.setattr(config_module, "_DEPENDENCIES_CHECKED", True)
    config_path = tmp_path / "config.json"
    config_path.write_text(
        json.dumps({"SUPPORTED_IMAGE_EXTENSIONS": [".jpg", ".png"]}),
        encoding="utf-8",
    )

    config = Config()
    config.load_from_json(str(config_path))

    assert config.SUPPORTED_IMAGE_EXTENSIONS == (".jpg", ".png", ".heic")
