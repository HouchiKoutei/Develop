@echo off
setlocal enabledelayedexpansion

rem ---------------------------------------------------------
rem  Detect Python installation directory
rem ---------------------------------------------------------

for %%d in (
    "C:\Users\a2003408\Documents\ProgramFiles\Coding\WPy64-38100\python-3.8.10.amd64"
    "D:\ProgramFiles\Coding\WPy64-38100\python-3.8.10.amd64"
    "D:\ProgramFiles\Coding\WPy64-31220\python-3.12.2.amd64"
    "D:\ProgramFiles\Coding\WPy64-313110\python"
) do (
    echo Checking: %%d
    if exist "%%d\python.exe" (
        set PYTHON_DIR=%%d
        echo Python directory found: %%d
    )
)

rem ---------------------------------------------------------
rem  Error if Python not found
rem ---------------------------------------------------------
if not defined PYTHON_DIR (
    echo ERROR: Python not found in any of the listed directories.
    exit /b 1
)

rem ---------------------------------------------------------
rem  Move to Python directory
rem ---------------------------------------------------------
echo Current directory: %CD%
pushd "%PYTHON_DIR%"
echo Switched to directory: %CD%

rem ---------------------------------------------------------
rem  Install packages
rem ---------------------------------------------------------

rem Use the detected Python executable to ensure packages install into the correct interpreter
set "PYTHON_EXE=%PYTHON_DIR%\python.exe"

%PYTHON_EXE% -m pip install --upgrade pythonnet
%PYTHON_EXE% -m pip install -U pip
%PYTHON_EXE% -m pip install --upgrade pip

rem --- 1. Core build tools ---
%PYTHON_EXE% -m pip install -U pip wheel setuptools cython
%PYTHON_EXE% -m pip install docutils pygments pypiwin32 dataclasses pythonnet portalocker cryptography

rem --- 2. AI / Machine Learning / NLP ---
%PYTHON_EXE% -m pip install torchvision tensorboard sentence_transformers
%PYTHON_EXE% -m pip install ollama tavily-python tiktoken pydantic

rem --- 3. Image processing / OCR / Capture ---
%PYTHON_EXE% -m pip install Pillow opencv-python imagehash pyocr mss

rem --- 4. Automation / OS control ---
%PYTHON_EXE% -m pip install pyautogui pynput keyboard pygetwindow psutil watchdog pyreadline ultralytics

rem --- 5. Kivy GUI framework ---
%PYTHON_EXE% -m pip install kivy.deps.glew kivy.deps.gstreamer
%PYTHON_EXE% -m pip install kivy kivymd asynckivy japanize-kivy plyer pyjnius

rem --- 6. Data processing / Serialization / Communication ---
%PYTHON_EXE% -m pip install pandas xmltodict dicttoxml pyopenssl
%PYTHON_EXE% -m pip install json_log_formatter python-json-logger chardet
%PYTHON_EXE% -m pip install pymodbus pyserial flask flask_socketio PyYAML

rem --- 7. Development tools ---
%PYTHON_EXE% -m pip install https://github.com/pyinstaller/pyinstaller/archive/develop.tar.gz

echo ---------------------------------------------------------
echo VSCode Python Interpreter Path:
echo %PYTHON_DIR%\python.exe
echo ---------------------------------------------------------

pause