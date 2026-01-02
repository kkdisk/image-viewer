# Python 優化完成報告

> **版本**: v1.8.0  
> **完成日期**: 2026-01-03  
> **目的**: 記錄已完成的優化項目，為未來 Rust 重構提供參考

---

## 已完成優化項目

### Phase 0: 程式碼模組化 ✅

將 1872 行的單一檔案拆分為模組化結構：

```
image_viewer/
├── __init__.py          # 套件初始化，導出主要類別
├── main.py              # 應用程式入口點
├── config.py            # Config 類別 + 全域常數
├── core/
│   ├── editor_window.py # ImageEditorWindow 主視窗 (965 行)
│   ├── workers.py       # EffectWorker, ThumbnailWorker, AsyncImageLoader
│   └── resource_manager.py
├── ui/
│   ├── widgets.py       # HistogramWidget, MagnifierWindow, ResizeDialog
│   ├── ui_manager.py    # UIManager (UI 建構)
│   └── theme_manager.py # ThemeManager (主題管理)
└── utils/
    └── decorators.py    # @requires_image 裝飾器
```

**Rust 重構提示**: 這個結構可直接映射到 Rust 的 module 系統。

---

### Phase 1: 高優先級優化 ✅

#### 1.1 執行緒安全修復

**問題**: `EffectWorker._stop_requested` 是類別變數，可能造成競爭條件

**解決方案**:
```python
# 修改前 (類別變數)
class EffectWorker(QObject):
    _stop_requested = False  # 危險！

# 修改後 (實例變數)
class EffectWorker(QObject):
    def __init__(self):
        super().__init__()
        self._stop_requested = False  # 安全
```

**Rust 重構提示**: Rust 的 `AtomicBool` 或 `Arc<Mutex<bool>>` 可提供更強的執行緒安全保證。

---

#### 1.2 LRU 快取優化

**問題**: 使用 `list` 做 LRU 追蹤，`remove()` 是 O(n) 操作

**解決方案**:
```python
# 修改前
self._cached_pixmaps: Dict[float, QPixmap] = {}
self._cache_access_order: List[float] = []

# 修改後
from collections import OrderedDict
self._cached_pixmaps: OrderedDict[float, QPixmap] = OrderedDict()
# move_to_end() 是 O(1) 操作
```

**Rust 重構提示**: 使用 `lru` crate 或 `linked_hash_map` 實現。

---

#### 1.3 縮圖生成優化

**問題**: 多餘的圖片模式轉換

**解決方案**:
```python
# 修改前
if img.mode not in ('RGB', 'RGBA'):
    img = img.convert('RGB')
final_img = img.convert("RGBA")  # 重複轉換！

# 修改後
if img.mode != 'RGBA':
    final_img = img.convert("RGBA")
else:
    final_img = img
```

**Rust 重構提示**: `image` crate 的 `DynamicImage::into_rgba8()` 可高效處理。

---

### Phase 2: 中優先級優化 ✅

#### 2.1 Magic Numbers 提取

已將硬編碼數值移至 `Config` 類別：

```python
DEFAULT_CONFIG = {
    # 新增的常數
    "THUMBNAIL_DRAFT_FACTOR": 2,
    "THUMBNAIL_MAX_DIMENSION_BEFORE_DOWNSCALE": 1000,
    "THUMBNAIL_INTERMEDIATE_SIZE": (500, 500),
    "CACHE_STATS_LOG_INTERVAL": 50,
    "MAGNIFIER_WINDOW_OFFSET": 20,
}
```

**Rust 重構提示**: 使用 `config` 或 `toml` crate 載入設定。

---

#### 2.2 __init__.py 修復

修正了模組化後的導入問題：

```python
from .config import Config, HEIC_SUPPORTED, NATSORT_ENABLED
from .core.editor_window import ImageEditorWindow
from .main import main
```

---

### Phase 3: 低優先級優化 ✅ (部分)

#### 3.1 NumPy 直方圖優化

**問題**: PIL `histogram()` 對大圖較慢

**解決方案**: 使用 NumPy 計算直方圖

```python
import numpy as np

img_array = np.array(img_for_hist)
r_hist, _ = np.histogram(img_array[:,:,0].flatten(), bins=256, range=(0, 256))
g_hist, _ = np.histogram(img_array[:,:,1].flatten(), bins=256, range=(0, 256))
b_hist, _ = np.histogram(img_array[:,:,2].flatten(), bins=256, range=(0, 256))

# 亮度使用 ITU-R BT.601 標準
lum_array = (0.299 * img_array[:,:,0] + 0.587 * img_array[:,:,1] + 0.114 * img_array[:,:,2]).astype(np.uint8)
```

**Rust 重構提示**: 使用 `rayon` 並行計算，效能可再提升 5-10x。

---

#### 3.2 白平衡向量化

**狀態**: 已經使用 NumPy 向量化

```python
def white_balance_func(img: Image.Image) -> Image.Image:
    img_np = np.array(img_rgb, dtype=np.float32) / 255.0
    r, g, b = img_np[:, :, 0], img_np[:, :, 1], img_np[:, :, 2]
    # 向量化運算
    r *= 1.0 + temp_factor * 0.8
    b *= 1.0 - temp_factor * 0.5
    # ...
    img_np = np.clip(np.stack([r, g, b], axis=-1), 0.0, 1.0) * 255.0
```

**Rust 重構提示**: 使用 SIMD (`packed_simd` 或 `wide` crate) 可進一步加速。

---

## 未完成項目 (可選)

| 項目 | 優先級 | 說明 |
|------|--------|------|
| 完整型別標註 | 中 | 持續性工作，已有基礎 |
| 壓縮復原堆疊 | 低 | 需權衡 pickle+zlib 開銷 vs 記憶體節省 |
| Rust 核心模組 | 長期 | 見 `RUST_SPECIFICATION.md` |

---

## 效能基準 (待未來 Rust 版本對比)

| 操作 | Python v1.8.0 (預估) | 目標 Rust 效能 |
|------|----------------------|----------------|
| 圖片載入 (4K) | ~150ms | ~50ms |
| 白平衡運算 | ~80ms | ~10ms |
| 縮圖生成 | ~30ms | ~8ms |
| 直方圖計算 | ~20ms | ~3ms |
| 記憶體佔用 | ~150MB | ~80MB |

---

## Git 提交歷史

```
v1.8.0  - 2026-01-03 - release: Complete Modular Architecture
        - chore: remove legacy flat structure files
        - perf: Phase 2-3 optimizations - NumPy histogram & fix imports
```

---

*此報告供 Rust 重構時參考，請搭配 `RUST_SPECIFICATION.md` 開發規格書使用*
