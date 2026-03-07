@echo off
setlocal EnableDelayedExpansion

:: --- Settings ---
set "ADB=D:\ProgramFiles\RemoteControl\scrsndcpy\scrcpy\adb.exe"
set "SCRCPY=D:\ProgramFiles\RemoteControl\scrsndcpy\scrcpy\scrcpy.exe"
set "IPFILE=devices.txt"

:: --- Launch header ---
cls
echo =====================================
echo SCRCPY WiFi Launcher
echo =====================================
echo.

:: --- Ask for device registration ---
set "CHOICE="
set /p "CHOICE=Register new devices? (Y/N): "
if /I "%CHOICE%"=="Y" goto REGISTER_LOOP
goto ASK_AUDIO

:: =========================
:: USB registration loop
:: =========================
:REGISTER_LOOP
cls
echo =====================================
echo Connect your Android device via USB
echo Press OK on the USB debugging prompt
echo =====================================
echo.
"%ADB%" kill-server >nul 2>&1
"%ADB%" start-server >nul 2>&1

:WAIT_DEVICE
set "SERIAL="
for /f "tokens=1,2" %%i in ('%ADB% devices 2^>nul') do (
    if "%%j"=="device" set "SERIAL=%%i"
)
if not defined SERIAL (
    echo Waiting for USB device...
    echo Please allow USB debugging on your phone.
    timeout /t 3 >nul
    goto WAIT_DEVICE
)
echo Device detected: !SERIAL!

:: --- Get WiFi IP ---
set "IP="
for /f "tokens=9" %%a in ('%ADB% -s !SERIAL! shell ip route 2^>nul ^| findstr wlan0') do (
    set "IP=%%a"
)
if not defined IP (
    echo ERROR: Could not detect WiFi IP.
    echo Make sure WiFi is enabled on the device.
    goto REGISTER_NEXT
)
echo Found IP: !IP!

:: --- Switch to TCP/IP mode ---
"%ADB%" -s !SERIAL! tcpip 5555 >nul 2>&1
timeout /t 2 >nul

:: --- Create devices.txt if it doesn't exist ---
if not exist "%IPFILE%" type nul > "%IPFILE%"

:: --- Check for duplicates & register ---
findstr /x "!IP!" "%IPFILE%" >nul 2>&1
if errorlevel 1 (
    echo !IP!>>"%IPFILE%"
    echo Registered: !IP!
) else (
    echo Already registered: !IP!
)

:REGISTER_NEXT
echo.
set "CHOICE="
set /p "CHOICE=Register another device? (Y/N): "
if /I "%CHOICE%"=="Y" goto REGISTER_LOOP

:: =========================
:: Ask audio transfer option
:: =========================
:ASK_AUDIO
echo.
echo =====================================
echo Audio Transfer Option
echo =====================================
echo   Y = Audio ON  : PC plays audio  / Phone silent
echo   N = Audio OFF : Phone plays audio / PC silent
echo =====================================
set "AUDIO_TRANSFER="
set /p "AUDIO_TRANSFER=Transfer phone audio to PC? (Y/N): "
if /I "%AUDIO_TRANSFER%"=="Y" (
    set "USE_AUDIO=1"
) else (
    set "USE_AUDIO=0"
)

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
    pause
    exit /b
)

for %%A in ("%IPFILE%") do if %%~zA==0 (
    echo No registered devices found.
    pause
    exit /b
)

for /f %%i in (%IPFILE%) do (
    echo -----------------------------------
    echo Connecting %%i ...
    "%ADB%" connect %%i:5555 >nul 2>&1

    if "!USE_AUDIO!"=="1" (
        echo   [AUDIO] PC playback ON / Phone speaker OFF
        "%ADB%" connect %%i:5555 >nul
        start "" "%SCRCPY%" -s %%i:5555 --window-title "%%i"
    ) else (
        echo   [AUDIO] Phone speaker ON / PC silent
        start "" cmd /c ""%SCRCPY%" -s %%i:5555 --window-title "%%i" --video-source=display --no-audio"
    )

    timeout /t 1 >nul
)

echo.
echo ===== ALL DEVICES CONNECTED =====
pause
exit /b