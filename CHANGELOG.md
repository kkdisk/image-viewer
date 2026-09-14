# Changelog

## [Unreleased]

## [2.4.0] - 2026-09-14

### Added

- 使用 Qt Multimedia 加入本機影片播放、暫停、seek、音量與靜音控制。
- Filmstrip 支援圖片與影片混合顯示及前後導覽。
- 新增 MP4、M4V、MOV、MKV、WEBM 與 AVI 檔案篩選。
- Filmstrip 使用單一非同步解碼器擷取影片第一個有效影格，並疊加播放圖示。
- 雙擊影片可進入全螢幕，控制列會在閒置後隱藏並於移動滑鼠時顯示。
- 狀態列即時顯示影片檔名、解析度、總長度及播放狀態。
- 多檔拖放會略過不支援的項目，開啟第一個有效媒體並掃描其所在資料夾。

### Changed

- 中央顯示區改為圖片檢視器與影片播放器分頁切換。
- 前後導覽泛化為媒體導覽，並保留既有圖片方法的相容介面。
- 將 Filmstrip 掃描、縮圖排程、快取與選取同步抽離至獨立 controller。
- 明確維持 GIF、APNG、Animated WebP、multi-page TIFF 與 HEIF sequence 的預設靜態影格顯示行為。

### Fixed

- 切換圖片／影片及關閉程式時停止播放器並清除媒體來源，避免殘留聲音或鎖住來源檔案。
- 修正 Qt 6.11 回報影片尺寸時因 signal handler 簽名不符造成的 crash。

## [2.3.4] - 2026-09-09

### Fixed

- 明確使用 queued Qt signal，確保圖片效果函數在 worker thread 執行。
- 正規化 Windows 路徑後再同步移除重複圖片結果。
- HEIC 可選支援擴充至 `.heif` 副檔名。

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
