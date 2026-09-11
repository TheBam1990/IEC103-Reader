# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=["serial.tools.list_ports_windows"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    [], name="IEC103-Reader", debug=False,
    bootloader_ignore_signals=False, strip=False, upx=True,
    console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None,
    codesign_identity=None, entitlements_file=None,
)
