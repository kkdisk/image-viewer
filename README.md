# 增強型圖片瀏覽器 v1.9.0

## 簡介

這是一款使用 Python、PyQt6 和 Pillow 函式庫開發的高效能圖片瀏覽與編輯工具。它提供了流暢的圖片載入體驗、基本編輯功能以及現代化的使用者介面。

## 主要特色

- **非同步載入與縮圖快取**: 使用背景執行緒載入圖片和生成縮圖，並透過 LRU 快取機制提升重複載入的效能。
- **多種圖片格式支援**: 支援 JPG, PNG, BMP, GIF, TIFF, WEBP 等常見格式。
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
- **記憶體管理**: 監控記憶體用量，自動清理快取
- **自然排序 (可選)**: 若安裝 `natsort` 函式庫

## 專案結構

```
image-viewer/
├── run.py                 # 應用程式進入點
├── build.py               # PyInstaller 打包腳本
├── config.json            # 設定檔
├── dark_theme.qss         # 暗色主題樣式
├── requirements.txt       # 依賴套件
├── image_viewer/          # 主程式碼 (模組化)
│   ├── __init__.py
│   ├── main.py            # 應用程式初始化
│   ├── config.py          # 配置與常數
│   ├── core/
│   │   ├── editor_window.py   # 主視窗
│   │   ├── workers.py         # 背景執行緒 (效果、縮圖、載入)
│   │   └── resource_manager.py
│   ├── ui/
│   │   ├── widgets.py         # 自訂元件 (直方圖、放大鏡)
│   │   ├── ui_manager.py      # UI 建構
│   │   └── theme_manager.py   # 主題管理
│   └── utils/
│       └── decorators.py      # 裝飾器
└── env/                   # 虛擬環境 (建議)
```

## 需求

- Python 3.9+
- PyQt6
- Pillow
- psutil
- numpy

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
| `←` / `→` | 上一張/下一張 |
| 滑鼠滾輪 | 縮放 |

## 授權

此專案採用 MIT 授權。
