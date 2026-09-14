# 增強型圖片與影片瀏覽器


## 簡介

這是一款使用 Python、PyQt6 和 Pillow 函式庫開發的高效能圖片瀏覽、編輯與影片播放工具。它提供流暢的媒體瀏覽體驗、基本圖片編輯功能以及現代化的使用者介面。

## 主要特色

- **非同步載入與縮圖快取**: 使用背景執行緒載入圖片和生成縮圖，並透過 LRU 快取機制提升重複載入的效能。
- **多種圖片格式支援**: 支援 JPG, PNG, BMP, GIF, TIFF, WEBP 等常見格式；GIF、APNG、Animated WebP、multi-page TIFF 與 HEIF sequence 目前顯示預設靜態影格，不播放圖片動畫。
- **本機影片播放**: 支援 MP4、M4V、MOV、MKV、WEBM、AVI 檔案篩選，並提供播放、暫停、seek、音量與靜音控制；實際 codec 支援依 Qt Multimedia backend 而定。
- **影片狀態資訊**: 狀態列即時顯示目前影片的檔名、解析度、總長度與播放狀態。
- **圖片與影片混合預覽列**: Filmstrip 依檔名排列同一資料夾內的圖片與影片；影片會非同步產生第一個有效影格縮圖並疊加播放圖示。
- **多檔拖放**: 拖入多個項目時開啟第一個支援的檔案，Filmstrip 接著掃描該檔案所在資料夾；其他資料夾的拖入項目不會建立臨時清單。
- **HEIC 支援 (可選)**: 若安裝 `pillow-heif` 函式庫，可支援 HEIC/HEIF 格式。
- **基本圖片編輯**:
  - 調整尺寸、旋轉、翻轉
  - 濾鏡效果 (反轉、灰階、模糊、銳化、懷舊)
  - 細緻調整 (亮度、對比、飽和度)
  - 白平衡調整 (色溫、色調)
  - 多達 20 步的操作復原
- **使用者介面**:
  - 暗色/亮色主題切換
  - 可停靠的側邊欄 (EXIF 資訊、效果調整、直方圖)
  - 底部圖片預覽列 (Filmstrip)
  - 圖片拖放開啟、放大鏡功能
  - 滑鼠滾輪縮放、拖曳平移
- **EXIF 資訊與直方圖顯示**
- **重複圖片檢查工具 (v2.1 新增，v2.2 引入 Rust 加速)**:
  - 使用感知雜湊 (pHash) 偵測視覺相似圖片
  - 支援 MD5 精確比對
  - **Rust 效能加速 (v2.2+)**：整合 Rust 原生擴充模組 (`image_viewer_rs`)，使用 Rayon 進行多執行緒平行計算，大幅提升大批檔案的雜湊計算與 Union-Find 分群比對效能（內建 Graceful Fallback 回退機制）。
  - 批次刪除或移動重複檔案，節省磁碟空間
  - 現代化 QSS 美化介面
- **記憶體管理**: 監控記憶體用量，自動清理快取
- **自然排序 (可選)**: 若安裝 `natsort` 函式庫

## 專案結構

```
image-viewer/
├── run.py                 # 應用程式進入點
├── build.py               # PyInstaller 打包腳本
├── config.json            # 設定檔
├── dark_theme.qss         # 暗色主題樣式
├── requirements.txt       # 執行期依賴
├── requirements-dev.txt   # 開發與測試依賴
├── requirements-optional.txt # 可選功能依賴
├── image_viewer/          # 主程式碼 (模組化)
│   ├── __init__.py
│   ├── main.py            # 應用程式初始化
│   ├── config.py          # 配置與常數
│   ├── core/
│   │   ├── editor_window.py   # 主視窗
│   │   ├── archive_workflow.py # 非同步壓縮檔開啟流程
│   │   ├── filmstrip_controller.py # 混合媒體列表與縮圖
│   │   ├── media_types.py     # 媒體類型分類
│   │   ├── video_controller.py # 影片播放與控制列狀態
│   │   ├── video_fullscreen_controller.py # 影片全螢幕行為
│   │   ├── video_thumbnailer.py # 非同步影片縮圖
│   │   ├── workers.py         # 背景執行緒 (效果、縮圖、載入)
│   │   └── resource_manager.py
│   ├── ui/
│   │   ├── widgets.py         # 自訂元件 (直方圖、放大鏡)
│   │   ├── ui_manager.py      # UI 建構
│   │   └── theme_manager.py   # 主題管理
│   ├── utils/
│   │   └── decorators.py      # 裝飾器
│   └── duplicate_checker/     # 重複圖片檢查工具模組 (v2.1 新增)
│       ├── core/              # 核心邏輯 (雜湊計算、比對、檔案操作)
│       ├── ui/                # UI 面板 (掃描、結果、預覽)
│       └── workers/           # 背景掃描執行緒
└── env/                   # 虛擬環境 (建議)
```

## 需求

- Python 3.10+
- PyQt6
- Qt Multimedia（隨 PyQt6 安裝）
- Pillow
- psutil
- numpy
- imagehash (重複檢查所需)
- send2trash (安全刪除所需)
- scipy (感知雜湊計算)
- PyWavelets (小波雜湊支援)

**可選**:
- pillow-heif (HEIC/HEIF 支援)
- natsort (自然排序)

## 快速開始

### 1. 建立虛擬環境 (建議)

```bash
python -m venv env
.\env\Scripts\activate  # Windows
# source env/bin/activate  # Linux/macOS
```

### 2. 安裝依賴

```bash
pip install -r requirements.txt
```

### 2.1 安裝開發與測試依賴 (可選)

```bash
pip install -r requirements-dev.txt
```

### 2.2 安裝可選功能依賴 (HEIC / 自然排序)

```bash
pip install -r requirements-optional.txt
```

### 2.3 安裝 Rust 加速擴充模組 (可選，極力推薦)

本專案支援使用 Rust 編譯的二進位擴充模組 `image_viewer_rs`。若要編譯並安裝該模組，請確保本機已安裝 Rust 工具鏈 (rustc/cargo)，然後執行以下指令：

```bash
# 安裝編譯工具 maturin 到虛擬環境
pip install maturin

# 編譯並安裝擴充模組到虛擬環境
cd rust_ext
# Windows 環境下設定 VIRTUAL_ENV 後編譯
set VIRTUAL_ENV=d:\code\cytesi\image-viewer_github\env
..\env\Scripts\maturin develop --release
```

安裝完成後，重複檢查工具在處理大量圖片時會自動啟用 Rust 效能加速，若未安裝則自動降級使用 Python 實作。

### 3. 執行應用程式

```bash
python run.py
# 或使用虛擬環境
.\env\Scripts\python run.py
```

## 打包成執行檔

確保已安裝 PyInstaller:

```bash
pip install pyinstaller
```

執行打包腳本:

```bash
python build.py
```

執行檔將會產生於 `dist/ImageViewer.exe`。

## 快捷鍵

| 快捷鍵 | 功能 |
|--------|------|
| `Ctrl+O` | 開啟檔案 |
| `Ctrl+S` | 儲存 |
| `Ctrl+Z` | 復原 |
| `Ctrl+M` | 開啟/關閉放大鏡 |
| `Ctrl+T` | 切換主題 |
| `←` / `→` | 圖片模式：上一個/下一個；影片模式：後退/前進 5 秒 |
| `Ctrl+←` / `Ctrl+→` | 上一個/下一個媒體 |
| `Space` | 影片播放/暫停 |
| `↑` / `↓` | 影片音量增加/減少 |
| `M` | 影片靜音切換 |
| 雙擊影片 | 進入／離開全螢幕；控制列在閒置時自動隱藏 |
| `Esc` | 離開影片全螢幕 |
| 滑鼠滾輪 | 縮放 |

## 授權

此專案採用 [MIT 授權](LICENSE)。
