$ErrorActionPreference = 'Stop'
Set-Location -LiteralPath $PSScriptRoot
$compiler = 'C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe'
& $compiler /nologo /optimize+ /platform:x64 /target:exe '/out:assets\MouseHook.exe' 'scripts\MouseHook.cs'
if ($LASTEXITCODE -ne 0) { throw 'Mouse shortcut helper build failed' }
$env:PYTHONUTF8 = '1'
python -m venv .venv
if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed' }
& '.venv\Scripts\python.exe' -m pip install -r requirements.txt 'pyinstaller==6.22.3'
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed' }
& '.venv\Scripts\python.exe' scripts/prepare_data.py
if ($LASTEXITCODE -ne 0) { throw 'Dictionary preparation failed' }
& '.venv\Scripts\python.exe' -m PyInstaller --noconfirm --clean Lexora.spec
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
& '.venv\Scripts\python.exe' -c "import shutil; shutil.copytree('data', 'dist/Lexora/data', dirs_exist_ok=True, ignore=shutil.ignore_patterns('bundled-dictionaries.zip','manifest.json')); [shutil.copytree(name, 'dist/Lexora/' + name, dirs_exist_ok=True) for name in ('assets','licenses','docs')]"
if ($LASTEXITCODE -ne 0) { throw 'Artifact copy failed' }
Copy-Item -LiteralPath README.md,LICENSE,THIRD_PARTY.md,CHANGELOG.md,SECURITY.md -Destination 'dist\Lexora' -Force
Write-Host 'Built: dist\Lexora\Lexora.exe'
