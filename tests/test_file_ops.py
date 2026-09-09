from pathlib import Path
import os

import pytest

from image_viewer.duplicate_checker.core.file_ops import FileOperator
from image_viewer.duplicate_checker.core.comparator import DuplicateGroup
from image_viewer.duplicate_checker.core.hasher import ImageInfo
from image_viewer.duplicate_checker.ui.results_panel import ResultsPanel
from PIL import Image


def test_batch_delete_reports_only_successful_paths(monkeypatch, tmp_path):
    operator = FileOperator()
    success = tmp_path / "success.jpg"
    failure = tmp_path / "failure.jpg"

    def fake_delete(path: Path) -> bool:
        if path == failure:
            raise PermissionError("denied")
        return True

    monkeypatch.setattr(operator, "delete_to_trash", fake_delete)
    result = operator.batch_delete([success, failure])

    assert result["success_count"] == 1
    assert result["fail_count"] == 1
    assert result["success_paths"] == [success]


def test_batch_move_reports_only_successful_paths(monkeypatch, tmp_path):
    operator = FileOperator()
    success = tmp_path / "success.jpg"
    failure = tmp_path / "failure.jpg"

    def fake_move(path: Path, destination: Path) -> Path:
        if path == failure:
            raise PermissionError("denied")
        return destination / path.name

    monkeypatch.setattr(operator, "move_file", fake_move)
    result = operator.batch_move([success, failure], tmp_path / "destination")

    assert result["success_count"] == 1
    assert result["fail_count"] == 1
    assert result["success_paths"] == [success]


def test_results_panel_removes_only_requested_paths(qtbot, tmp_path):
    paths = [tmp_path / f"image-{index}.png" for index in range(3)]
    for path in paths:
        Image.new("RGB", (8, 8), "red").save(path)

    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.set_results([
        DuplicateGroup(0, [ImageInfo(path) for path in paths], "exact")
    ])

    groups = panel.remove_paths([paths[0]])

    assert len(groups) == 1
    assert [info.filepath for info in groups[0].images] == paths[1:]
    assert panel._tree.topLevelItem(0).childCount() == 2


@pytest.mark.skipif(os.name != "nt", reason="Windows path normalization")
def test_results_panel_normalizes_windows_paths(qtbot, tmp_path):
    paths = [tmp_path / f"image-{index}.png" for index in range(3)]
    for path in paths:
        Image.new("RGB", (8, 8), "blue").save(path)

    panel = ResultsPanel()
    qtbot.addWidget(panel)
    panel.set_results([
        DuplicateGroup(0, [ImageInfo(path) for path in paths], "exact")
    ])
    differently_formatted = Path(str(paths[0]).upper().replace("\\", "/"))

    groups = panel.remove_paths([differently_formatted])

    assert [info.filepath for info in groups[0].images] == paths[1:]
