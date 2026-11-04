@echo off
REM Actualiza Alcampo ENTERO haciendo todas las pasadas seguidas, sin que tengas
REM que estar delante (Alcampo corta a las ~25 peticiones, asi que se reparte en
REM varias pasadas). Pensado para el Programador de tareas (ver
REM scripts\programar_alcampo.ps1) o para lanzarlo a mano y dejarlo.
REM
REM En cada pasada llama a actualizar_alcampo.bat. Si queda trabajo (existe
REM data\alcampo_progreso.json) espera unos minutos y sigue; si no, ha terminado
REM (o ha fallado por otra causa: en ese caso tambien se para).
cd /d "%~dp0.."
set MAX_PASADAS=10
set ESPERA_S=600
set N=0
:bucle
set /a N+=1
echo.
echo ===== Alcampo: pasada %N% de %MAX_PASADAS% =====
call scripts\actualizar_alcampo.bat nopause
if not exist data\alcampo_progreso.json goto :fin
if %N% GEQ %MAX_PASADAS% goto :tope
echo Quedan secciones por descargar. Espero %ESPERA_S% segundos y sigo...
REM ping en vez de timeout: timeout falla cuando lo lanza el Programador de tareas.
ping -n %ESPERA_S% 127.0.0.1 >nul
goto :bucle
:tope
echo Se alcanzo el maximo de %MAX_PASADAS% pasadas sin terminar: el progreso queda guardado para la proxima vez.
:fin
echo Fin.
if /i not "%1"=="nopause" pause
