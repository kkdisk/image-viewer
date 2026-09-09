# Changelog

## [2.3.3] - 2026-09-09

### Changed

- 將壓縮檔開啟流程抽離至 `ArchiveWorkflowMixin`。
- 將圖片效果執行緒生命週期抽離至 `EffectController`。
- 將 HEIC 與自然排序套件整理為真正的 optional dependencies。
- PyInstaller 僅收集目前環境已安裝的選擇性模組。
- 清理 Python 原始碼與測試的格式及 lint 問題。

### Added

- 新增 MIT `LICENSE`。
- 新增效果控制器的非同步與平行工作拒絕測試。
- 將 `autopep8` 加入開發依賴。

## [2.3.2] - 2026-09-09

### Fixed

- 限制 7z 解壓路徑、符號連結、檔案數與解壓容量。
- 修正圖片載入、效果處理與重複掃描的 QThread 關閉競態。
- 修正載入 JSON 設定後 HEIC 副檔名遺失。
- 修正批次刪除或移動部分失敗時的結果狀態不同步。
- 改善設定驗證並統一最低 Python 版本為 3.10。
