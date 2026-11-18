# Build dist\ContineoAutoLogin.exe
# Run from the project folder with the venv active:  .\build.ps1
# Note: PyInstaller logs to stderr, so don't use $ErrorActionPreference="Stop"
# (PowerShell 5.1 would abort on the first log line). Check the exit code instead.
pyinstaller main.py `
    --name ContineoAutoLogin `
    --onefile `
    --windowed `
    --noconfirm `
    --clean `
    --collect-data customtkinter `
    --collect-all playwright `
    --hidden-import keyring.backends.Windows `
    --hidden-import win32ctypes.core

if ($LASTEXITCODE -ne 0) { Write-Host "`nBuild FAILED (exit $LASTEXITCODE)"; exit $LASTEXITCODE }
Write-Host "`nBuilt: dist\ContineoAutoLogin.exe"
