import os
import pytest
import tempfile
import py7zr
from image_viewer.core.archive_manager import ArchiveManager


@pytest.fixture
def manager():
    mgr = ArchiveManager()
    yield mgr
    mgr.cleanup()


@pytest.fixture
def sample_7z(tmp_path):
    """建立一個包含虛擬文字檔的 .7z 測試壓縮檔"""
    # 建立測試用文字檔
    txt_file = tmp_path / "hello.txt"
    txt_file.write_text("hello world", encoding="utf-8")

    archive_path = str(tmp_path / "test.7z")
    with py7zr.SevenZipFile(archive_path, 'w') as z:
        z.write(txt_file, "hello.txt")
    return archive_path


@pytest.fixture
def password_7z(tmp_path):
    """建立一個帶密碼的 .7z 測試壓縮檔"""
    txt_file = tmp_path / "secret.txt"
    txt_file.write_text("secret data", encoding="utf-8")

    archive_path = str(tmp_path / "password_test.7z")
    with py7zr.SevenZipFile(archive_path, 'w', password="test123") as z:
        z.write(txt_file, "secret.txt")
    return archive_path


class TestArchiveManagerExtraction:
    """測試 ArchiveManager 的解壓縮功能"""

    def test_extract_success(self, manager, sample_7z):
        """測試正常解壓縮"""
        success, result = manager.extract_7z(sample_7z)
        assert success is True
        assert os.path.isdir(result)
        # 確認檔案確實被解壓出來
        extracted_file = os.path.join(result, "hello.txt")
        assert os.path.exists(extracted_file)
        with open(extracted_file, encoding="utf-8") as f:
            assert f.read() == "hello world"

    def test_extract_nonexistent_file(self, manager):
        """測試解壓不存在的檔案"""
        success, result = manager.extract_7z("nonexistent.7z")
        assert success is False
        assert "失敗" in result or "Error" in result or "error" in result.lower()

    def test_extract_password_required(self, manager, password_7z):
        """測試需要密碼但未提供"""
        success, result = manager.extract_7z(password_7z)
        assert success is False
        assert result in ("需要密碼", "密碼錯誤")

    def test_extract_wrong_password(self, manager, password_7z):
        """測試提供錯誤密碼"""
        success, result = manager.extract_7z(password_7z, password="wrong")
        assert success is False

    def test_extract_correct_password(self, manager, password_7z):
        """測試提供正確密碼"""
        success, result = manager.extract_7z(password_7z, password="test123")
        assert success is True
        assert os.path.isdir(result)


class TestArchiveManagerLifecycle:
    """測試 ArchiveManager 的生命週期管理"""

    def test_cleanup_removes_temp_dir(self, manager, sample_7z):
        """測試 cleanup 方法能正確刪除暫存資料夾"""
        success, temp_path = manager.extract_7z(sample_7z)
        assert success is True
        assert os.path.isdir(temp_path)

        manager.cleanup()
        # 暫存目錄應該已經被刪除
        assert not os.path.exists(temp_path)

    def test_cleanup_resets_state(self, manager, sample_7z):
        """測試 cleanup 後狀態重置"""
        manager.extract_7z(sample_7z)
        manager.cleanup()
        assert manager.get_current_archive_path() is None
        assert manager.is_archive_open() is False

    def test_is_archive_open_initial(self, manager):
        """測試初始狀態"""
        assert manager.is_archive_open() is False
        assert manager.get_current_archive_path() is None

    def test_is_archive_open_after_extract(self, manager, sample_7z):
        """測試解壓後狀態"""
        manager.extract_7z(sample_7z)
        assert manager.is_archive_open() is True
        assert manager.get_current_archive_path() == sample_7z

    def test_second_extract_cleans_up_first(self, manager, sample_7z):
        """測試連續解壓會清理前一次的暫存"""
        success1, path1 = manager.extract_7z(sample_7z)
        assert success1 is True

        success2, path2 = manager.extract_7z(sample_7z)
        assert success2 is True
        # 第一個暫存目錄應該已經被清除
        assert not os.path.exists(path1)
        assert os.path.isdir(path2)

    def test_double_cleanup_safe(self, manager, sample_7z):
        """測試連續呼叫 cleanup 不會出錯"""
        manager.extract_7z(sample_7z)
        manager.cleanup()
        manager.cleanup()  # 第二次不應該拋出例外
        assert manager.is_archive_open() is False
