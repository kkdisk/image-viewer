# 增強型圖片瀏覽器 - Rust 重構開發規格書

> **版本**: 1.0  
> **基於**: Python v1.8.0  
> **目標**: 提供完整規格供 RD 或 AI 開發 Rust 版本

---

## 1. 專案概述

### 1.1 產品定義

**增強型圖片瀏覽器** 是一款桌面端圖片瀏覽與編輯工具，主要功能包括：

- 圖片瀏覽與導航
- 基本圖片編輯 (調整尺寸、旋轉、翻轉)
- 進階濾鏡效果 (模糊、銳化、灰階、反轉、懷舊)
- 色彩調整 (亮度、對比、飽和度、白平衡)
- 即時預覽與縮圖導航
- 多步復原功能

### 1.2 技術需求

| 項目 | Python 版本 | Rust 目標 |
|------|-------------|-----------|
| GUI 框架 | PyQt6 | egui / iced / Tauri |
| 圖片處理 | Pillow + NumPy | image + rayon |
| 設定檔 | JSON | TOML / JSON (serde) |
| 跨平台 | Windows/macOS/Linux | 同上 |
| 打包 | PyInstaller | cargo build --release |

---

## 2. 功能規格

### 2.1 圖片載入與顯示

#### 2.1.1 支援格式

```rust
const SUPPORTED_EXTENSIONS: &[&str] = &[
    "jpg", "jpeg", "png", "bmp", "gif", "tiff", "webp", "heic"
];
```

#### 2.1.2 載入流程

```
用戶選擇檔案
    │
    ▼
驗證檔案大小 (< MAX_IMAGE_FILE_SIZE)
    │
    ▼
背景執行緒載入  ──┬── 成功 ──▶ EXIF 旋轉校正 ──▶ 顯示圖片
                  │
                  └── 失敗 ──▶ 顯示錯誤訊息
```

#### 2.1.3 非同步載入

```rust
// 偽代碼
async fn load_image(path: &Path) -> Result<DynamicImage, ImageError> {
    // 1. 檢查檔案大小
    let metadata = fs::metadata(path)?;
    if metadata.len() > MAX_FILE_SIZE { return Err(FileTooLarge); }
    
    // 2. 載入圖片
    let img = image::open(path)?;
    
    // 3. EXIF 旋轉校正
    let oriented = apply_exif_orientation(img)?;
    
    Ok(oriented)
}
```

---

### 2.2 圖片顯示

#### 2.2.1 縮放功能

| 操作 | 行為 |
|------|------|
| 滑鼠滾輪上 | 放大 (scale *= ZOOM_IN_FACTOR) |
| 滑鼠滾輪下 | 縮小 (scale *= ZOOM_OUT_FACTOR) |
| 符合視窗 | 計算最佳縮放比例 |
| 自訂輸入 | 支援百分比輸入 (1% - 1000%) |

```rust
const ZOOM_IN_FACTOR: f32 = 1.25;
const ZOOM_OUT_FACTOR: f32 = 0.8;
const MIN_SCALE: f32 = 0.01;
const MAX_SCALE: f32 = 10.0;
```

#### 2.2.2 平移功能

- 按住滑鼠左鍵拖曳平移
- 支援滑鼠中鍵平移 (可選)

#### 2.2.3 快取機制

```rust
struct PixmapCache {
    cache: LruCache<Scale, Pixmap>,
    max_size: usize, // 動態計算，基於可用記憶體
}

impl PixmapCache {
    fn get_or_compute(&mut self, scale: f32, source: &Image) -> Pixmap {
        let key = Scale(round(scale, 2));
        if let Some(pixmap) = self.cache.get(&key) {
            return pixmap.clone();
        }
        let pixmap = source.resize(scale);
        self.cache.put(key, pixmap.clone());
        pixmap
    }
}
```

---

### 2.3 圖片編輯

#### 2.3.1 基本操作

| 操作 | 說明 | 快捷鍵 |
|------|------|--------|
| 調整尺寸 | 開啟對話框輸入新尺寸 | - |
| 順時針旋轉 | 旋轉 90° | Ctrl+R |
| 逆時針旋轉 | 旋轉 -90° | Ctrl+L |
| 水平翻轉 | 左右鏡像 | H |
| 垂直翻轉 | 上下鏡像 | V |

#### 2.3.2 濾鏡效果

```rust
enum ImageFilter {
    Invert,      // 反轉色彩
    Grayscale,   // 灰階
    Blur,        // 高斯模糊 (radius = 2)
    Sharpen,     // 銳化
    Sepia,       // 懷舊效果
}

impl ImageFilter {
    fn apply(&self, img: &mut DynamicImage) {
        match self {
            Self::Invert => img.invert(),
            Self::Grayscale => *img = img.grayscale(),
            Self::Blur => *img = img.blur(BLUR_RADIUS),
            Self::Sharpen => *img = img.unsharpen(1.0, 1),
            Self::Sepia => apply_sepia(img),
        }
    }
}
```

#### 2.3.3 色彩調整

**亮度/對比/飽和度**

```rust
struct ColorAdjustment {
    brightness: f32, // 0.0 - 2.0, default 1.0
    contrast: f32,   // 0.0 - 2.0, default 1.0
    saturation: f32, // 0.0 - 2.0, default 1.0
}

fn apply_adjustment(img: &mut RgbaImage, adj: &ColorAdjustment) {
    img.par_pixels_mut().for_each(|pixel| {
        // Brightness
        let r = (pixel[0] as f32 * adj.brightness).min(255.0) as u8;
        let g = (pixel[1] as f32 * adj.brightness).min(255.0) as u8;
        let b = (pixel[2] as f32 * adj.brightness).min(255.0) as u8;
        
        // Contrast (around midpoint 128)
        let r = ((r as f32 - 128.0) * adj.contrast + 128.0).clamp(0.0, 255.0) as u8;
        // ... similar for g, b
        
        // Saturation (HSL conversion)
        // ...
        
        *pixel = Rgba([r, g, b, pixel[3]]);
    });
}
```

**白平衡 (色溫/色調)**

```rust
struct WhiteBalance {
    temperature: i32, // -100 to +100
    tint: i32,        // -100 to +100
}

fn apply_white_balance(img: &mut RgbaImage, wb: &WhiteBalance) {
    let temp_factor = wb.temperature as f32 / 100.0;
    let tint_factor = wb.tint as f32 / 100.0;
    
    img.par_pixels_mut().for_each(|pixel| {
        let mut r = pixel[0] as f32;
        let mut g = pixel[1] as f32;
        let mut b = pixel[2] as f32;
        
        // Temperature adjustment
        if temp_factor > 0.0 {
            r *= 1.0 + temp_factor * 0.8;
            b *= 1.0 - temp_factor * 0.5;
        } else {
            r *= 1.0 + temp_factor * 0.5;
            b *= 1.0 - temp_factor * 0.8;
        }
        
        // Tint adjustment
        g *= 1.0 + tint_factor * 0.6;
        r *= 1.0 - tint_factor * 0.1;
        b *= 1.0 - tint_factor * 0.1;
        
        *pixel = Rgba([
            r.clamp(0.0, 255.0) as u8,
            g.clamp(0.0, 255.0) as u8,
            b.clamp(0.0, 255.0) as u8,
            pixel[3]
        ]);
    });
}
```

---

### 2.4 復原功能

#### 2.4.1 規格

- 最大復原步數: `MAX_UNDO_STEPS` (預設 20)
- 每次編輯前自動儲存狀態
- 支援 Ctrl+Z 快捷鍵

```rust
struct UndoStack {
    stack: VecDeque<ImageState>,
    max_size: usize,
}

impl UndoStack {
    fn push(&mut self, state: ImageState) {
        if self.stack.len() >= self.max_size {
            self.stack.pop_front(); // 移除最舊的
        }
        self.stack.push_back(state);
    }
    
    fn pop(&mut self) -> Option<ImageState> {
        self.stack.pop_back()
    }
}
```

#### 2.4.2 記憶體優化建議

考慮使用差異儲存或壓縮：

```rust
// 選項 1: LZ4 壓縮
fn compress_state(img: &RgbaImage) -> Vec<u8> {
    lz4_flex::compress(&img.as_raw())
}

// 選項 2: 差異儲存 (僅儲存變更區域)
struct DiffState {
    region: Rect,
    original_pixels: Vec<u8>,
}
```

---

### 2.5 檔案導航

#### 2.5.1 Filmstrip (縮圖列)

- 顯示同一資料夾內的所有圖片縮圖
- 縮圖大小: 128x128 (可設定)
- 點擊縮圖切換圖片
- 支援上/下一張快捷鍵 (←/→)

```rust
struct Filmstrip {
    thumbnails: HashMap<PathBuf, Thumbnail>,
    current_folder: PathBuf,
    generation: u64, // 用於取消過時的縮圖任務
}

struct Thumbnail {
    pixmap: Pixmap,
    path: PathBuf,
}

// 縮圖生成 (背景執行緒)
fn generate_thumbnail(path: &Path, size: (u32, u32)) -> Result<Pixmap> {
    let img = image::open(path)?;
    
    // 使用 draft mode 加速 (僅 JPEG)
    // img.draft(ColorType::Rgb8, size)?;
    
    // 兩階段縮小提升品質
    let thumb = if img.width() > 1000 || img.height() > 1000 {
        img.thumbnail(500, 500).thumbnail(size.0, size.1)
    } else {
        img.thumbnail(size.0, size.1)
    };
    
    Ok(to_pixmap(&thumb))
}
```

#### 2.5.2 檔案樹

- 顯示目前資料夾結構
- 支援展開/收合子資料夾
- 雙擊檔案開啟

---

### 2.6 放大鏡功能

#### 2.6.1 規格

| 參數 | 預設值 | 範圍 |
|------|--------|------|
| 視窗大小 | 180x180 px | 固定 |
| 放大倍率 | 2.0x | 1.5x - 8.0x |
| 視窗偏移 | 20 px | 游標右下方 |

#### 2.6.2 繪製規格

```rust
struct Magnifier {
    size: u32,
    factor: f32,
    visible: bool,
}

impl Magnifier {
    fn render(&self, cursor_pos: Point, source_image: &Image) -> Pixmap {
        // 1. 計算取樣區域
        let sample_size = self.size as f32 / self.factor;
        let sample_rect = Rect::from_center(
            cursor_pos, 
            sample_size, 
            sample_size
        );
        
        // 2. 裁切並放大
        let cropped = source_image.crop(sample_rect);
        let magnified = cropped.resize(self.size, self.size);
        
        // 3. 套用圓形遮罩
        let circular = apply_circular_mask(&magnified);
        
        // 4. 繪製十字線和邊框
        draw_crosshair(&mut circular);
        draw_border(&mut circular, Color::from_hex("#0078d7"));
        draw_factor_text(&mut circular, self.factor);
        
        circular
    }
}
```

---

### 2.7 直方圖顯示

#### 2.7.1 規格

| 參數 | 值 |
|------|-----|
| 尺寸 | 280 x 150 px |
| 通道 | R, G, B, 亮度 |
| 更新時機 | 圖片載入/編輯後 |

#### 2.7.2 計算

```rust
struct Histogram {
    r: [u32; 256],
    g: [u32; 256],
    b: [u32; 256],
    lum: [u32; 256],
    max_value: u32,
}

impl Histogram {
    fn compute(img: &RgbaImage) -> Self {
        let mut hist = Histogram::default();
        
        // 使用 rayon 並行計算
        let (r, g, b, lum) = img.par_pixels()
            .fold(
                || ([0u32; 256], [0u32; 256], [0u32; 256], [0u32; 256]),
                |mut acc, pixel| {
                    acc.0[pixel[0] as usize] += 1;
                    acc.1[pixel[1] as usize] += 1;
                    acc.2[pixel[2] as usize] += 1;
                    // ITU-R BT.601 亮度
                    let lum = (0.299 * pixel[0] as f32 
                             + 0.587 * pixel[1] as f32 
                             + 0.114 * pixel[2] as f32) as u8;
                    acc.3[lum as usize] += 1;
                    acc
                }
            )
            .reduce(
                || ([0u32; 256], [0u32; 256], [0u32; 256], [0u32; 256]),
                |a, b| {
                    // 合併結果
                    // ...
                }
            );
        
        hist.r = r;
        hist.g = g;
        hist.b = b;
        hist.lum = lum;
        hist.max_value = *[&r[..], &g[..], &b[..], &lum[..]]
            .iter()
            .flat_map(|h| h.iter())
            .max()
            .unwrap_or(&1);
        
        hist
    }
}
```

---

### 2.8 EXIF 資訊顯示

顯示以下欄位 (若存在):

| 欄位 | EXIF Tag |
|------|----------|
| 相機製造商 | Make |
| 相機型號 | Model |
| 拍攝日期 | DateTimeOriginal |
| 曝光時間 | ExposureTime |
| 光圈值 | FNumber |
| ISO | ISOSpeedRatings |
| 焦距 | FocalLength |
| GPS 座標 | GPSLatitude, GPSLongitude |

```rust
fn extract_exif(path: &Path) -> Option<ExifData> {
    let file = std::fs::File::open(path).ok()?;
    let mut bufreader = std::io::BufReader::new(file);
    let exif = exif::Reader::new().read_from_container(&mut bufreader).ok()?;
    
    Some(ExifData {
        make: get_field(&exif, Tag::Make),
        model: get_field(&exif, Tag::Model),
        datetime: get_field(&exif, Tag::DateTimeOriginal),
        // ...
    })
}
```

---

### 2.9 主題系統

#### 2.9.1 支援主題

- **Dark** (預設): 深色背景，護眼
- **Light**: 淺色背景

#### 2.9.2 主題定義

```rust
struct Theme {
    name: &'static str,
    background: Color,
    foreground: Color,
    accent: Color,
    border: Color,
    hover: Color,
    // ...
}

const DARK_THEME: Theme = Theme {
    name: "dark",
    background: Color::from_rgb(30, 30, 30),
    foreground: Color::from_rgb(220, 220, 220),
    accent: Color::from_rgb(0, 120, 215),
    border: Color::from_rgb(60, 60, 60),
    hover: Color::from_rgb(45, 45, 45),
};

const LIGHT_THEME: Theme = Theme {
    name: "light",
    background: Color::from_rgb(240, 240, 240),
    foreground: Color::from_rgb(30, 30, 30),
    accent: Color::from_rgb(0, 120, 215),
    border: Color::from_rgb(200, 200, 200),
    hover: Color::from_rgb(230, 230, 230),
};
```

---

## 3. 設定檔規格

### 3.1 config.toml (建議格式)

```toml
[window]
title = "增強型圖片瀏覽器"
default_size = [1200, 800]
theme = "dark"

[image]
max_file_size = 524288000  # 500 MB
supported_extensions = ["jpg", "jpeg", "png", "bmp", "gif", "tiff", "webp"]

[zoom]
in_factor = 1.25
out_factor = 0.8

[editing]
max_undo_steps = 20
blur_radius = 2.0

[thumbnail]
size = [128, 128]
draft_factor = 2
max_dimension_before_downscale = 1000

[histogram]
width = 280
height = 150

[magnifier]
size = 180
default_factor = 2.0
factor_range = [1.5, 8.0]
window_offset = 20

[memory]
threshold_mb = 800
check_interval_ms = 30000

[adjustment]
range = [0, 200]
default = 100

[white_balance]
temp_range = [-100, 100]
tint_range = [-100, 100]
```

---

## 4. UI 佈局規格

### 4.1 主視窗佈局

```
┌─────────────────────────────────────────────────────────────────┐
│ 選單列 (File | Edit | View | Filter | Help)                      │
├─────────────────────────────────────────────────────────────────┤
│ 工具列 [開啟][儲存][復原] │ [◀ ▶] │ [+][-][符合] │ [🔍放大鏡]   │
├───────────┬─────────────────────────────────────┬───────────────┤
│           │                                     │ 調整面板      │
│ 檔案樹    │                                     │ ├─ 亮度       │
│           │          圖片顯示區                  │ ├─ 對比       │
│           │                                     │ ├─ 飽和度     │
│           │                                     │ └─ 白平衡     │
│           │                                     │               │
│           │                                     │ 直方圖        │
│           │                                     │ ┌───────────┐ │
│           │                                     │ │  R G B L  │ │
│           │                                     │ └───────────┘ │
├───────────┴─────────────────────────────────────┴───────────────┤
│ 縮圖列 (Filmstrip)                                                │
│ [🖼️][🖼️][🖼️][🖼️][🖼️][🖼️][🖼️][🖼️][🖼️][🖼️]                        │
├─────────────────────────────────────────────────────────────────┤
│ 狀態列: 檔名 | 尺寸 | 縮放比例 | 記憶體使用量                     │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 快捷鍵列表

| 快捷鍵 | 功能 |
|--------|------|
| Ctrl+O | 開啟檔案 |
| Ctrl+S | 儲存 |
| Ctrl+Shift+S | 另存新檔 |
| Ctrl+Z | 復原 |
| Ctrl+M | 切換放大鏡 |
| Ctrl+T | 切換主題 |
| Ctrl+R | 順時針旋轉 |
| Ctrl+L | 逆時針旋轉 |
| H | 水平翻轉 |
| V | 垂直翻轉 |
| ← | 上一張 |
| → | 下一張 |
| Ctrl++ | 放大 |
| Ctrl+- | 縮小 |
| Ctrl+0 | 符合視窗 |
| Delete | 刪除圖片 (可選) |

---

## 5. 建議 Rust Crates

| 功能 | Crate | 說明 |
|------|-------|------|
| GUI | `egui` / `iced` / `tauri` | 選一 |
| 圖片處理 | `image` | 核心 |
| EXIF | `exif` / `kamadak-exif` | |
| 並行運算 | `rayon` | 必須 |
| 設定檔 | `toml` + `serde` | |
| LRU 快取 | `lru` | |
| 日誌 | `tracing` / `log` | |
| 錯誤處理 | `anyhow` / `thiserror` | |
| 壓縮 | `lz4_flex` | 可選 (復原堆疊) |
| HEIC 支援 | `libheif-rs` | 可選 |

---

## 6. 驗收測試案例

### 6.1 基本功能

- [ ] 可開啟 JPG, PNG, BMP, GIF, TIFF, WEBP
- [ ] 可顯示大圖 (4K+) 不卡頓
- [ ] 縮放 1% - 1000% 正常
- [ ] 拖曳平移順暢
- [ ] 上下張切換正常

### 6.2 編輯功能

- [ ] 調整尺寸 (維持/不維持比例)
- [ ] 旋轉 90°/-90°
- [ ] 翻轉 水平/垂直
- [ ] 5 種濾鏡效果正確
- [ ] 亮度/對比/飽和度滑桿
- [ ] 白平衡色溫/色調滑桿
- [ ] 多步復原正常

### 6.3 效能

- [ ] 4K 圖片載入 < 200ms
- [ ] 縮圖生成 < 50ms
- [ ] 濾鏡效果 < 100ms
- [ ] 記憶體用量 < 200MB (單圖)

---

*本規格書可供 Rust 開發者或 AI 直接參考實作*
