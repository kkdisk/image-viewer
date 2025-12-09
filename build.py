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
# [v1.7] 支援兩種打包模式：模組化版本或單檔案版本
USE_MODULE_VERSION = True  # True = 使用 image_viewer/ 套件, False = 使用單檔案

if USE_MODULE_VERSION:
    SCRIPT_NAME = "image_viewer/main.py"
else:
    SCRIPT_NAME = "image_viewer_full_final.py"

ICON_NAME = "app_icon.ico"
# [新增] 需要一起打包的資料檔案
DATA_FILES = [
    "config.json",
    "dark_theme.qss"
]

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

    # [新增] 準備 --add-data 參數
    add_data_args = []
    for file_name in DATA_FILES:
        if not os.path.exists(file_name):
            print(f"警告：找不到必要的資料檔案 '{file_name}'。打包可能會失敗或執行時出錯。")
        else:
            # Windows 使用 ';' 作為分隔符，Mac/Linux 使用 ':'
            # 我們將檔案打包到 .exe 的根目錄 ('.')
            separator = ';' if os.name == 'nt' else ':'
            add_data_args.extend(['--add-data', f"{file_name}{separator}."])

    # PyInstaller 指令參數
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
        # 插入在 --windowed 之後
        pyinstaller_args.insert(4, icon_option)

    # [修改] 將 --add-data 參數加入指令中
    # 插入在 icon 之後 (或 --windowed 之後)
    pyinstaller_args[4:4] = add_data_args

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
