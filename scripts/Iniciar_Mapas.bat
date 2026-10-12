@echo off
setlocal EnableExtensions
title Generador de mapas interactivos

rem ============================================================================
rem  Iniciar_Mapas.bat
rem  Doble clic y listo: prepara Python (si hace falta), instala las librerias
rem  y abre la aplicacion en el navegador. No requiere permisos de administrador.
rem ============================================================================

rem --- Version de Python que se instala automaticamente si el equipo no tiene ninguna valida
set "PYVER=3.12.8"

rem --- Trabajar desde la RAIZ del proyecto (este .bat esta en scripts\; pushd tambien vale en unidades de red \\servidor\...)
pushd "%~dp0.." || (echo No se puede acceder a la carpeta de la aplicacion. & pause & exit /b 1)

rem --- Todo lo "pesado" (Python propio y entorno virtual) se guarda en el disco LOCAL de cada usuario:
rem     es mas rapido, evita problemas en carpetas de red y cada persona tiene el suyo.
if not defined LOCALAPPDATA set "LOCALAPPDATA=%USERPROFILE%\AppData\Local"
set "BASE=%LOCALAPPDATA%\MapasInteractivos"
set "VENV=%BASE%\venv"
set "PYEXE=%VENV%\Scripts\python.exe"
set "PYLOCAL=%BASE%\python\python.exe"
set "REQ_OK=%VENV%\requirements.instalado.txt"

rem --- Si el entorno existe y sus librerias se instalaron por completo (y no han cambiado), arrancar
if not exist "%PYEXE%" goto :crear
rem Un entorno copiado desde otro ordenador (o con su Python desinstalado) existe pero no funciona: se recrea
"%PYEXE%" -c "import sys" >nul 2>&1
if errorlevel 1 goto :entorno_roto
fc /b requirements.txt "%REQ_OK%" >nul 2>&1
if errorlevel 1 goto :instalar
goto :arrancar

:entorno_roto
echo El entorno de Python guardado en este ordenador no funciona (se movio o se desinstalo su Python). Se recreara.
echo.

:crear
echo ============================================================
echo  Preparando la aplicacion por primera vez.
echo  Puede tardar unos minutos y necesita conexion a internet
echo  (salvo que exista la carpeta "instalador\wheels" en el proyecto).
echo ============================================================
echo.

rem --- 1) Buscar un Python valido. Solo versiones con librerias precompiladas (3.10 a 3.13).
set "PY="
if exist "%PYLOCAL%" set PY="%PYLOCAL%"
rem Con la carpeta "instalador\wheels" solo vale Python 3.12 (las librerias precompiladas son para esa version)
set "VERS=3.12 3.11 3.13 3.10"
if exist "instalador\wheels" set "VERS=3.12"
for %%V in (%VERS%) do if not defined PY (py -%%V --version >nul 2>&1 && set "PY=py -%%V")
if defined PY goto :python_listo

rem --- 2) No hay ninguno: descargar e instalar Python solo para este usuario (sin administrador)
echo No se ha encontrado una version valida de Python. Instalando Python %PYVER% para este usuario...
echo.
set "PYINST=%TEMP%\python-%PYVER%-instalador.exe"
if exist "%PYINST%" del "%PYINST%" >nul 2>&1
if exist "instalador\python-%PYVER%-amd64.exe" copy /y "instalador\python-%PYVER%-amd64.exe" "%PYINST%" >nul
if exist "%PYINST%" goto :instalador_descargado
powershell -NoProfile -ExecutionPolicy Bypass -Command "[Net.ServicePointManager]::SecurityProtocol=[Net.SecurityProtocolType]::Tls12; try { Invoke-WebRequest 'https://www.python.org/ftp/python/%PYVER%/python-%PYVER%-amd64.exe' -OutFile '%PYINST%' -UseBasicParsing } catch { exit 1 }" >nul 2>&1
if errorlevel 1 goto :sin_python
if not exist "%PYINST%" goto :sin_python

:instalador_descargado
start "" /wait "%PYINST%" /quiet InstallAllUsers=0 PrependPath=0 Include_launcher=0 Include_test=0 Include_tcltk=1 "TargetDir=%BASE%\python"
del "%PYINST%" >nul 2>&1
if not exist "%PYLOCAL%" goto :sin_python
set PY="%PYLOCAL%"

:python_listo
rem Si quedo un entorno a medias de un intento anterior, se borra y se empieza de cero
if exist "%VENV%" rmdir /s /q "%VENV%"
%PY% -m venv "%VENV%"
if errorlevel 1 goto :error_venv
if not exist "%PYEXE%" goto :error_venv

:instalar
echo Instalando las librerias necesarias (solo cuando hace falta)...
echo.
rem Si existe la carpeta "instalador\wheels" se instala sin internet; si falla (o no existe) se usa internet
if not exist "instalador\wheels" goto :instalar_online
"%PYEXE%" -m pip install --no-index --find-links "instalador\wheels" -r requirements.txt
if not errorlevel 1 goto :verificar
echo.
echo La instalacion sin conexion no ha funcionado. Se intentara descargar de internet...
echo.

:instalar_online
"%PYEXE%" -m pip install -r requirements.txt
if errorlevel 1 goto :error_pip

:verificar
rem Comprobar de verdad que lo esencial se puede importar antes de dar el entorno por bueno
"%PYEXE%" -c "import streamlit, geopandas, folium, pandas, openpyxl" >nul 2>&1
if errorlevel 1 goto :error_pip

rem Solo ahora se marca como instalado: si algo fallo antes, la proxima vez se reintenta
copy /y requirements.txt "%REQ_OK%" >nul
echo.
echo Instalacion terminada correctamente.
echo.

:arrancar
rem Evitar que Streamlit se quede esperando un email en la primera ejecucion
set "CRED=%USERPROFILE%\.streamlit\credentials.toml"
if exist "%CRED%" goto :cred_ok
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
(echo [general]& echo email = "") > "%CRED%"
:cred_ok

rem Aviso (no bloqueante): sin tkinter no funciona el boton "Elegir capas del disco"
"%PYEXE%" -c "import tkinter" >nul 2>&1
if errorlevel 1 (
  echo AVISO: este Python no incluye tkinter. El boton "Elegir capas del disco" no funcionara;
  echo        se podran subir las capas arrastrandolas. Para activarlo, reinstala Python
  echo        dejando marcada la opcion "tcl/tk and IDLE".
  echo.
)
echo Abriendo la aplicacion en el navegador. No cierres esta ventana mientras la uses.
echo.
rem localhost: evita el aviso del firewall de Windows. gatherUsageStats=false: sin preguntas ni telemetria.
"%PYEXE%" -m streamlit run app.py --server.address localhost --browser.gatherUsageStats false
if errorlevel 1 (
  echo.
  echo La aplicacion se ha cerrado con un error. Copia el mensaje de arriba si necesitas ayuda.
)
goto :fin

:sin_python
echo.
echo ERROR: no se ha podido preparar Python en este ordenador.
echo Causas habituales: sin conexion a internet, o una red corporativa que bloquea la descarga.
echo Solucion manual:
echo   1. Instala Python %PYVER% (64 bits) desde https://www.python.org/downloads/
echo   2. Durante la instalacion deja marcadas "tcl/tk and IDLE" y "py launcher".
echo   3. Vuelve a hacer doble clic en este archivo.
echo Alternativa sin internet: copia python-%PYVER%-amd64.exe en la carpeta "instalador" del proyecto.
goto :fin

:error_venv
echo.
echo ERROR: no se pudo crear el entorno de la aplicacion en %VENV%.
echo Comprueba que tienes permiso para escribir en esa ruta y que hay espacio en disco.
goto :fin

:error_pip
echo.
echo ERROR: no se pudieron instalar las librerias necesarias.
echo Causas habituales:
echo   - Sin conexion a internet, o una red corporativa que bloquea pip (proxy/VPN).
echo   - Falta de espacio en disco.
echo Cuando lo soluciones, vuelve a hacer doble clic en este archivo: se reintentara solo.
echo Si el problema continua, envia una captura de esta ventana.
goto :fin

:fin
echo.
popd
pause
endlocal
