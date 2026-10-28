from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_submodules,collect_data_files

python_lib = Path(sys.base_prefix) / 'Lib'
rejected_ca = python_lib / 'codex-rejected-cas.pem'
ssl_source = python_lib / 'ssl.py'
if ssl_source.is_file() and 'codex-rejected-cas.pem' in ssl_source.read_text(encoding='utf-8') and not rejected_ca.is_file():
    raise RuntimeError('The Python runtime requires its rejected-CA file, but it is missing')
ssl_data = [(str(rejected_ca), '.')] if rejected_ca.is_file() else []
a = Analysis(['main.py'],pathex=[],binaries=[],datas=collect_data_files('windowwords._vendor.rapidocr') + ssl_data,
    hiddenimports=collect_submodules('winrt'),hookspath=[],hooksconfig={},
    runtime_hooks=[],excludes=[],noarchive=False,optimize=0)

# Keep the Qt modules used by this QWidget app. The virtual keyboard / QML /
# PDF / SVG plug-ins are not used and must not pull unrelated modules into it.
qt_allowed = {'qt6core.dll','qt6gui.dll','qt6widgets.dll','qt6network.dll','qt6opengl.dll'}
def used(item):
    name = item[0].replace('\\','/').lower()
    filename = name.rsplit('/',1)[-1]
    # Qt uses the Windows ICU API. A same-named Poppler DLL on a developer's
    # PATH has incompatible exports and must never be bundled instead.
    if filename in {'icuuc.dll','icuin.dll'} or filename.startswith('icudt'):
        return False
    if filename.startswith('qt6') and filename.endswith('.dll'):
        return filename in qt_allowed
    if '/pyside6/plugins/platforminputcontexts/' in '/'+name:
        return False
    if '/pyside6/plugins/imageformats/' in '/'+name:
        return filename in {'qgif.dll','qico.dll','qjpeg.dll'}
    if '/pyside6/qml/' in '/'+name:
        return False
    return True
a.binaries = [item for item in a.binaries if used(item)]
a.datas = [item for item in a.datas if used(item)]
# WinRT ships an older MSVC runtime. Use Qt's compatible newer redistributable
# consistently instead of allowing DLL search order to choose the old copy.
qt_runtime = Path(__import__('PySide6').__file__).parent
fixed = []
for destination,source,kind in a.binaries:
    filename = Path(source).name.lower()
    # Other software on PATH may contain same-named OpenSSL DLLs. Python's
    # _ssl.pyd must use the pair shipped with this exact Python runtime.
    python_dlls = Path(sys.base_prefix) / 'DLLs'
    if filename in {'libcrypto-3-x64.dll', 'libssl-3-x64.dll'}:
        compatible = python_dlls / filename
        if not compatible.is_file():
            raise RuntimeError(f'Missing Python OpenSSL runtime: {compatible}')
        source = str(compatible)
    if filename.startswith(('msvcp140','vcruntime140')) and (qt_runtime/filename).is_file():
        source = str(qt_runtime/filename)
    fixed.append((destination,source,kind))
a.binaries = fixed

pyz = PYZ(a.pure)
exe = EXE(pyz,a.scripts,[],exclude_binaries=True,name='Lexora',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=False,icon='assets/logo.ico',uac_admin=False)
coll = COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='Lexora')
