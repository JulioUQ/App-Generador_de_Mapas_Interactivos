@echo off
setlocal EnableExtensions
title Crear paquete para compartir

rem ============================================================================
rem  Crear_paquete.bat   (SOLO PARA EL DESARROLLADOR)
rem  Genera dist\MapasInteractivos_AAAAMMDD.zip con la aplicacion, la carpeta
rem  instalador (wheels + instalador de Python), sin .venv, .git, data ni __pycache__.
rem  Para que no se incluya algo mas (por ejemplo, datos confidenciales), anadelo
rem  a la lista /XD (carpetas) o /XF (archivos) del comando robocopy de abajo.
rem ============================================================================

pushd "%~dp0.." || (echo No se puede acceder a la carpeta de la aplicacion. & pause & exit /b 1)

set "PYVER=3.12.8"

dir /b "instalador\wheels\*.whl" >nul 2>&1
if errorlevel 1 goto :sin_wheels
if not exist "instalador\python-%PYVER%-amd64.exe" echo AVISO: falta instalador\python-%PYVER%-amd64.exe; los equipos sin Python necesitaran internet para instalarlo.
echo.

for /f %%D in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd"') do set "FECHA=%%D"
set "RAIZ=%TEMP%\MapasInteractivos_paquete"
set "STAGE=%RAIZ%\MapasInteractivos"
if exist "%RAIZ%" rmdir /s /q "%RAIZ%"

echo Copiando archivos...
robocopy "." "%STAGE%" /E /XD ".venv" "__pycache__" ".git" "dist" "data" "wheels_tmp" /XF "*.pyc" ".gitignore" ".gitattributes" "_gitignore" "_gitattributes" /NFL /NDL /NJH /NJS /NP
if errorlevel 8 goto :error_copia

if not exist "dist" mkdir "dist"
set "ZIP=dist\MapasInteractivos_%FECHA%.zip"
if exist "%ZIP%" del "%ZIP%"
echo Comprimiendo (puede tardar un poco)...
tar -a -c -f "%ZIP%" -C "%RAIZ%" "MapasInteractivos"
if errorlevel 1 goto :error_zip
rmdir /s /q "%RAIZ%"

echo.
echo ============================================================
echo  Paquete creado: %CD%\%ZIP%
echo.
echo  Instrucciones para quien lo reciba:
echo    1. Descomprimir el .zip COMPLETO en una carpeta (no ejecutar desde dentro del zip).
echo    2. Doble clic en scripts\Iniciar_Mapas.bat.
echo ============================================================
goto :fin

:sin_wheels
echo ERROR: la carpeta instalador\wheels no existe o esta vacia. Ejecuta antes Actualizar_wheels.bat.
goto :fin

:error_copia
echo ERROR: no se pudieron copiar los archivos.
goto :fin

:error_zip
echo ERROR: no se pudo crear el zip. Necesitas Windows 10 (1803) o superior, que incluye el comando tar.
goto :fin

:fin
echo.
popd
pause
endlocal
