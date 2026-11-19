@echo off
rem Usado pelo executar_mensal.ps1, a partir da pasta dos robos: rodar_robo.bat <nome.exe> <pasta> [opcoes]
rem (so nomes curtos, sem espaco: o caminho completo pode ter espaco, ex.: "LUIZ FELIPE")
rem Roda o robo nesta janela; no fim a janela fica aberta com o relatorio da execucao.
title ROBO %1
cd /d "%~dp0%~2"
".\%~1" %3
echo.
echo [ROBO FINALIZADO]
