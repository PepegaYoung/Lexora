$ErrorActionPreference='Stop'
Set-Location -LiteralPath $PSScriptRoot
if (!(Test-Path -LiteralPath 'dist/Lexora/Lexora.exe')) { & './build.ps1' }
& '.venv/Scripts/python.exe' build_installer_payload.py 'dist/Lexora' 'build/installer/payload.zip'
if ($LASTEXITCODE -ne 0) { throw 'Installer payload failed' }
& '.venv/Scripts/python.exe' -m PyInstaller --noconfirm Installer.spec
if ($LASTEXITCODE -ne 0) { throw 'Installer build failed' }
Write-Host 'Built: dist/Lexora-0.6.2-Setup.exe'
