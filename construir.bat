@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
set "ROOT=%~dp0"
set "CRED=%ROOT%bradesco\credentials.json"
set "TOK=%ROOT%bradesco\token.json"

echo ============================================================
echo  CONSTRUINDO EXECUTAVEIS DOS BANCOS
echo ============================================================
echo.

REM ── Opções comuns a todos os bancos ──────────────────────────
set "COMUM=--onedir --clean --noconfirm"
set "COMUM=%COMUM% --collect-all selenium"
set "COMUM=%COMUM% --collect-all google.auth"
set "COMUM=%COMUM% --collect-all google_auth_oauthlib"
set "COMUM=%COMUM% --collect-all googleapiclient"
set "COMUM=%COMUM% --collect-all winotify"
set "COMUM=%COMUM% --hidden-import pynput.keyboard"
set "COMUM=%COMUM% --hidden-import pynput.mouse"
set "COMUM=%COMUM% --hidden-import dotenv"

REM ── [1/5] BRADESCO ───────────────────────────────────────────
echo [1/5] Construindo BRADESCO...
cd /d "%ROOT%bradesco"
python -m PyInstaller %COMUM% ^
  --collect-all anthropic ^
  --collect-all PIL ^
  --name bradesco ^
  --distpath "%ROOT%Executavel_bancos" ^
  --workpath "%ROOT%build_tmp\bradesco" ^
  main.py
if errorlevel 1 ( echo ERRO no Bradesco & goto :fim )
call :restaurar bradesco
echo    OK: Executavel_bancos\bradesco\

REM ── [2/5] SANTANDER ──────────────────────────────────────────
echo.
echo [2/5] Construindo SANTANDER...
cd /d "%ROOT%santander"
python -m PyInstaller %COMUM% ^
  --name santander ^
  --distpath "%ROOT%Executavel_bancos" ^
  --workpath "%ROOT%build_tmp\santander" ^
  main.py
if errorlevel 1 ( echo ERRO no Santander & goto :fim )
call :restaurar santander
echo    OK: Executavel_bancos\santander\

REM ── [3/5] SICREDI ────────────────────────────────────────────
echo.
echo [3/5] Construindo SICREDI...
cd /d "%ROOT%sicredi"
python -m PyInstaller %COMUM% ^
  --name sicredi ^
  --distpath "%ROOT%Executavel_bancos" ^
  --workpath "%ROOT%build_tmp\sicredi" ^
  main.py
if errorlevel 1 ( echo ERRO no Sicredi & goto :fim )
call :restaurar sicredi
echo    OK: Executavel_bancos\sicredi\

REM ── [4/5] CAIXA ──────────────────────────────────────────────
echo.
echo [4/5] Construindo CAIXA...
cd /d "%ROOT%caixa"
python -m PyInstaller %COMUM% ^
  --name caixa ^
  --distpath "%ROOT%Executavel_bancos" ^
  --workpath "%ROOT%build_tmp\caixa" ^
  main.py
if errorlevel 1 ( echo ERRO na Caixa & goto :fim )
call :restaurar caixa
echo    OK: Executavel_bancos\caixa\

REM ── [5/5] ITAU ───────────────────────────────────────────────
echo.
echo [5/5] Construindo ITAU...
cd /d "%ROOT%itau"
python -m PyInstaller %COMUM% ^
  --name itau ^
  --distpath "%ROOT%Executavel_bancos" ^
  --workpath "%ROOT%build_tmp\itau" ^
  main.py
if errorlevel 1 ( echo ERRO no Itau & goto :fim )
call :restaurar itau
echo    OK: Executavel_bancos\itau\

REM ── Resumo ───────────────────────────────────────────────────
echo.
echo ============================================================
echo  CONCLUIDO — executaveis em: Executavel_bancos\
echo ============================================================
goto :fim

REM ── Sub-rotina de restauração ─────────────────────────────────
:restaurar
set "BANCO=%~1"
set "DEST=%ROOT%Executavel_bancos\%BANCO%"
set "SRC=%ROOT%%BANCO%"

REM abrir.bat
(echo @echo off
 echo call %BANCO%.exe
 echo if errorlevel 1 pause) > "%DEST%\abrir.bat"

REM .env (copia da pasta fonte se existir)
if exist "%SRC%\.env" copy /Y "%SRC%\.env" "%DEST%\.env" >nul

REM credentials.json
if exist "%SRC%\credentials.json" (
    copy /Y "%SRC%\credentials.json" "%DEST%\credentials.json" >nul
) else if exist "%CRED%" (
    copy /Y "%CRED%" "%DEST%\credentials.json" >nul
)

REM token.json
if exist "%SRC%\token.json" (
    copy /Y "%SRC%\token.json" "%DEST%\token.json" >nul
) else if exist "%TOK%" (
    copy /Y "%TOK%" "%DEST%\token.json" >nul
)

echo    Config restaurada em Executavel_bancos\%BANCO%\
goto :eof

:fim
cd /d "%ROOT%"
pause
