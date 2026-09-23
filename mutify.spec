# -*- mode: python ; coding: utf-8 -*-
"""Сборка Mutify в исполняемый файл.

    pyinstaller mutify.spec --noconfirm

Результат: dist/Mutify/Mutify.exe. Рядом с .exe лежат папки data, assets и
models — их видно пользователю, туда же кладётся скачанная модель.
"""
from PyInstaller.utils.hooks import collect_all, collect_data_files, collect_dynamic_libs

# Нативные библиотеки, которые PyInstaller сам не находит.
binaries = []
binaries += collect_dynamic_libs("vosk")          # libvosk.dll
binaries += collect_dynamic_libs("sounddevice")   # portaudio
binaries += collect_dynamic_libs("soundfile")     # libsndfile

datas = []
datas += collect_data_files("vosk")
datas += collect_data_files("sounddevice")
datas += collect_data_files("soundfile")
datas += [("assets/icon.png", "assets"), ("assets/icon.ico", "assets")]

# faster-whisper: сама библиотека, её движок ctranslate2 и декодер av.
# Библиотеки CUDA (cuBLAS, cuDNN) сюда не входят — tools/build.py кладёт их
# рядом с программой в папку cuda, иначе они раздули бы архив сборки.
hiddenimports_whisper = []
for package in ("faster_whisper", "ctranslate2", "tokenizers", "av"):
    try:
        pkg_datas, pkg_binaries, pkg_hidden = collect_all(package)
    except Exception:
        continue
    datas += pkg_datas
    binaries += pkg_binaries
    hiddenimports_whisper += pkg_hidden

# Тяжёлые части Qt, которые приложению не нужны: без них сборка меньше втрое.
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQml", "PySide6.Qt3DCore",
    "PySide6.Qt3DRender", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtPositioning", "PySide6.QtLocation", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtDesigner", "PySide6.QtHelp",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSpatialAudio",
    "PySide6.QtNetworkAuth", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtStateMachine", "PySide6.QtTextToSpeech", "PySide6.QtWebChannel",
    "PySide6.QtWebSockets", "PySide6.QtUiTools",
    "matplotlib", "scipy", "pandas", "PIL", "tkinter", "pytest", "IPython",
]

a = Analysis(
    ["main.py"],
    pathex=[],
    binaries=binaries,
    datas=datas,
    # QtMultimedia нужен, чтобы читать mp3, m4a и звук из видео системными
    # кодеками Windows, когда libsndfile такой файл не осилил.
    hiddenimports=["vosk", "sounddevice", "soundfile", "numpy",
                   "PySide6.QtMultimedia", "huggingface_hub"] + hiddenimports_whisper,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Mutify",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # без чёрного окна консоли
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.ico",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Mutify",
)
