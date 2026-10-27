@echo off
rem ============================================================
rem  ConsoleReader - one-click launcher
rem  Starts the local web server (from this folder) and opens
rem  the app page in Google Chrome.
rem  Close the minimized "ConsoleReader server" window to stop it.
rem ============================================================
setlocal EnableExtensions
title ConsoleReader launcher
cd /d "%~dp0"

set "PORT=8000"
set "URL=http://localhost:%PORT%/app/"

rem ---------- 0) sanity check: right folder? -------------------
if not exist "app\index.html" (
  echo.
  echo [X] app\index.html was not found next to this file.
  echo     Put this launcher in the project root, beside the "app" folder.
  echo     Current folder: %CD%
  echo.
  pause
  exit /b 1
)

rem ---------- 1) locate Python --------------------------------
set "PY="
python --version >nul 2>nul && set "PY=python"
if not defined PY (py -3 --version >nul 2>nul && set "PY=py -3")
if not defined PY goto nopython

rem ---------- 2) server already running? ----------------------
netstat -ano | findstr /C:":%PORT% " | findstr /C:"LISTENING" >nul
if not errorlevel 1 (
  echo [i] The server is already running on port %PORT%.
  goto open
)

rem ---------- 3) start the server -----------------------------
echo [i] Starting the local server on port %PORT% ...
start "ConsoleReader server - close this window to stop" /min /d "%~dp0" %PY% -m http.server %PORT%

rem wait up to ~15s for the port to open (ping = delay that works everywhere)
for /l %%i in (1,1,15) do (
  ping -n 2 127.0.0.1 >nul
  netstat -ano | findstr /C:":%PORT% " | findstr /C:"LISTENING" >nul && goto open
)
echo.
echo [X] The server did not start on port %PORT%.
echo     Open a terminal in this folder and run:
echo         %PY% -m http.server %PORT%
echo     to see the exact error.
echo.
pause
exit /b 1

:open
rem ---------- 4) open Chrome --------------------------------
set "C1=%ProgramFiles%\Google\Chrome\Application\chrome.exe"
set "C2=%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"
set "C3=%LocalAppData%\Google\Chrome\Application\chrome.exe"
set "CHROME="
if exist "%C1%" set "CHROME=%C1%"
if not defined CHROME if exist "%C2%" set "CHROME=%C2%"
if not defined CHROME if exist "%C3%" set "CHROME=%C3%"

if defined CHROME (
  echo [i] Opening %URL% in Google Chrome ...
  start "" "%CHROME%" "%URL%"
) else (
  echo [!] Chrome was not found - opening the default browser instead.
  start "" "%URL%"
)

echo [i] Done. Keep the minimized server window open while using the app.
echo     To stop the server: close that minimized window.
ping -n 4 127.0.0.1 >nul
exit /b 0

:nopython
echo.
echo [X] Python was not found on this computer.
echo     Install it from https://www.python.org/downloads/
echo     and tick "Add python.exe to PATH" during setup, then try again.
echo.
pause
exit /b 1
