# 影片播放功能導入規劃

## 1. 目標

在不影響既有圖片瀏覽與編輯功能的前提下，為 ImageViewer 加入本機影片播放能力，並讓圖片與影片共同出現在下方 Filmstrip 檔案列表中。

第一階段聚焦於可靠的播放與媒體切換，不包含影片剪輯、轉檔、濾鏡或網路串流。

## 2. 可行性結論

- 可行性：高。
- 建議技術：PyQt6 Qt Multimedia。
- 主要元件：`QMediaPlayer`、`QVideoWidget`、`QAudioOutput`、`QStackedWidget`。
- 建議架構：圖片與影片使用各自的顯示及狀態控制器，共用檔案集合、Filmstrip 與上一個／下一個導覽。
- 不建議將影片逐幀轉為 Pillow 圖片播放，因為音畫同步、seek、效能與硬體解碼成本過高。

## 3. 第一階段範圍（MVP）

### 3.1 納入範圍

- 開啟本機影片檔案。
- 拖放影片至主視窗。
- 圖片與影片共同顯示於下方 Filmstrip。
- 依目前的自然排序或標準排序規則混合排列媒體檔案。
- 點擊 Filmstrip 項目時，在圖片檢視器與影片播放器間切換。
- 上一個／下一個可跨圖片與影片切換。
- 播放、暫停與停止。
- 播放進度顯示與 seek。
- 顯示目前時間與總長度。
- 音量控制與靜音。
- 保持影片長寬比。
- 顯示載入中、無法播放及不支援 codec 等錯誤。
- 關閉視窗或切換媒體時停止播放並釋放播放器資源。
- Windows PyInstaller 成品播放驗證。

### 3.2 暫不納入

- 影片剪輯、轉檔、旋轉、濾鏡與另存影片。
- 網路串流或遠端 URL。
- 7z 壓縮檔內的影片播放。
- 外掛字幕檔載入及字幕樣式設定。
- 音訊軌與字幕軌選擇 UI。
- 播放速度調整與逐格播放。
- 影片畫面截圖。
- 播放清單管理。
- 影片重複／相似檢查。

GIF、APNG、Animated WebP、multi-page TIFF 與 HEIF sequence 繼續沿用圖片
載入流程，只顯示預設靜態影格；不由影片播放器處理。

## 4. 支援格式策略

新增獨立設定 `SUPPORTED_VIDEO_EXTENSIONS`，初始建議值：

```python
('.mp4', '.m4v', '.mov', '.mkv', '.webm', '.avi')
```

副檔名只用於檔案篩選，不能保證檔案內的 codec 可被解碼。實際播放能力應以 `QMediaPlayer` 的媒體狀態及錯誤訊號為準，不應宣稱所有同副檔名檔案皆可播放。

首要驗證組合：

- MP4 + H.264 + AAC。
- MP4/MOV + H.265 + AAC（依硬體與 backend 能力）。
- MKV + H.264 + AAC。
- WebM + VP9 + Opus。
- 僅有影像、沒有音訊的影片。
- 僅有音訊軌、損毀或 codec 不支援的測試檔。

## 5. 架構設計

### 5.1 中央顯示區

以 `QStackedWidget` 管理兩個頁面：

```text
QStackedWidget
├─ ImagePage
│  └─ 現有 QScrollArea + QLabel
└─ VideoPage
   ├─ QVideoWidget
   └─ VideoControls
```

`ImagePage` 保留現有圖片縮放、平移、放大鏡與編輯行為。`VideoPage` 由獨立的播放器控制器管理，不經過 `ImageModel` 或 Pillow 載入流程。

### 5.2 媒體類型

新增明確的媒體類型判斷，例如：

```text
MediaKind.IMAGE
MediaKind.VIDEO
MediaKind.ARCHIVE
MediaKind.UNSUPPORTED
```

所有開檔入口必須先進行相同的分類，再分派至圖片載入器、影片播放器或壓縮檔流程，避免檔案對話框、拖放與 Filmstrip 各自維護不同判斷邏輯。

### 5.3 共用媒體列表

將目前圖片專用的 `image_list` 泛化為 `media_list`，並將相關方法逐步改名：

| 現有名稱 | 建議名稱 |
|---|---|
| `image_list` | `media_list` |
| `get_prev_image_path()` | `get_prev_media_path()` |
| `get_next_image_path()` | `get_next_media_path()` |
| `prev_image()` | `prev_media()` |
| `next_image()` | `next_media()` |

媒體列表包含支援的圖片與影片，維持單一排序與單一目前索引。壓縮檔不加入一般資料夾 Filmstrip。

為降低一次性修改風險，可以先保留舊方法作為相容 wrapper，待測試完整後再移除。

### 5.4 播放器控制器

新增 `VideoController`，負責：

- 建立並持有 `QMediaPlayer` 與 `QAudioOutput`。
- 設定與清除本機媒體來源。
- 播放、暫停、停止與 seek。
- 將 `positionChanged`、`durationChanged`、`playbackStateChanged`、`mediaStatusChanged` 與 `errorOccurred` 映射至 UI。
- 切換至圖片、關閉視窗或發生錯誤時停止播放。
- 避免 UI 直接散布播放器狀態判斷。

### 5.5 圖片與影片狀態隔離

影片模式下停用下列圖片專用功能：

- 儲存與另存圖片。
- 復原。
- 圖片縮放及最適化顯示。
- 旋轉、翻轉、濾鏡與細緻調整。
- 放大鏡。
- EXIF 與圖片直方圖。

切回圖片後依圖片是否成功載入恢復功能。若離開一張有未儲存修改的圖片，仍須先沿用現有儲存提示流程。

### 5.6 Filmstrip 職責切分

使用獨立 `FilmstripController` 管理資料夾掃描、混合排序、圖片與影片縮圖排程、
縮圖快取以及選取同步。主視窗只保留媒體切換決策與向後相容入口，避免後續加入
影片 metadata、全螢幕或播放清單時繼續擴大 `editor_window.py` 的職責。

## 6. Filmstrip 設計

### 6.1 MVP 呈現

- 圖片：沿用現有非同步縮圖。
- 影片：先顯示一致的影片圖示。
- 每個項目保留完整路徑及媒體類型資料。
- 可增加檔名 tooltip，避免相似縮圖難以辨識。
- 影片圖示需與圖片載入失敗圖示有明顯區別。

### 6.2 後續影片縮圖

第二階段再加入第一幀縮圖：

- 背景執行，不阻塞主 UI thread。
- 快取 key 至少包含完整路徑、檔案修改時間與目標尺寸。
- 在縮圖右下角疊加播放符號；取得 duration 後可再顯示影片長度。
- 解碼失敗時保留通用影片圖示，不應使整個 Filmstrip 失效。

不建議在 MVP 為每個列表項目同時建立一個 `QMediaPlayer`，以免大量初始化解碼器、增加記憶體與資源競爭。

## 7. UI 與快捷鍵

### 7.1 播放控制列

至少包含：

- 播放／暫停按鈕。
- 停止按鈕。
- seek slider。
- `目前時間 / 總長度`。
- 靜音按鈕。
- 音量 slider。

### 7.2 建議快捷鍵

| 快捷鍵 | 影片模式功能 |
|---|---|
| `Space` | 播放／暫停 |
| `Ctrl+Left` | 上一個媒體 |
| `Ctrl+Right` | 下一個媒體 |
| `Left` | 後退 5 秒 |
| `Right` | 前進 5 秒 |
| `Up` / `Down` | 調整音量 |
| `M` | 靜音切換 |
| `Esc` | 離開全螢幕 |

目前方向鍵用於上一張／下一張。影片模式採用 seek 後，應將跨檔案導覽改為 `Ctrl+Left`／`Ctrl+Right`，圖片模式可暫時保留原有方向鍵行為。

## 8. 預計修改範圍

| 檔案／模組 | 工作內容 |
|---|---|
| `image_viewer/config.py` | 新增影片副檔名與相關播放器設定；納入 tuple 正規化及驗證 |
| `config.json` | 加入可覆寫的影片副檔名設定 |
| `image_viewer/core/image_model.py` | 將共用瀏覽列表泛化，或抽出 `MediaCollectionModel` |
| `image_viewer/core/editor_window.py` | 開檔分流、媒體切換、拖放、導覽、清理與狀態更新 |
| `image_viewer/ui/ui_manager.py` | 建立 stacked central widget、影片頁面、控制列與動作狀態 |
| `image_viewer/core/video_controller.py` | 新增播放器生命週期及訊號處理 |
| `image_viewer/core/filmstrip_controller.py` | 管理媒體掃描、縮圖排程、快取與選取同步 |
| `image_viewer/core/media_types.py` | 集中管理媒體類型及副檔名分類（可選） |
| `image_viewer/core/workers.py` | 第二階段加入影片縮圖 worker；MVP 不需要 |
| `image_viewer/core/resource_manager.py` | 第二階段加入影片縮圖快取 |
| `build.py` | 確保 Qt Multimedia、MultimediaWidgets、backend plugin 與 FFmpeg DLL 被收集 |
| `requirements.txt` | 為 PyQt6 設定經驗證的版本範圍 |
| `README.md` | 更新格式、操作、快捷鍵與打包說明 |
| `CHANGELOG.md` | 完成功能後記錄版本變更 |

## 9. 實作階段

### Phase 0：播放能力驗證

- [x] 建立最小 `QMediaPlayer + QVideoWidget + QAudioOutput` spike。
- [x] 驗證 MP4/H.264/AAC 解碼、seek、音量與錯誤訊號。
- [x] 驗證目前 PyQt6 版本及 Windows Qt Multimedia backend。
- [x] 建立隔離的 PyInstaller 成品並完成本機啟動測試。
- [x] 確認成品包含 Qt Multimedia、FFmpeg plugin 與必要 codec DLL。

完成條件：開發環境與打包環境皆能穩定播放基準影片。

2026-09-14 驗證紀錄：PyQt 6.11 / Qt 6.11 成功解碼 W3C Sintel 測試影片的
H.264 854×480 影像與 AAC 音訊軌，取得有效影片影格及 52,208 ms duration；
隔離的 PyInstaller onefile 成品可正常啟動，且 archive 內含
`Qt6Multimedia.dll`、`Qt6MultimediaWidgets.dll`、`ffmpegmediaplugin.dll`、
`avcodec-61.dll`、`avformat-61.dll` 與 `swscale-8.dll`。乾淨 Windows VM 的
實機影音輸出仍保留於發行前驗收。

### Phase 1：媒體分類與混合列表

- [x] 新增影片副檔名設定。
- [x] 集中實作媒體類型判斷。
- [x] 將資料夾掃描改為圖片與影片混合掃描。
- [x] 將 gallery/list/navigation 命名及行為泛化。
- [x] Filmstrip 影片項目顯示通用影片圖示。
- [x] 更新檔案選擇器及拖放規則。
- [x] 補齊排序、索引與前後導覽測試。

完成條件：影片會與圖片一起出現在 Filmstrip，點擊及前後切換能正確取得媒體路徑。

### Phase 2：播放器 UI 與狀態整合

- [x] 建立 `VideoController`。
- [x] 將中央區域改為 `QStackedWidget`。
- [x] 建立影片頁面及控制列。
- [x] 實作播放、暫停、停止、seek、音量與靜音。
- [x] 實作圖片／影片模式切換。
- [x] 切換媒體前套用未儲存圖片提示。
- [x] 影片模式停用圖片專用 actions 與 docks。
- [x] 實作播放器錯誤與狀態訊息。
- [x] 實作快捷鍵與焦點規則。
- [x] 實作關閉與資源清理。

完成條件：圖片與影片可連續混合瀏覽，播放操作不影響圖片編輯流程。

### Phase 3：測試、文件與發行

- [x] 新增 controller 單元測試，以 mock 或 signal 驗證狀態轉換。
- [x] 新增媒體分類、列表與導覽測試。
- [x] 新增圖片／影片切換整合測試。
- [ ] 測試無音訊、損毀、零長度及不支援 codec 的檔案。
- [ ] 測試播放時切檔、刪除來源檔及關閉程式。
- [x] 更新 README、快捷鍵與支援格式說明。
- [ ] 執行乾淨 Windows 環境 PyInstaller smoke test（收集設定已完成）。
- [x] 執行既有完整測試，確認圖片與重複檢查功能無回歸。
- [x] 更新 CHANGELOG 與版本號。

完成條件：自動化測試通過，且乾淨 Windows 環境可播放基準影片。

2026-09-14 本機發行候選驗證：完整測試共 118 項通過；PyInstaller 6.20
成功建立 121,624,521-byte one-file 成品。封裝內容確認包含 Qt Multimedia、
FFmpeg multimedia plugin、avcodec、avformat 與 swscale，且成品可正常啟動並
持續運行。另以實際 H.264/AAC MP4 驗證 Qt 6.11 的無參數
`videoSizeChanged` 訊號，成功取得 464×688 尺寸及 6,041 ms 片長且無錯誤。
乾淨 Windows VM 的實際畫面與聲音播放仍待人工驗收。

### Phase 4：選配改善

- [x] 非同步擷取影片第一個有效影格縮圖。
- [ ] Filmstrip 顯示 duration。
- [x] 全螢幕播放，雙擊切換並自動隱藏控制列。
- [x] 狀態列顯示影片檔名、解析度、總長度與播放狀態。
- [x] 多檔拖放採資料夾導向，開啟第一個支援檔案後掃描其所在資料夾。
- [ ] 循環與播放速度。
- [ ] 字幕及多音軌選擇。
- [ ] 畫面擷取成圖片。

2026-09-14 縮圖驗證紀錄：使用單一排隊式 Qt Multimedia 解碼器成功從
H.264 MP4 取得第一個有效影格，輸出 128×128 等比例補邊縮圖並疊加播放符號；
縮圖快取會依檔案修改時間與大小失效，解碼錯誤或逾時則回退通用影片圖示。

## 10. 測試策略

### 10.1 單元測試

- 副檔名大小寫及未知格式分類。
- 圖片與影片混合排序。
- 目前媒體索引同步。
- 第一個／最後一個項目的導覽邊界。
- 圖片及影片模式對應的 action enabled state。
- 時間格式化及 slider 與毫秒位置換算。
- 播放器錯誤至使用者訊息的映射。

### 10.2 整合測試

- 圖片 → 影片 → 圖片切換。
- 有未儲存圖片時切換至影片。
- 播放期間切換至下一個媒體。
- 播放期間關閉視窗。
- seekable 與 non-seekable 狀態。
- 影片無音訊時的音量控制狀態。
- Filmstrip 重新掃描後維持目前選取。

### 10.3 手動／打包測試

- Windows 10 與 Windows 11。
- 有／無可用音訊裝置。
- 高 DPI 與多螢幕。
- 軟體解碼與常見 GPU 驅動。
- Unicode、空白及長路徑檔名。
- 1080p、4K、直向影片及可變幀率影片。
- PyInstaller `--onefile` 啟動、播放、切檔與結束。

CI 的 offscreen Qt 環境不適合驗證實際影音輸出，因此播放 smoke test 應另在具備顯示與音訊 backend 的 Windows runner 或人工發行檢查中執行。

## 11. 驗收標準

- [ ] 支援的影片副檔名會與圖片一起顯示於 Filmstrip。
- [ ] 混合列表排序、選取與上一個／下一個行為一致。
- [ ] MP4/H.264/AAC 基準影片可在開發版與打包版播放。
- [ ] 播放、暫停、停止、seek、音量及靜音可正常操作。
- [ ] 圖片與影片切換時不殘留上一段影片的影像或聲音。
- [ ] 影片模式不會誤啟用圖片編輯功能。
- [ ] 未儲存圖片不會因切換至影片而無提示遺失。
- [ ] 不支援或損毀的影片會顯示可理解的錯誤，程式不崩潰。
- [ ] 關閉程式後沒有殘留播放器、thread 或鎖住來源檔案。
- [ ] 既有測試全部通過，圖片瀏覽、編輯、壓縮檔與重複檢查功能無回歸。

## 12. 風險與緩解措施

| 風險 | 影響 | 緩解措施 |
|---|---|---|
| 容器可辨識但 codec 不支援 | 特定影片無法播放 | 以播放器錯誤為準；公開列出已驗證組合 |
| Qt/FFmpeg backend 跨平台差異 | 各平台行為不一致 | 鎖定 PyQt6 版本；使用實際平台測試矩陣 |
| PyInstaller 漏收 plugin 或 DLL | 開發版可播、成品不可播 | Phase 0 優先做打包 spike；乾淨 VM 驗證 |
| 混用 ImageModel 與影片狀態 | 邏輯耦合及回歸增加 | 建立獨立 VideoController；共用部分限於列表與路徑 |
| Filmstrip 影片縮圖消耗大量資源 | UI 卡頓、記憶體上升 | MVP 使用通用圖示；後續採 worker、快取及併發限制 |
| 方向鍵語意衝突 | 導覽或 seek 操作混亂 | 依媒體模式定義；跨檔案導覽提供 Ctrl 組合鍵 |
| `--onefile` 體積及啟動時間增加 | 使用體驗下降 | 量測後評估是否提供 `--onedir` 發行版本 |

## 13. 工作量估算

| 工作 | 預估 |
|---|---:|
| Phase 0 播放與打包 spike | 0.5～1 人日 |
| Phase 1 混合列表與媒體分類 | 1～2 人日 |
| Phase 2 播放器及 UI 整合 | 1.5～3 人日 |
| Phase 3 測試、文件與打包修正 | 1～2 人日 |
| MVP 合計 | 約 4～7 人日 |
| Phase 4 影片縮圖及進階功能 | 另估 2～5 人日以上 |

估算不包含影片剪輯、轉檔、串流及特殊 codec 授權處理。

## 14. 建議實作順序

1. 先完成最小播放器與 PyInstaller spike，排除 backend／部署風險。
2. 泛化媒體分類與 Filmstrip 清單，加入影片通用圖示。
3. 導入 `QStackedWidget` 與 `VideoController`。
4. 完成控制列、錯誤處理及圖片／影片狀態切換。
5. 補齊自動化測試與乾淨環境打包驗證。
6. MVP 穩定後才加入影片縮圖、全螢幕、字幕等功能。
