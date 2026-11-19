@echo off
rem Uma vez so, na maquina do agendamento: autoriza a conta contabilidade36 a enviar o relatorio geral por e-mail.
rem Abre o navegador; entre com contabilidade36@akartos.com.br e clique em Permitir. No fim chega um e-mail de teste.
cd /d "%~dp0santander"
"%~dp0santander\santander.exe" --autorizar-email
echo.
pause
