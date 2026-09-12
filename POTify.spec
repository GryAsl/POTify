# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for POTify desktop distribution."""

import os
from PyInstaller.config import CONF
from PyInstaller.utils.hooks import (
    collect_data_files,
    collect_dynamic_libs,
    collect_submodules,
)

# Default distribution directory to 'release' if not overridden
if not CONF.get('distpath') or CONF['distpath'] == os.path.join(SPECPATH, 'dist'):
    CONF['distpath'] = os.path.join(SPECPATH, 'release')

block_cipher = None

# Collect package data and dependencies
datas = [
    (os.path.join(SPECPATH, 'assets'), 'assets'),
]
datas += collect_data_files('customtkinter')
datas += collect_data_files('tkinterdnd2')

# Collect fixed datas and binaries
binaries = []
binaries += collect_dynamic_libs('tkinterdnd2')

hiddenimports = [
    'potify',
    'potify.assets',
    'potify.config',
    'potify.constants',
    'potify.converter',
    'potify.gui',
    'potify.image_utils',
    'potify.models',
    'PIL',
    'PIL.Image',
    'PIL.ImageDraw',
]
hiddenimports += collect_submodules('customtkinter')
hiddenimports += collect_submodules('tkinterdnd2')

a = Analysis(
    [os.path.join(SPECPATH, 'main.py')],
    pathex=[SPECPATH],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', '_pytest', 'unittest', 'test'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(
    a.pure,
    a.zipped_data,
    cipher=block_cipher,
)

icon_path = os.path.join(SPECPATH, 'assets', 'icon.ico')
version_file = os.path.join(SPECPATH, 'version_info.txt')

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='POTify',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path if os.path.exists(icon_path) else None,
    version=version_file if os.path.exists(version_file) else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='POTify',
)
