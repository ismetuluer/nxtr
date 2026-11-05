@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem SD kart denetimi: modun Atemphere'in aradigi yerde olup olmadigini soyler.
rem Hicbir dosyayi degistirmez. Once "NX Ceviri Studyosu.bat" bir kez calismis olmali.

if not exist ".venv\Scripts\python.exe" (
    echo HATA: Once "NX Ceviri Studyosu.bat" dosyasini bir kez calistirin.
    echo ^(gerekli Python paketleri kurulsun^)
    pause
    exit /b 1
)

set "PYTHONIOENCODING=utf-8"
".venv\Scripts\python.exe" sd_kontrol.py %*
echo.
pause
endlocal
