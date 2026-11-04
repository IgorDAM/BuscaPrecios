@echo off
REM Actualiza los precios de Alcampo para la version publicada (web/movil).
REM Alcampo bloquea a los runners de GitHub, asi que se genera desde este PC
REM (abre un Chrome fuera de pantalla unos minutos) y se sube al repo.
REM Uso: doble clic, o programarlo en el Programador de tareas de Windows.
cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
git pull --rebase origin master || goto :error
python scripts\generar_precios.py --solo-alcampo || goto :error
git add webapp\static\precios_alcampo.json
git diff --cached --quiet && (echo Sin cambios en Alcampo. & goto :fin)
git commit -m "Actualiza precios_alcampo.json" || goto :error
git push origin master || goto :error
echo Listo: Alcampo actualizado y subido.
goto :fin
:error
echo ERROR: algo ha fallado, mira los mensajes de arriba.
:fin
pause
