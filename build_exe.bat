@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

REM ===== USER CONFIG: conda env dir (must contain python.exe) =====
set "CONDA_ENV=D:\anaconda3\envs\qtUI"
REM ================================================================

set "PY_EXE=%CONDA_ENV%\python.exe"

echo === ViewImage build (onedir) ===

if not exist "%PY_EXE%" (
  echo [ERROR] Python not found: %PY_EXE%
  echo [ERROR] Edit CONDA_ENV at the top of this file, then run again.
  echo [ERROR] Expected python.exe inside: %CONDA_ENV%
  goto :fail
)

"%PY_EXE%" -c "import sys;print('[INFO] Using:',sys.executable)"
if errorlevel 1 (
  echo [ERROR] Python not runnable. Check CONDA_ENV at the top of this file.
  goto :fail
)

set "QT_BINDING="
"%PY_EXE%" -c "import PyQt5" >nul 2>&1
if not errorlevel 1 goto :qt_pyqt5
"%PY_EXE%" -c "import PySide6" >nul 2>&1
if not errorlevel 1 goto :qt_pyside6
"%PY_EXE%" -c "import PyQt6" >nul 2>&1
if not errorlevel 1 goto :qt_pyqt6
echo [ERROR] No Qt binding importable in this interpreter.
echo [ERROR] Install one of: PyQt5 / PySide6 / PyQt6
echo [ERROR] Example: "%PY_EXE%" -m pip install -r requirements.txt
goto :fail

:qt_pyqt5
set "QT_BINDING=PyQt5"
goto :qt_detected
:qt_pyside6
set "QT_BINDING=PySide6"
goto :qt_detected
:qt_pyqt6
set "QT_BINDING=PyQt6"
goto :qt_detected
:qt_detected
echo [INFO] Qt binding: %QT_BINDING%

"%PY_EXE%" -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
  echo [ERROR] PyInstaller not installed in this interpreter.
  echo [ERROR] Run: "%PY_EXE%" -m pip install pyinstaller
  goto :fail
)

echo [1/3] Building...
"%PY_EXE%" -m PyInstaller --noconfirm --clean --windowed --onedir --name ViewImage --paths "." --icon "image\ViewImage.ico" --hidden-import PyQt5.sip --distpath "dist" --workpath "build" --specpath . dual_image_viewer.py
if errorlevel 1 (
  echo [ERROR] PyInstaller failed. See output above.
  goto :fail
)

echo [2/3] Copying viewer_config.json...
set "OUTDIR=%~dp0dist\ViewImage"
if not exist "%OUTDIR%\_internal" (
  echo [WARN] _internal not found. Check dist layout manually.
  goto :done
)
copy /Y "%~dp0viewer_config.json" "%OUTDIR%\_internal\viewer_config.json" >nul
copy /Y "%~dp0viewer_config.json" "%OUTDIR%\viewer_config.json" >nul

echo [3/3] Done.
:done
echo Output: %OUTDIR%\ViewImage.exe
echo NOTE: config location after packaging is INFERRED, not tested. Verify save/load once.
echo NOTE: change --windowed to --console if you need runtime errors.
pause
exit /b 0

:fail
pause
exit /b 1
