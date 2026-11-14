@echo off
setlocal
chcp 65001 >nul
title APEX - Atualizador

cd /d "%~dp0"

echo ================================================
echo             APEX - ATUALIZADOR
echo ================================================
echo.

if not exist "%~dp0ATUALIZAR_APEX.ps1" (
    echo ERRO: nao encontrei ATUALIZAR_APEX.ps1.
    echo Deixe os dois arquivos juntos na pasta principal do APEX.
    echo.
    pause
    exit /b 1
)

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0ATUALIZAR_APEX.ps1"
set "APEX_EXIT_CODE=%ERRORLEVEL%"

echo.
if not "%APEX_EXIT_CODE%"=="0" (
    echo O atualizador terminou com erro. Copie a mensagem acima para enviar ao suporte.
) else (
    echo Processo finalizado.
)
echo.
pause
exit /b %APEX_EXIT_CODE%
