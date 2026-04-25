"""報告匯出模組 — 支援 CSV 和 HTML 格式。"""

import csv
import html
from datetime import datetime
from pathlib import Path

from image_viewer.duplicate_checker.core.comparator import DuplicateGroup


class ReportExporter:
    """將重複圖片掃描結果匯出為報告。"""

    @staticmethod
    def export_csv(groups: list[DuplicateGroup], output_path: Path) -> Path:
        """匯出 CSV 格式報告。"""
        output_path = Path(output_path)
        with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow([
                "群組編號", "比對類型", "相似度距離", "檔案名稱",
                "檔案路徑", "檔案大小(bytes)", "圖片寬度", "圖片高度",
            ])
            for group in groups:
                match_label = "精確相同" if group.match_type == "exact" else "視覺相似"
                for img in group.images:
                    w, h = img.dimensions
                    writer.writerow([
                        group.group_id + 1, match_label, group.max_distance,
                        img.filename, str(img.filepath), img.file_size, w, h,
                    ])
        return output_path

    @staticmethod
    def export_html(groups: list[DuplicateGroup], output_path: Path) -> Path:
        """匯出 HTML 格式報告（含縮圖）。"""
        output_path = Path(output_path)
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total_groups = len(groups)
        total_files = sum(g.file_count for g in groups)
        total_saveable = sum(g.saveable_size for g in groups)

        rows_html = ""
        for group in groups:
            match_label = "精確相同" if group.match_type == "exact" else "視覺相似"
            badge_cls = "badge-exact" if group.match_type == "exact" else "badge-similar"
            for i, img in enumerate(group.images):
                w, h = img.dimensions
                file_uri = img.filepath.as_uri()
                best = group.get_best_image()
                is_best = "⭐ 建議保留" if best and img.filepath == best.filepath else ""
                rows_html += f"""<tr>
                    <td>{group.group_id + 1}</td>
                    <td><span class="{badge_cls}">{match_label}</span></td>
                    <td>{group.max_distance}</td>
                    <td><img src="{html.escape(file_uri)}" class="thumb" loading="lazy"></td>
                    <td>{html.escape(img.filename)}</td>
                    <td class="path">{html.escape(str(img.filepath))}</td>
                    <td>{ReportExporter._format_size(img.file_size)}</td>
                    <td>{w} × {h}</td>
                    <td>{is_best}</td>
                </tr>"""

        html_content = f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<title>重複圖片掃描報告</title>
<style>
body {{ font-family: 'Segoe UI', 'Microsoft JhengHei', sans-serif; margin: 20px; background: #1a1a2e; color: #e0e0e0; }}
h1 {{ color: #64ffda; text-align: center; }}
.summary {{ background: #16213e; padding: 15px; border-radius: 8px; margin-bottom: 20px; display: flex; gap: 30px; justify-content: center; }}
.summary .item {{ text-align: center; }}
.summary .value {{ font-size: 24px; font-weight: bold; color: #64ffda; }}
table {{ width: 100%; border-collapse: collapse; background: #0f3460; border-radius: 8px; overflow: hidden; }}
th {{ background: #533483; color: white; padding: 12px 8px; text-align: left; }}
td {{ padding: 8px; border-bottom: 1px solid #1a1a2e; vertical-align: middle; }}
tr:hover {{ background: #16213e; }}
.thumb {{ width: 60px; height: 60px; object-fit: cover; border-radius: 4px; }}
.path {{ font-size: 11px; color: #999; max-width: 300px; word-break: break-all; }}
.badge-exact {{ background: #e94560; color: white; padding: 2px 8px; border-radius: 10px; font-size: 12px; }}
.badge-similar {{ background: #f5a623; color: #1a1a2e; padding: 2px 8px; border-radius: 10px; font-size: 12px; }}
.footer {{ text-align: center; margin-top: 20px; color: #666; font-size: 12px; }}
</style>
</head>
<body>
<h1>🔍 重複圖片掃描報告</h1>
<div class="summary">
  <div class="item"><div class="value">{total_groups}</div><div>重複群組</div></div>
  <div class="item"><div class="value">{total_files}</div><div>重複檔案</div></div>
  <div class="item"><div class="value">{ReportExporter._format_size(total_saveable)}</div><div>可節省空間</div></div>
</div>
<table>
<thead><tr><th>群組</th><th>類型</th><th>距離</th><th>預覽</th><th>檔案名稱</th><th>路徑</th><th>大小</th><th>尺寸</th><th>建議</th></tr></thead>
<tbody>{rows_html}</tbody>
</table>
<div class="footer">產生時間: {now} | 重複圖片檢查工具</div>
</body></html>"""

        output_path.write_text(html_content, encoding="utf-8")
        return output_path

    @staticmethod
    def _format_size(size_bytes: int) -> str:
        for unit in ("B", "KB", "MB", "GB"):
            if size_bytes < 1024:
                return f"{size_bytes:.1f} {unit}"
            size_bytes /= 1024
        return f"{size_bytes:.1f} TB"
