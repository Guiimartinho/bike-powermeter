@echo off
setlocal
REM ============================================================================
REM Monitor serial do console do firmware (log do Zephyr).
REM
REM   serial.bat            usa a porta de SERIAL_PORT ou COM11
REM   serial.bat COM7       usa a porta indicada
REM   serial.bat COM7 9600  porta e baud rate
REM
REM No nRF52840-DK o console e o uart0 (115200 baud), exposto pela porta
REM VCOM do J-Link. Descubra a porta com: nrfutil device list
REM Ctrl+] encerra o miniterm.
REM ============================================================================

call "%~dp0tools\fw\ncs_env.bat"
if errorlevel 1 goto :fail

if not defined SERIAL_PORT set "SERIAL_PORT=COM11"
if not "%~1"=="" set "SERIAL_PORT=%~1"
set "BAUDRATE=115200"
if not "%~2"=="" set "BAUDRATE=%~2"

echo ============================================================================
echo Monitor serial: %SERIAL_PORT% a %BAUDRATE% baud (Ctrl+] para sair)
echo ============================================================================
python -m serial.tools.miniterm %SERIAL_PORT% %BAUDRATE%
set "RC=%ERRORLEVEL%"
goto :end

:fail
set "RC=1"

:end
if not defined NOPAUSE pause
exit /b %RC%
