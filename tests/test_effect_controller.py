from PIL import Image

from image_viewer.core.effect_controller import EffectController


def test_effect_controller_emits_result_and_clears_busy(qtbot):
    controller = EffectController()
    source = Image.new("RGB", (4, 4), "red")

    with qtbot.waitSignal(controller.result_ready, timeout=3000) as blocker:
        assert controller.start(source, lambda image: image.copy()) is True
        assert controller.is_busy is True

    result = blocker.args[0]
    assert result.getpixel((0, 0)) == (255, 0, 0)
    result.close()
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=3000)


def test_effect_controller_rejects_parallel_work(qtbot):
    controller = EffectController()
    source = Image.new("RGB", (4, 4), "blue")

    with qtbot.waitSignal(controller.result_ready, timeout=3000) as blocker:
        assert controller.start(source, lambda image: image.copy()) is True
        second = Image.new("RGB", (4, 4), "green")
        assert controller.start(second, lambda image: image.copy()) is False
        second.close()

    blocker.args[0].close()
    qtbot.waitUntil(lambda: not controller.is_busy, timeout=3000)
