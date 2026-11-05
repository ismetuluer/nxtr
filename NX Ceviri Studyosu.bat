@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

rem NX Ceviri Studyosu baslatici.
rem Ilk calistirmada sanal ortami (.venv) kurar. Bagimliliklar degismisse (pyproject.toml
rem guncellendiyse) paketleri yeniden kurar. Sonra uygulamayi konsolsuz acar.

if not exist ".venv\Scripts\python.exe" (
    echo Ilk kurulum yapiliyor, bu bir kac dakika surebilir...
    set "PYVER="
    for %%V in (3.13 3.12 3.14) do (
        if not defined PYVER (
            py -%%V -c "import sys" >nul 2>&1 && set "PYVER=%%V"
        )
    )
    if not defined PYVER (
        echo.
        echo HATA: Uygun Python bulunamadi. https://www.python.org adresinden Python 3.13 kurun
        echo ^(kurulumda "py launcher" secili olsun^) ve tekrar deneyin.
        pause
        exit /b 1
    )
    call py -%%PYVER%% -m venv .venv
    if errorlevel 1 (
        echo HATA: Sanal ortam olusturulamadi.
        pause
        exit /b 1
    )
)

rem Bagimliliklar: pyproject.toml son kurulumdakiyle ayni degilse yeniden kur.
fc /b "pyproject.toml" ".venv\kurulu_pyproject.toml" >nul 2>&1
if errorlevel 1 (
    echo Gerekli paketler kuruluyor veya guncelleniyor...
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -e .
    if errorlevel 1 (
        echo.
        echo HATA: Gerekli paketler kurulamadi. Internet baglantinizi kontrol edip tekrar deneyin.
        pause
        exit /b 1
    )
    copy /y "pyproject.toml" ".venv\kurulu_pyproject.toml" >nul
)

start "" ".venv\Scripts\pythonw.exe" -m nxceviri %*
endlocal
