a = Analysis(['installer.py'],pathex=[],binaries=[],datas=[('build/installer/payload.zip','.')],
    hiddenimports=[],hookspath=[],hooksconfig={},runtime_hooks=[],excludes=[],noarchive=False,optimize=0)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,a.binaries,a.datas,[],name='Lexora-0.6.34-Setup',debug=False,
    bootloader_ignore_signals=False,strip=False,upx=False,console=False,icon='assets/logo.ico',uac_admin=False)
