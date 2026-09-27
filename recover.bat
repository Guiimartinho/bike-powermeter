@echo off
setlocal
REM ============================================================================
REM Recupera um nRF52840 ou nRF54 protegido: apaga TODA a memoria e a UICR
REM e libera a porta de debug. Use antes do flash.bat quando a gravacao falhar
REM por protecao.
REM
REM Com mais de um J-Link conectado, defina NRF_SERIAL. BOARD ou FAMILY
REM escolhem a familia do nrfutil, como no flash.bat.
REM Defina NOPAUSE=1 para nao esperar tecla no fim.
REM ============================================================================

call "%~dp0tools\fw\ncs_env.bat"
if errorlevel 1 goto :fail

if not defined BOARD set "BOARD=nrf52840dk/nrf52840"
if not defined FAMILY (
    echo %BOARD%| findstr /i "nrf54l" >nul && (set "FAMILY=nrf54l") || (set "FAMILY=nrf52")
)
set "SELECT=--traits jlink"
if defined NRF_SERIAL set "SELECT=--serial-number %NRF_SERIAL%"

echo ============================================================================
echo ATENCAO: isto apaga TODO o conteudo do chip.
echo ============================================================================
nrfutil device recover %SELECT% --family %FAMILY%
if errorlevel 1 goto :fail

echo ============================================================================
echo RECOVER OK: a placa esta desbloqueada. Rode flash.bat.
echo ============================================================================
set "RC=0"
goto :end

:fail
echo ============================================================================
echo RECOVER FALHOU
echo ============================================================================
set "RC=1"

:end
if not defined NOPAUSE pause
exit /b %RC%
