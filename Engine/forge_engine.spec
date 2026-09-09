# PyInstaller onedir spec for FORGE's offline Windows engine.
# onedir is intentionally used instead of onefile: startup is much faster when
# the VST3 launches the engine repeatedly during editing/stack iteration.
from PyInstaller.utils.hooks import collect_all

packages = [
    'numpy', 'scipy', 'pandas', 'soundfile', 'librosa',
    'parselmouth', 'numba', 'llvmlite', 'sklearn', 'audioread',
]

datas, binaries, hiddenimports = [], [], []
for package in packages:
    try:
        d, b, h = collect_all(package)
        datas += d
        binaries += b
        hiddenimports += h
    except Exception:
        pass

a = Analysis(
    ['forge_engine.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['matplotlib', 'IPython', 'jupyter', 'pytest', 'tkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='forge_engine',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name='forge_engine',
)
