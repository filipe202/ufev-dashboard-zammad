@echo off
REM Script silencioso para execução automática via Task Scheduler
REM NÃO mostra prompts nem pausa - adequado para automação

REM ============================================
REM CONFIGURAÇÃO - EDITE ESTAS LINHAS
REM ============================================

REM Token da API Zammad (obrigatório)
set ZAMMAD_TOKEN=1qbRbHElT2yBzhPPc7sFnE-BQITXT9asONjyx_rH6DyJc-U5JJ7CYWcfWmVa6s2x
set ZAMMAD_BASE_URL=https://ufevsuporte.zammad.com

REM Verificar SSL (opcional: true ou false)
set ZAMMAD_VERIFY_SSL=false

REM ============================================
REM EXECUÇÃO SILENCIOSA
REM ============================================

REM Criar log com timestamp
set LOG_DIR=%~dp0logs
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

set TIMESTAMP=%date:~-4,4%%date:~-10,2%%date:~-7,2%_%time:~0,2%%time:~3,2%%time:~6,2%
set TIMESTAMP=%TIMESTAMP: =0%
set LOG_FILE=%LOG_DIR%\mark_articles_%TIMESTAMP%.log

echo [%date% %time%] Iniciando execucao automatica >> "%LOG_FILE%"

cd /d "%~dp0"
python scripts\mark_articles_internal_fast.py >> "%LOG_FILE%" 2>&1

echo [%date% %time%] Execucao concluida >> "%LOG_FILE%"

REM Limpar logs antigos (manter apenas últimos 30 dias)
forfiles /p "%LOG_DIR%" /s /m *.log /d -30 /c "cmd /c del @path" 2>nul
