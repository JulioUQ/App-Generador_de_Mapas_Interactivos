@echo off
setlocal EnableExtensions
title Actualizar carpeta wheels

rem ============================================================================
rem  Actualizar_wheels.bat   (SOLO PARA EL DESARROLLADOR)
rem  Descarga a la carpeta "wheels" todas las librerias de requirements.txt
rem  (con sus dependencias) para Windows 64 bits y Python 3.12, y comprueba que
rem  se pueden instalar sin internet. Ejecutalo cada vez que cambie requirements.txt
rem  y siempre antes de crear un paquete para compartir.
rem ============================================================================

pushd "%~dp0" || (echo No se puede acceder a la carpeta de la aplicacion. & pause & exit /b 1)

rem --- Debe coincidir con PYVER de Iniciar_Mapas.bat
set "PYVER=3.12.8"
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "BASE=%LOCALAPPDATA%\MapasInteractivos"

echo ============================================================
echo  Actualizando la carpeta "wheels" a partir de requirements.txt
echo  Necesita conexion a internet.
echo ============================================================
echo.

if not exist requirements.txt goto :sin_requirements

rem --- Buscar un Python con pip para lanzar la descarga
set "PY="
if not defined PY (py -3.12 --version >nul 2>&1 && set "PY=py -3.12")
if not defined PY (if exist "%BASE%\python\python.exe" set PY="%BASE%\python\python.exe")
if not defined PY (python --version >nul 2>&1 && set "PY=python")
if not defined PY goto :sin_python

rem --- Descargar a una carpeta temporal: si algo falla, la carpeta wheels anterior queda intacta
if exist "wheels_tmp" rmdir /s /q "wheels_tmp"
mkdir "wheels_tmp"
echo Descargando librerias (Windows 64 bits, Python 3.12)...
echo.
%PY% -m pip download --only-binary=:all: --platform win_amd64 --python-version 3.12 --implementation cp --abi cp312 -r requirements.txt -d "wheels_tmp"
if errorlevel 1 goto :error_descarga

rem --- La descarga fue bien: se sustituye la carpeta antigua (asi desaparecen las versiones obsoletas)
if exist "wheels" rmdir /s /q "wheels"
ren "wheels_tmp" "wheels"
if errorlevel 1 goto :error_descarga

rem --- Verificar de verdad: instalar en un entorno temporal SIN internet (solo si hay un Python 3.12 local)
echo.
echo Verificando que la instalacion funciona sin internet...
%PY% -c "import sys; sys.exit(0 if sys.version_info[:2]==(3,12) else 1)" >nul 2>&1
if errorlevel 1 goto :sin_verificacion
set "VERIF=%TEMP%\mapas_verificacion_venv"
if exist "%VERIF%" rmdir /s /q "%VERIF%"
%PY% -m venv "%VERIF%"
if errorlevel 1 goto :sin_verificacion
"%VERIF%\Scripts\python.exe" -m pip install --no-index --find-links "wheels" -r requirements.txt
if errorlevel 1 goto :error_verificacion
"%VERIF%\Scripts\python.exe" -c "import streamlit, geopandas, folium, pandas, numpy, openpyxl, python_calamine, pyogrio, matplotlib"
if errorlevel 1 goto :error_verificacion
rmdir /s /q "%VERIF%"
echo Verificacion correcta.
goto :instalador

:sin_verificacion
echo AVISO: no hay un Python 3.12 en este equipo para verificar la instalacion sin internet.
echo        La carpeta wheels se ha creado, pero conviene probarla en otro equipo.

:instalador
rem --- Instalador de Python para equipos sin Python ni internet (el .bat lo usa si esta junto a el)
echo.
if exist "python-%PYVER%-amd64.exe" goto :resumen
echo Descargando el instalador de Python %PYVER%...
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe' -OutFile '%CD%\python-%PYVER%-amd64.exe' -UseBasicParsing } catch { exit 1 }" >nul 2>&1
if errorlevel 1 echo AVISO: no se pudo descargar el instalador de Python. Descargalo a mano y dejalo junto a este archivo con el nombre python-%PYVER%-amd64.exe

:resumen
echo.
echo ============================================================
for /f %%N in ('dir /b "wheels\*.whl" ^| find /c /v ""') do echo  Paquetes en wheels: %%N
powershell -NoProfile -Command "$s=(Get-ChildItem wheels | Measure-Object Length -Sum).Sum/1MB; Write-Host (' Tamano de wheels: {0:N0} MB' -f $s)"
echo ============================================================
echo.
echo Listo. Cuando quieras compartir la aplicacion, ejecuta Crear_paquete.bat
goto :fin

:sin_requirements
echo ERROR: no se encuentra requirements.txt en esta carpeta.
goto :fin

:sin_python
echo ERROR: no se encuentra Python. Instala Python %PYVER% (64 bits) o ejecuta antes Iniciar_Mapas.bat.
goto :fin

:error_descarga
echo.
echo ERROR: no se pudieron descargar las librerias. La carpeta wheels anterior (si existia) no se ha tocado.
echo Causas habituales: sin internet, proxy/VPN, o alguna libreria sin version precompilada para Windows y Python 3.12.
if exist "wheels_tmp" rmdir /s /q "wheels_tmp"
goto :fin

:error_verificacion
echo.
echo ERROR: la carpeta wheels no basta para instalar sin internet. Revisa el mensaje de arriba.
if exist "%VERIF%" rmdir /s /q "%VERIF%"
goto :fin

:fin
echo.
popd
pause
endlocal
