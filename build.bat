@echo off
setlocal
REM ============================================================================
REM Compila o zephyr_app (stravaV10 em Zephyr) com o nRF Connect SDK.
REM
REM   build.bat            build incremental em zephyr_app\build
REM   build.bat pristine   apaga zephyr_app\build e compila do zero
REM
REM Alvo: BOARD (padrao nrf52840dk/nrf52840, com os pinos da placa
REM myStravaB em zephyr_app\boards\nrf52840dk_nrf52840.overlay), com sysbuild.
REM Versao do SDK e do toolchain: tools\fw\ncs_env.bat.
REM Defina BUILD_DIR para compilar em outra pasta e BOARD para outro alvo
REM (por exemplo nrf54lm20dk/nrf54lm20a/cpuapp).
REM Defina NOPAUSE=1 para nao esperar tecla no fim.
REM Defina ANT=1 para compilar com o ANT: o add-on sdk-ant em SDK_ANT_DIR
REM (padrao %NCS_ROOT%\sdk-ant), zephyr_app\modules\ant_ncs33_compat e
REM zephyr_app\ant.conf; ao trocar ANT, use pristine ou outra BUILD_DIR.
REM ============================================================================

call "%~dp0tools\fw\ncs_env.bat"
if errorlevel 1 goto :fail

set "APP_DIR=%~dp0zephyr_app"
if not defined BUILD_DIR set "BUILD_DIR=%APP_DIR%\build"
REM Um BUILD_DIR relativo vale a partir da pasta atual: o build roda no zephyr_app.
for %%I in ("%BUILD_DIR%") do set "BUILD_DIR=%%~fI"
if not defined BOARD set "BOARD=nrf52840dk/nrf52840"
set "PRISTINE=auto"
if /i "%~1"=="pristine" set "PRISTINE=always"

REM ANT: o add-on e o modulo de compatibilidade com o NCS v3.3.0 entram como
REM modulos extras (barras normais para o CMake); ant.conf liga o ANT so no app.
set "WEST_EXTRA="
if not "%ANT%"=="1" goto :noant
if not defined SDK_ANT_DIR set "SDK_ANT_DIR=%NCS_ROOT%\sdk-ant"
if not exist "%SDK_ANT_DIR%\zephyr\module.yml" (
    echo sdk-ant nao encontrado em %SDK_ANT_DIR% ^(defina SDK_ANT_DIR^)
    goto :fail
)
set "ZEPHYR_EXTRA_MODULES=%SDK_ANT_DIR%;%APP_DIR%\modules\ant_ncs33_compat"
set "ZEPHYR_EXTRA_MODULES=%ZEPHYR_EXTRA_MODULES:\=/%"
set "WEST_EXTRA=-- -Dzephyr_app_EXTRA_CONF_FILE=ant.conf"
:noant

echo ============================================================================
echo Compilando %APP_DIR%
echo SDK: NCS %NCS_VERSION% (toolchain %NCS_TOOLCHAIN%)
echo Placa: %BOARD%
echo Build: %BUILD_DIR%
echo ============================================================================

REM O west precisa rodar no drive do projeto: com o NCS em C: e o projeto
REM em F:, rodar a partir de C: quebra o os.path.relpath do west.
cd /d "%APP_DIR%"
python -m west build -p %PRISTINE% -b %BOARD% -d "%BUILD_DIR%" --sysbuild "%APP_DIR%" %WEST_EXTRA%
if errorlevel 1 goto :fail

echo ============================================================================
echo BUILD OK
echo Firmware: %BUILD_DIR%\zephyr_app\zephyr\zephyr.hex
echo ============================================================================
set "RC=0"
goto :end

:fail
echo ============================================================================
echo BUILD FALHOU
echo ============================================================================
set "RC=1"

:end
if not defined NOPAUSE pause
exit /b %RC%
