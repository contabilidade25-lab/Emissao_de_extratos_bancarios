@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
set "ROOT=%~dp0"

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

REM ── [1/4] BRADESCO ───────────────────────────────────────────
echo [1/4] Construindo BRADESCO...
cd /d "%ROOT%bradesco"
pyinstaller %COMUM% ^
  --collect-all anthropic ^
  --collect-all PIL ^
  --name bradesco ^
  --distpath "%ROOT%Executavel_bancos" ^
  --workpath "%ROOT%build_tmp\bradesco" ^
  main.py
if errorlevel 1 ( echo ERRO no Bradesco & goto :fim )
echo    OK: Executavel_bancos\bradesco\

REM ── [2/4] SANTANDER ──────────────────────────────────────────
echo.
echo [2/4] Construindo SANTANDER...
cd /d "%ROOT%santander"
pyinstaller %COMUM% ^
  --name santander ^
  --distpath "%ROOT%Executavel_bancos" ^
  --workpath "%ROOT%build_tmp\santander" ^
  main.py
if errorlevel 1 ( echo ERRO no Santander & goto :fim )
echo    OK: Executavel_bancos\santander\

REM ── [3/4] SICREDI ────────────────────────────────────────────
echo.
echo [3/4] Construindo SICREDI...
cd /d "%ROOT%sicredi"
pyinstaller %COMUM% ^
  --name sicredi ^
  --distpath "%ROOT%Executavel_bancos" ^
  --workpath "%ROOT%build_tmp\sicredi" ^
  main.py
if errorlevel 1 ( echo ERRO no Sicredi & goto :fim )
echo    OK: Executavel_bancos\sicredi\

REM ── [4/4] CAIXA ──────────────────────────────────────────────
echo.
echo [4/4] Construindo CAIXA...
cd /d "%ROOT%caixa"
pyinstaller %COMUM% ^
  --name caixa ^
  --distpath "%ROOT%Executavel_bancos" ^
  --workpath "%ROOT%build_tmp\caixa" ^
  main.py
if errorlevel 1 ( echo ERRO na Caixa & goto :fim )
echo    OK: Executavel_bancos\caixa\

REM ── Resumo ────────────────────────────────────────────────────
echo.
echo ============================================================
echo  CONCLUIDO — executaveis em: Executavel_bancos\
echo ============================================================
echo.
echo Copie para CADA pasta em Executavel_bancos\ os seguintes arquivos:
echo   - .env
echo   - credentials.json
echo   - token.json  (ou deixe criar no primeiro uso)
echo.

:fim
cd /d "%ROOT%"
pause
