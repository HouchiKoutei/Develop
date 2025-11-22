rem Detect Python dictionary
for /d %%d in ("C:\Users\a2003408\Documents\ProgramFiles\Coding\WinPython64\python-3.6.5.amd64\","D:\ProgramFiles\Coding\WPy64-38100\python-3.8.10.amd64\","D:\ProgramFiles\Coding\WPy64-31220\python-3.12.2.amd64\") do (
    echo start find: %%d
    if exist "%%dpython.exe" (
        set PYTHON_DIR=%%d
        echo Python directory found: %%d
    )
)

rem Display error and exit if Python is not found
if not defined PYTHON_DIR (
    echo Python not found!
    exit /b 1
)

rem Move to Python installation directory and install packages
echo Current directory: %CD%
pushd "%PYTHON_DIR%"
echo Current directory: %CD%
python -m pip install --upgrade pythonnet
python -m pip install -U pip
python -m pip install --upgrade pip

python -m pip install pyautogui
python -m pip install Pillow
python -m pip install pynput

python -m pip install pyocr

python -m pip install xmltodict
python -m pip install dicttoxml

python -m pip install dicttoxml

python -m pip install opencv-python
python -m pip install chardet

python -m pip install pytk
python -m pip install --upgrade pip wheel setuptools
python -m pip install docutils pygments pypiwin32 kivy.deps.glew
python -m pip install kivy.deps.gstreamer
python -m pip install kivy
python -m pip install kivymd
python -m pip install japanize-kivy
python -m pip install watchdog
python -m pip install keyboard
python -m pip install pyreadline
python -m pip install pandas
python -m pip install json_log_formatter
python -m pip install python-json-logger
python -m pip install cython
python -m pip install pyjnius
python -m pip install asynckivy
python -m pip install plyer
python -m pip install kivymd
python -m pip install portalocker
python -m pip install https://github.com/pyinstaller/pyinstaller/archive/develop.tar.gz
python -m pip install pygetwindow psutil

python -m pip install gym
python -m pip install torch
python -m pip install stable_baselines3
python -m pip install DQN

echo Please set VSCode Python:Default interpreter Path 
echo %PYTHON_DIR%\python.exe
pause
