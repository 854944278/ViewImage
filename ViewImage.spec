# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.compat import is_win
from PyInstaller.utils.hooks import conda_support

# Conda 的 _ctypes 依赖 Library/bin 下的 libffi，需要显式收集到发布目录。
conda_binaries = []
if is_win and conda_support is not None:
    conda_binaries = conda_support.collect_dynamic_libs('libffi', dependencies=False)

a = Analysis(
    ['dual_image_viewer.py'],
    pathex=['.'],
    binaries=conda_binaries,
    # 运行时图标与 EXE 图标分别配置，确保打包后仍能读取图标文件。
    datas=[('image/ViewImage.ico', 'image')],
    hiddenimports=['PyQt5.sip'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ViewImage',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['image/ViewImage.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ViewImage',
)
