# 增強型圖片瀏覽器 v1.4.13

## 簡介

這是一款使用 Python、PyQt6 和 Pillow 函式庫開發的高效能圖片瀏覽與編輯工具。它提供了流暢的圖片載入體驗、基本編輯功能以及現代化的使用者介面。

## 主要特色
- 非同步載入與縮圖快取: 使用背景執行緒載入圖片和生成縮圖，並透過快取機制（LRU）提升重複載入的效能，確保 UI 流暢不卡頓。
- 多種圖片格式支援: 支援常見的圖片格式，如 JPG, PNG, BMP, GIF, TIFF, WEBP 等。
- HEIC 支援 (可選): 若安裝 pillow-heif 函式庫，可支援 HEIC/HEIF 格式。
- 基本圖片編輯:
  - 調整尺寸 (Resize)
  - 旋轉 (Rotate Left/Right)
  - 翻轉 (Flip Horizontal/Vertical)
  - 濾鏡效果 (反轉、灰階、模糊、銳化、懷舊)
  - 細緻調整 (亮度、對比、飽和度)
  - 白平衡調整 (色溫、色調)
  - 復原功能: 支援多達 20 步的操作復原。
- 使用者介面:
  - 現代化的暗色/亮色主題切換。
  - 可停靠的側邊欄 (EXIF 資訊、效果調整、直方圖)。
  - 底部圖片預覽列 (Filmstrip)。
  - 圖片拖放開啟。
  - 放大鏡功能。
  - 滑鼠滾輪縮放、拖曳平移。
- EXIF 資訊顯示: 可檢視圖片的 EXIF 中繼資料。
- 直方圖顯示: 即時顯示圖片的 RGB 及亮度直方圖。
- 記憶體管理: 監控記憶體使用量，並在超過閾值時自動清理快取。
- 錯誤處理: 針對檔案載入、效果套用等操作提供明確的錯誤提示。
- 自然排序 (可選): 若安裝 natsort 函式庫，檔案列表將使用自然排序。

## 需求

- Python 3.7+
- PyQt6
- Pillow
- psutil
- numpy

可選:

- pillow-heif (用於支援 HEIC/HEIF 格式)
- natsort (用於檔案列表的自然排序)

## 如何執行

確保已安裝 Python 及上述必要的函式庫。

`pip install PyQt6 Pillow psutil numpy`


(可選) 安裝額外支援：

`pip install pillow-heif natsort`


執行 Python 腳本：

`python image_viewer_full_final.py`


## 檔案結構

整個應用程式包含在單一的 Python 腳本 `image_viewer_full_final.py` 中。

## 貢獻

歡迎提出問題 (Issues) 或合併請求 (Pull Requests) 來改進此應用程式。

## 授權

此專案採用 MIT 授權。詳情請見 `LICENSE` 檔案 (若有的話)。
