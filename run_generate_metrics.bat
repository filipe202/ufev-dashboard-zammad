@echo off
REM Script para gerar métricas do Zammad
REM Configure as variáveis de ambiente abaixo antes de executar

REM ============================================
REM CONFIGURAÇÃO - EDITE ESTAS LINHAS
REM ============================================

REM Token da API Zammad (obrigatório)
set ZAMMAD_TOKEN=1qbRbHElT2yBzhPPc7sFnE-BQITXT9asONjyx_rH6DyJc-U5JJ7CYWcfWmVa6s2x
set ZAMMAD_BASE_URL=https://ufevsuporte.zammad.com

REM Verificar SSL (opcional: true ou false)
set ZAMMAD_VERIFY_SSL=false

REM ============================================
REM NÃO EDITE ABAIXO DESTA LINHA
REM ============================================

echo ========================================
echo Gerando métricas do Zammad...
echo ========================================
echo.

REM Verificar se o token foi configurado
if "%ZAMMAD_TOKEN%"=="SEU_TOKEN_AQUI" (
    echo ERRO: Por favor, edite o arquivo run_generate_metrics.bat
    echo e configure a variavel ZAMMAD_TOKEN com seu token real.
    echo.
    pause
    exit /b 1
)

REM Executar o script Python
python scripts\generate_metrics.py

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ========================================
    echo Metricas geradas com sucesso!
    echo ========================================
    echo.
    echo Agora voce pode executar o dashboard com: npm start
) else (
    echo.
    echo ========================================
    echo ERRO ao gerar metricas!
    echo ========================================
)

echo.
pause
