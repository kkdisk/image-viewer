"""通用工具函式。"""

def format_size(size_bytes: int) -> str:
    """將位元組數值轉換為易讀的格式 (B, KB, MB, GB, TB)。"""
    if size_bytes == 0:
        return "0 B"
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"
