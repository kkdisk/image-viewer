import os
import sys
import shutil
from pathlib import Path
from datetime import datetime

try:
    import PyInstaller.__main__
except ImportError:
    print("錯誤：找不到 PyInstaller 模組。")
    print("請先使用 'pip install pyinstaller' 進行安裝。")
    sys.exit(1)

# --- 設定 ---
APP_NAME = "ImageViewer"
SCRIPT_NAME = "image_viewer_full_final.py"
ICON_NAME = "app_icon.ico"

# --- 腳本執行 ---
def main():
    """執行 PyInstaller 來打包應用程式。"""
    # 檢查主腳本是否存在
    if not os.path.exists(SCRIPT_NAME):
        print(f"錯誤：找不到主腳本 '{SCRIPT_NAME}'。請將此腳本放置在與主程式相同的目錄中。")
        sys.exit(1)

    # 檢查圖示是否存在，若不存在則提供提示
    if not os.path.exists(ICON_NAME):
        print(f"提示：找不到圖示檔案 '{ICON_NAME}'。將使用預設圖示。")
        icon_option = ""
    else:
        icon_option = f"--icon={ICON_NAME}"

    # PyInstaller 指令參數
    # --onefile: 打包成單一執行檔
    # --windowed: 執行時不顯示主控台視窗
    # --name: 指定輸出檔案的名稱
    # --hidden-import: 手動加入 PyInstaller 可能無法自動偵測的套件
    pyinstaller_args = [
        '--name', APP_NAME,
        '--onefile',
        '--windowed',
        '--clean',
        '--hidden-import', 'pillow_heif',
        '--hidden-import', 'natsort',
        SCRIPT_NAME
    ]
    
    if icon_option:
        pyinstaller_args.insert(4, icon_option)

    print("="*60)
    print(f"開始打包應用程式: {APP_NAME}")
    print(f"主腳本: {SCRIPT_NAME}")
    print(f"打包指令: pyinstaller {' '.join(pyinstaller_args)}")
    print("="*60)

    # 執行 PyInstaller
    PyInstaller.__main__.run(pyinstaller_args)

    print("\n" + "="*60)
    print("打包完成！")
    
    # 顯示最終檔案的路徑
    dist_path = Path("dist") / f"{APP_NAME}.exe"
    if dist_path.exists():
        print(f"您可以在以下路徑找到執行檔：")
        print(os.path.abspath(dist_path))
    else:
        print("錯誤：打包似乎失敗了，在 'dist' 目錄中找不到執行檔。")

    # 清理臨時檔案
    try:
        if os.path.exists(f"{APP_NAME}.spec"):
            os.remove(f"{APP_NAME}.spec")
        if os.path.exists("build"):
            shutil.rmtree("build")
        print("\n已清理臨時檔案 (.spec, build/)。")
    except Exception as e:
        print(f"清理臨時檔案時發生錯誤: {e}")
        
    print("="*60)


if __name__ == '__main__':
    main()

        
