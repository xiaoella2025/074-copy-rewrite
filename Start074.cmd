@echo off
REM app074 launcher
set URL=http://127.0.0.1:18801
set APPDIR=D:\1Leida-shipinhao\074-copy-rewrite
set PY=C:\Users\Admin\AppData\Local\Programs\Python\Python314\pythonw.exe
set EDGE=C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe

REM 启动 pythonw（无窗口）
start "" /b "%PY%" "%APPDIR%\server.py"

REM 等 3 秒让服务起来
ping -n 3 127.0.0.1 >nul

REM 打开浏览器（--new-window 强制新窗口）
if exist "%EDGE%" (
    start "" "%EDGE%" --new-window %URL%
) else (
    start "" %URL%
)

exit