@echo off
REM Actualiza Alcampo para la version publicada (web/movil).
REM Alcampo bloquea a los runners de GitHub, asi que se rastrea desde este PC
REM (abre un Chrome fuera de pantalla unos minutos) y se sube al repo.
REM Uso: doble clic, o programarlo en el Programador de tareas de Windows.
REM
REM Solo se rastrea el CATALOGO completo (unas 60 peticiones, 5 s entre ellas):
REM ya incluye la lista habitual, asi que no hacen falta ~80 busquedas sueltas
REM (con ellas Alcampo mostro un CAPTCHA el 2026-11-04). Si vuelve a mostrarlo,
REM el script se detiene solo: espera 1 hora SIN tocar Alcampo y repite UNA vez.
cd /d "%~dp0.."
if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat
git pull --rebase origin master || goto :error
python scripts\rastrear_catalogo.py --solo alcampo --pausa 5 || goto :error
git add webapp\static\catalogo_alcampo.json
git diff --cached --quiet && (echo Sin cambios en Alcampo. & goto :fin)
git commit -m "Actualiza catalogo_alcampo.json" || goto :error
git push origin master || goto :error
echo Listo: Alcampo actualizado y subido.
goto :fin
:error
echo ERROR: algo ha fallado, mira los mensajes de arriba.
:fin
pause
