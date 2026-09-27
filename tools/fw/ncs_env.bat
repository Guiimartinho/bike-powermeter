@echo off
REM ============================================================================
REM Ambiente do nRF Connect SDK para os scripts .bat do projeto.
REM
REM   call tools\fw\ncs_env.bat
REM
REM Variaveis opcionais (defina antes do call):
REM   NCS_ROOT       pasta de instalacao do NCS            (padrao: C:\ncs)
REM   NCS_VERSION    versao do SDK                           (padrao: v3.3.0)
REM   NCS_TOOLCHAIN  id do toolchain em NCS_ROOT\toolchains  (padrao: 936afb6332)
REM
REM Reproduz o environment.json do toolchain e define ZEPHYR_BASE.
REM Nao use o nome TOOLCHAIN_ROOT: o Zephyr le essa variavel como raiz das
REM definicoes de toolchain e o build quebra.
REM Sai com errorlevel 1 se o SDK ou o toolchain nao existirem.
REM ============================================================================

if not defined NCS_ROOT set "NCS_ROOT=C:\ncs"
if not defined NCS_VERSION set "NCS_VERSION=v3.3.0"
if not defined NCS_TOOLCHAIN set "NCS_TOOLCHAIN=936afb6332"

set "NCS_TOOLCHAIN_DIR=%NCS_ROOT%\toolchains\%NCS_TOOLCHAIN%"
set "ZEPHYR_BASE=%NCS_ROOT%\%NCS_VERSION%\zephyr"

if not exist "%NCS_TOOLCHAIN_DIR%\opt\bin\python.exe" (
    echo ERRO: toolchain nao encontrado em %NCS_TOOLCHAIN_DIR%
    echo Confira NCS_TOOLCHAIN com: type "%NCS_ROOT%\toolchains\toolchains.json"
    exit /b 1
)
if not exist "%ZEPHYR_BASE%\VERSION" (
    echo ERRO: SDK nao encontrado em %NCS_ROOT%\%NCS_VERSION%
    exit /b 1
)

set "ZEPHYR_TOOLCHAIN_VARIANT=zephyr"
set "ZEPHYR_SDK_INSTALL_DIR=%NCS_TOOLCHAIN_DIR%\opt\zephyr-sdk"
set "NRFUTIL_HOME=%NCS_TOOLCHAIN_DIR%\nrfutil\home"
set "PYTHONPATH=%NCS_TOOLCHAIN_DIR%\opt\bin;%NCS_TOOLCHAIN_DIR%\opt\bin\Lib;%NCS_TOOLCHAIN_DIR%\opt\bin\Lib\site-packages"
set "PATH=%NCS_TOOLCHAIN_DIR%;%NCS_TOOLCHAIN_DIR%\mingw64\bin;%NCS_TOOLCHAIN_DIR%\bin;%NCS_TOOLCHAIN_DIR%\opt\bin;%NCS_TOOLCHAIN_DIR%\opt\bin\Scripts;%NCS_TOOLCHAIN_DIR%\opt\nanopb\generator-bin;%NCS_TOOLCHAIN_DIR%\nrfutil\bin;%NCS_TOOLCHAIN_DIR%\opt\zephyr-sdk\arm-zephyr-eabi\bin;%PATH%"
exit /b 0
