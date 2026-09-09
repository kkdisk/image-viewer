import os
import pytest
import py7zr
from types import SimpleNamespace
from image_viewer.core.archive_manager import ArchiveManager
from image_viewer.core.workers import ArchiveExtractWorker


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

    @pytest.mark.parametrize("name", ["../outside.txt", "/absolute.txt", "C:/outside.txt"])
    def test_rejects_unsafe_member_paths(self, name):
        manager = ArchiveManager()
        archive = SimpleNamespace(
            list=lambda: [SimpleNamespace(filename=name, uncompressed=1)]
        )
        with pytest.raises(ValueError, match="不安全路徑"):
            manager._validate_archive_entries(archive)

    def test_rejects_archive_limits(self):
        manager = ArchiveManager(max_files=1, max_single_file_size=5, max_total_size=8)
        too_many = SimpleNamespace(list=lambda: [
            SimpleNamespace(filename="a", uncompressed=1),
            SimpleNamespace(filename="b", uncompressed=1),
        ])
        with pytest.raises(ValueError, match="過多項目"):
            manager._validate_archive_entries(too_many)

        too_large = SimpleNamespace(
            list=lambda: [SimpleNamespace(filename="large.bin", uncompressed=6)]
        )
        with pytest.raises(ValueError, match="檔案過大"):
            manager._validate_archive_entries(too_large)

    def test_rejects_symbolic_links(self):
        manager = ArchiveManager()
        archive = SimpleNamespace(list=lambda: [
            SimpleNamespace(filename="link", uncompressed=1, is_symlink=True)
        ])
        with pytest.raises(ValueError, match="符號連結"):
            manager._validate_archive_entries(archive)


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


def test_archive_extract_worker_runs_off_main_thread(qtbot, manager, sample_7z):
    worker = ArchiveExtractWorker(manager, sample_7z)
    with qtbot.waitSignal(worker.extraction_completed, timeout=5000) as blocker:
        worker.start()
    worker.wait()

    success, extracted_path, original_path = blocker.args
    assert success is True
    assert os.path.isdir(extracted_path)
    assert original_path == sample_7z
