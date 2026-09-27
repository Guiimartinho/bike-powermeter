@echo off
setlocal
REM ============================================================================
REM Grava o firmware do zephyr_app no DK pelo J-Link da placa.
REM
REM   flash.bat          apaga a flash inteira antes (perde configuracoes e bonds BLE)
REM   flash.bat keep     apaga so as faixas do firmware (mantem a particao de settings)
REM
REM Com mais de um J-Link conectado, defina NRF_SERIAL com o numero de serie
REM mostrado por: nrfutil device list
REM BOARD escolhe a familia do nrfutil (nrf54l para nrf54lm20dk/..., nrf52 no
REM padrao); FAMILY a define direto.
REM Defina NOPAUSE=1 para nao esperar tecla no fim.
REM ============================================================================

call "%~dp0tools\fw\ncs_env.bat"
if errorlevel 1 goto :fail

if not defined BUILD_DIR set "BUILD_DIR=%~dp0zephyr_app\build"
set "FIRMWARE="
if exist "%BUILD_DIR%\merged.hex" set "FIRMWARE=%BUILD_DIR%\merged.hex"
if not defined FIRMWARE if exist "%BUILD_DIR%\zephyr_app\zephyr\zephyr.hex" set "FIRMWARE=%BUILD_DIR%\zephyr_app\zephyr\zephyr.hex"
if not defined FIRMWARE if exist "%BUILD_DIR%\zephyr\zephyr.hex" set "FIRMWARE=%BUILD_DIR%\zephyr\zephyr.hex"
if not defined FIRMWARE (
    echo ERRO: firmware nao encontrado em %BUILD_DIR%. Rode build.bat antes.
    goto :fail
)

set "ERASE=ERASE_ALL"
if /i "%~1"=="keep" set "ERASE=ERASE_RANGES_TOUCHED_BY_FIRMWARE"

if not defined BOARD set "BOARD=nrf52840dk/nrf52840"
if not defined FAMILY (
    echo %BOARD%| findstr /i "nrf54l" >nul && (set "FAMILY=nrf54l") || (set "FAMILY=nrf52")
)
set "SELECT=--traits jlink"
if defined NRF_SERIAL set "SELECT=--serial-number %NRF_SERIAL%"

echo ============================================================================
echo Gravando %FIRMWARE%
echo Apagamento: %ERASE%
echo Familia: %FAMILY%
echo ============================================================================
nrfutil device list --traits jlink
nrfutil device program %SELECT% --family %FAMILY% --firmware "%FIRMWARE%" --options chip_erase_mode=%ERASE%,verify=VERIFY_READ,reset=RESET_SYSTEM
if errorlevel 1 (
    echo Se a placa estiver protegida, rode recover.bat antes.
    goto :fail
)

echo ============================================================================
echo GRAVACAO OK
echo ============================================================================
set "RC=0"
goto :end

:fail
echo ============================================================================
echo GRAVACAO FALHOU
echo ============================================================================
set "RC=1"

:end
if not defined NOPAUSE pause
exit /b %RC%
