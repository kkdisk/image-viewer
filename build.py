import os
import sys
import shutil
import importlib.util
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
# [修改] 更新為模組化後的進入點
SCRIPT_NAME = "run.py" 
ICON_NAME = "app_icon.ico"
# [新增] 需要一起打包的資料檔案
DATA_FILES = [
    "config.json",
    "dark_theme.qss"
]


def _find_zstd_pyd():
    """找到 backports.zstd._zstd 的 .pyd (C extension) 檔案路徑。"""
    try:
        spec = importlib.util.find_spec('backports.zstd._zstd')
        if spec and spec.origin and spec.origin.endswith('.pyd'):
            return spec.origin
    except (ModuleNotFoundError, ValueError):
        pass

    # Fallback: 直接在 site-packages 中搜尋
    import sysconfig
    site_packages = sysconfig.get_path('purelib')
    if site_packages:
        zstd_dir = Path(site_packages) / 'backports' / 'zstd'
        for pyd_file in zstd_dir.glob('_zstd*.pyd'):
            return str(pyd_file)
    return None


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

    # [修正] 找到 backports.zstd._zstd 的 .pyd 檔案
    zstd_pyd_path = _find_zstd_pyd()
    add_binary_args = []
    if zstd_pyd_path:
        separator = ';' if os.name == 'nt' else ':'
        print(f"找到 backports.zstd._zstd C extension: {zstd_pyd_path}")
        add_binary_args.extend(['--add-binary', f"{zstd_pyd_path}{separator}backports/zstd/"])
    else:
        print("警告：找不到 backports.zstd._zstd .pyd 檔案，將依賴 CFFI fallback。")
    # PyInstaller 指令參數
    pyinstaller_args = [
        '--name', APP_NAME,
        '--onefile',
        '--windowed',
        '--clean',
        '--hidden-import', 'pillow_heif',
        '--hidden-import', 'natsort',
        # [修復] 加入 py7zr 打包所需的隱藏導入項與收集項目
        '--hidden-import', 'py7zr',
        '--collect-all', 'py7zr',
        '--collect-submodules', 'backports',
        '--collect-all', 'backports.zstd',
        '--collect-submodules', 'backports.zstd._cffi',
        '--collect-all', 'pyzstd',
        '--copy-metadata', 'backports.zstd',
        '--hidden-import', 'Cryptodome',
        '--hidden-import', 'pybcj',
        '--hidden-import', 'multivolumefile',
        '--hidden-import', 'inflate64',
        '--hidden-import', 'pyppmd',
        '--hidden-import', 'texttable',
        SCRIPT_NAME
    ]


    
    if icon_option:
        # 插入在 --windowed 之後
        pyinstaller_args.insert(4, icon_option)

    # [修改] 將 --add-data 與 --add-binary 參數加入指令中
    # 插入在 icon 之後 (或 --windowed 之後)
    pyinstaller_args[4:4] = add_data_args + add_binary_args

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
