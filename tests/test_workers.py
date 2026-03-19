import threading
import time
import pytest
from unittest.mock import MagicMock
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QThread
from PIL import Image

from image_viewer.core.workers import EffectWorker


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


@pytest.fixture
def worker(qapp):
    return EffectWorker()


class TestEffectWorkerBasic:
    """測試 EffectWorker 的基本功能"""

    def test_initial_state(self, worker):
        """測試初始狀態"""
        assert not worker._stop_event.is_set()

    def test_request_stop_sets_event(self, worker):
        """測試 request_stop 設定停止旗標"""
        worker.request_stop()
        assert worker._stop_event.is_set()
        # 重置
        worker._stop_event.clear()

    def test_apply_effect_success(self, worker, qapp):
        """測試效果正常套用"""
        test_image = Image.new('RGB', (10, 10), color='red')
        result_holder = {}

        def on_result(new_image, effect_id):
            result_holder['image'] = new_image
            result_holder['id'] = effect_id

        worker.result_ready.connect(on_result)

        def grayscale(img):
            return img.convert('L').convert('RGB')

        worker.apply_effect(test_image.copy(), grayscale, 1)

        assert 'image' in result_holder
        assert result_holder['id'] == 1
        assert result_holder['image'] is not None

        worker.result_ready.disconnect(on_result)
        if result_holder.get('image'):
            result_holder['image'].close()

    def test_apply_effect_error_handling(self, worker, qapp):
        """測試效果套用失敗時的錯誤處理"""
        test_image = Image.new('RGB', (10, 10))
        error_holder = {}

        def on_error(error_msg, effect_id):
            error_holder['msg'] = error_msg
            error_holder['id'] = effect_id

        worker.error_occurred.connect(on_error)

        def bad_effect(img):
            raise ValueError("故意產生的測試錯誤")

        worker.apply_effect(test_image.copy(), bad_effect, 42)

        assert 'msg' in error_holder
        assert error_holder['id'] == 42
        assert "故意產生的測試錯誤" in error_holder['msg']

        worker.error_occurred.disconnect(on_error)


class TestEffectWorkerStopMechanism:
    """測試 EffectWorker 的停止機制"""

    def test_stop_clears_at_start_of_apply(self, worker, qapp):
        """測試 apply_effect 開頭會清除 stop event（確保新效果不受上次 stop 影響）"""
        worker.request_stop()
        assert worker._stop_event.is_set()

        test_image = Image.new('RGB', (10, 10))
        result_holder = {'called': False}

        def on_result(new_image, effect_id):
            result_holder['called'] = True

        worker.result_ready.connect(on_result)

        def identity(img):
            return img.copy()

        # apply_effect 開頭會 clear stop event，所以效果會正常執行
        worker.apply_effect(test_image.copy(), identity, 1)
        assert result_holder['called'] is True

        worker.result_ready.disconnect(on_result)

    def test_stop_event_cleared_after_apply(self, worker, qapp):
        """測試 apply_effect 結束後 stop event 被清除"""
        test_image = Image.new('RGB', (10, 10))

        def identity(img):
            return img.copy()

        worker.apply_effect(test_image.copy(), identity, 1)
        # finally 區塊應該已經清除 stop event
        assert not worker._stop_event.is_set()

    def test_stop_during_effect_closes_result(self, worker, qapp):
        """測試在效果執行中設定 stop，結果應被丟棄"""
        test_image = Image.new('RGB', (10, 10))
        result_holder = {'called': False}

        def on_result(new_image, effect_id):
            result_holder['called'] = True

        worker.result_ready.connect(on_result)

        def slow_effect(img):
            # 模擬效果產生結果後再設定 stop
            result = img.copy()
            worker.request_stop()  # 在效果內部設定 stop
            return result

        worker.apply_effect(test_image.copy(), slow_effect, 1)

        # 由於 stop 在效果函式回傳後、emit 前被檢查到，結果不應該被 emit
        assert result_holder['called'] is False

        worker.result_ready.disconnect(on_result)
