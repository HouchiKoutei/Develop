@echo off
setlocal EnableDelayedExpansion

:: --- Settings ---
set "ADB=D:\ProgramFiles\RemoteControl\scrsndcpy\scrcpy\adb.exe"
set "SCRCPY=D:\ProgramFiles\RemoteControl\scrsndcpy\scrcpy\scrcpy.exe"
set "IPFILE=devices.txt"

:: --- Launch header ---
cls
echo =====================================
echo       SCRCPY WiFi Launcher
echo =====================================
echo.

:: --- Ask for device registration ---
set "CHOICE="
set /p "CHOICE=Register new devices? (Y/N): "

if /I "%CHOICE%"=="Y" goto REGISTER_LOOP
goto CONNECT_DEVICES

:: =========================
:: USB registration loop
:: =========================
:REGISTER_LOOP
cls
echo =====================================
echo   Connect Android via USB
echo =====================================
echo.

"%ADB%" kill-server >nul
"%ADB%" start-server >nul

:: --- Wait for USB device ---
set "SERIAL="
:WAIT_DEVICE
for /f "skip=1 tokens=1" %%i in ('%ADB% devices') do (
    if not "%%i"=="" set "SERIAL=%%i"
)

if not defined SERIAL (
    timeout /t 2 >nul
    goto WAIT_DEVICE
)

echo Device detected: !SERIAL!

:: --- Get WiFi IP ---
set "IP="
for /f "tokens=9" %%a in ('%ADB% -s !SERIAL! shell ip route ^| findstr wlan0') do (
    set "IP=%%a"
)

if not defined IP (
    echo ERROR: Could not detect WiFi IP. Make sure WiFi is ON.
    goto REGISTER_NEXT
)

echo Found IP: !IP!

:: --- Switch to TCP/IP mode ---
"%ADB%" -s !SERIAL! tcpip 5555 >nul
timeout /t 2 >nul

:: --- Create devices.txt if it doesn't exist ---
if not exist "%IPFILE%" type nul > "%IPFILE%"

:: --- Check for duplicates & register ---
findstr /x "!IP!" "%IPFILE%" >nul 2>&1
if errorlevel 1 (
    echo !IP!>>"%IPFILE%"
    echo Registered.
) else (
    echo Already registered.
)

:REGISTER_NEXT
:: --- Ask for next device ---
echo.
set "CHOICE="
set /p "CHOICE=Register another device? (Y/N): "
if /I "%CHOICE%"=="Y" goto REGISTER_LOOP

:: =========================
:: Connect all registered devices
:: =========================
:CONNECT_DEVICES
cls
echo =====================================
echo Connecting ALL registered devices
echo =====================================
echo.

if not exist "%IPFILE%" (
    echo No registered devices found.
    exit /b
)

:: --- Check if file is empty ---
for %%A in ("%IPFILE%") do if %%~zA==0 (
    echo No registered devices found.
    exit /b
)

:: --- Connect to IPs sequentially ---
for /f %%i in (%IPFILE%) do (
    echo Connecting %%i ...
    "%ADB%" connect %%i:5555 >nul
    start "" "%SCRCPY%" -s %%i:5555 --window-title "%%i"
)

echo.
echo ===== ALL DEVICES CONNECTED =====
exit /b
