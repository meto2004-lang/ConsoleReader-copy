@echo off
rem ============================================================
rem  ConsoleReader - server only (no browser on the PC)
rem  Use this when you control the app from a phone/tablet.
rem  Shows the local URLs to open on the phone.
rem  Close this window to stop the server.
rem ============================================================
setlocal EnableExtensions
title ConsoleReader server
cd /d "%~dp0"

set "PORT=8000"

if not exist "app\index.html" (
  echo.
  echo [X] app\index.html was not found next to this file.
  echo     Put this launcher in the project root, beside the "app" folder.
  echo     Current folder: %CD%
  echo.
  pause
  exit /b 1
)

set "PY="
python --version >nul 2>nul && set "PY=python"
if not defined PY (py -3 --version >nul 2>nul && set "PY=py -3")
if not defined PY goto nopython

netstat -ano | findstr /C:":%PORT% " | findstr /C:"LISTENING" >nul
if not errorlevel 1 (
  echo [i] The server is already running on port %PORT%.
  goto show
)

echo [i] Starting the server on port %PORT% ...
start "ConsoleReader server - close this window to stop" /min /d "%~dp0" %PY% -m http.server %PORT%

for /l %%i in (1,1,15) do (
  ping -n 2 127.0.0.1 >nul
  netstat -ano | findstr /C:":%PORT% " | findstr /C:"LISTENING" >nul && goto show
)
echo.
echo [X] The server did not start on port %PORT%.
echo     Open a terminal in this folder and run:
echo         %PY% -m http.server %PORT%
echo     to see the exact error.
echo.
pause
exit /b 1

:show
echo.
echo ============================================================
echo  Server is running. Open one of these on your PHONE/TABLET
echo  (same Wi-Fi network as this computer, Chrome browser):
echo ============================================================
echo.
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /C:"IPv4"') do call :showip "%%a"
echo.
echo  On this computer: http://localhost:%PORT%/app/
echo.
echo  NOTE (Android): Web Bluetooth needs a secure context. If the
echo  page shows a yellow warning, open in Chrome on the phone:
echo      chrome://flags/#unsafely-treat-insecure-origin-as-secure
echo  enable it, add  http://<this-computer-ip>:%PORT%  to the list,
echo  tap Relaunch, then reopen the page above.
echo.
echo  Firewall: if the phone cannot load the page, allow TCP %PORT%
echo  (run as Administrator):
echo      New-NetFirewallRule -DisplayName "ConsoleReader web (TCP %PORT%)" -Direction Inbound -Protocol TCP -LocalPort %PORT% -Action Allow -Profile Private
echo.
echo  Close this window to stop the server.
echo ============================================================
pause
exit /b 0

:showip
rem prints one clean URL per IPv4 address (strips the spaces ipconfig adds)
rem ويرشّح العناوين غير المفيدة (loopback / APIPA) ويعلّم العناوين غير المعتادة
rem مثل عناوين VPN حتى لا يجرب المستخدم عنوانًا لا يصل منه الجوال.
set "IP=%~1"
if not defined IP exit /b 0
for /f "tokens=* delims= " %%z in ("%IP%") do set "IP=%%z"
echo %IP% | findstr /B /C:"127." >nul && exit /b 0
echo %IP% | findstr /B /C:"169.254." >nul && exit /b 0
echo %IP% | findstr /B /C:"192.168." >nul && (echo      http://%IP%:%PORT%/app/ & exit /b 0)
echo %IP% | findstr /B /C:"10." >nul && (echo      http://%IP%:%PORT%/app/ & exit /b 0)
echo      http://%IP%:%PORT%/app/   (check: Wi-Fi address, not VPN)
exit /b 0

:nopython
echo.
echo [X] Python was not found on this computer.
echo     Install it from https://www.python.org/downloads/
echo     and tick "Add python.exe to PATH" during setup, then try again.
echo.
pause
exit /b 1
